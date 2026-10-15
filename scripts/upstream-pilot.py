#!/usr/bin/env python3
"""Reuse frozen contracts on a bounded, chronological upstream change queue."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "workflow", REPO / "scripts/workflow-pilot.py"
)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
art = workflow.art


def now():
    return datetime.now(timezone.utc).isoformat()


def git(upstream, *args):
    return subprocess.check_output(
        ["git", "-C", str(upstream), *args], text=True, timeout=60
    ).strip()


def seal(folder):
    art.save(folder / "seal.json", art.manifest(folder))


def verify(root):
    state = art.read(root / "state.json")
    if state["schema"] != 1:
        raise ValueError("Unsupported upstream study schema")
    for name, expected in state["frozen"].items():
        if art.manifest(root / name) != expected:
            raise ValueError(f"Frozen study changed: {name}")
    if workflow.maintained.application.packages(state["python"]) != state["packages"]:
        raise ValueError("Dependencies changed; preserve study and use a new root")
    selection = root / "selection"
    if selection.exists() and not (selection / "seal.json").exists():
        raise ValueError(
            "Selection incomplete or seal missing; preserve it and use a new root"
        )
    for result in (root / "runs").glob("*/result.json"):
        if not (result.parent / "seal.json").exists():
            raise ValueError("Completed result has no evidence seal")
    seals = [selection / "seal.json", *(root / "runs").glob("*/seal.json")]
    for path in seals:
        if path.exists():
            files = art.manifest(path.parent)
            files.pop("seal.json")
            if files != art.read(path):
                raise ValueError("Selected queue or completed evidence changed")
    if (root / "completion.json").exists():
        saved = art.read(root / "completion.json")
        if any(art.manifest(root / n) != saved[n] for n in ("selection", "runs")):
            raise ValueError("Completed evidence changed or disappeared")
    return state


def check_binary(binary):
    probe = subprocess.run(
        [str(binary), "ci", "check", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0 or "--base-config" not in probe.stdout:
        raise ValueError(
            "The selected binary lacks native ci check; build the current source first"
        )


def prepare(root, study, binary, limit, mode="mainline", offset=0):
    if root.exists():
        raise ValueError("Preserve existing studies; choose an explicit new root")
    check_binary(binary)
    original = workflow.verify(study)
    root.mkdir(parents=True)
    for name in ("base", "frozen"):
        shutil.copytree(study / name, root / name)
    (root / "runtime").mkdir()
    shutil.copyfile(binary, root / "runtime" / workflow.EXE)
    (root / "runtime" / workflow.EXE).chmod(0o755)
    # Relocate the adapter. Test inputs, expectations and policy are copied
    # unchanged from the reviewed green study before any new revision is selected.
    config = art.read(root / "base/wraith.yaml")
    config["agent"]["command"] = " ".join(
        shlex.quote(str(p))
        for p in (
            original["python"],
            "wraith_adapter.py",
            str(root / "frozen/entrypoint.py") + ":evaluate",
        )
    )
    art.save(root / "base/wraith.yaml", config)
    state = {
        "schema": 1,
        "source": original["source"],
        "python": original["python"],
        "packages": original["packages"],
        "frozenAt": now(),
        "scope": "chronological_upstream_reproduction_with_local_prerequisite_fixes",
        "selectionRule": {
            "limit": limit,
            **({"offset": offset} if offset else {}),
            "path": "src/smolagents/agents.py",
            "mode": mode,
            "order": "first-parent chronological descendants after base, touching path"
            if mode == "mainline"
            else "oldest open PRs by creation time targeting main and touching path; never replace blocked PRs",
            "carryForward": "Apply frozen base.patch unchanged; conflicts are integration blocks, not regressions",
        },
        "frozen": {n: art.manifest(root / n) for n in ("base", "frozen", "runtime")},
    }
    art.save(root / "state.json", state)
    print(
        "Contracts and selection rule frozen; fetch upstream only after this checkpoint."
    )


def select(root, state, upstream, tip):
    if state["selectionRule"].get("mode", "mainline") != "mainline":
        raise ValueError("This study froze an open-PR selection rule")
    target = root / "selection"
    if target.exists():
        raise ValueError("Queue already selected or incomplete; use a new study")
    revision = git(upstream, "rev-parse", "--verify", tip + "^{commit}")
    base = state["source"]["revision"]
    chain = git(upstream, "rev-list", "--first-parent", revision).splitlines()
    if base not in chain:
        raise ValueError("Base is not on the selected tip's first-parent history")
    selected = []
    for sha in reversed(chain[: chain.index(base)]):
        parent = git(upstream, "rev-parse", sha + "^1")
        paths = git(upstream, "diff", "--name-only", parent, sha).splitlines()
        if state["selectionRule"]["path"] in paths:
            selected.append({"revision": sha, "parent": parent})
        if len(selected) == state["selectionRule"]["limit"]:
            break
    target.mkdir()
    art.save(
        target / "queue.json",
        {
            "schema": 1,
            "selectedAt": now(),
            "tip": revision,
            "base": base,
            "selectionRule": state["selectionRule"],
            "candidates": selected,
        },
    )
    # Freeze the exact exports before evaluating any candidate. Archive includes
    # upstream tests unchanged; no commits are selected by whether they pass.
    for row in selected:
        sha = row["revision"]
        with (target / (sha + ".tar")).open("wb") as stream:
            subprocess.run(
                ["git", "-C", str(upstream), "archive", sha],
                stdout=stream,
                check=True,
                timeout=60,
            )
    seal(target)
    print(f"Selected {len(selected)} chronological upstream revisions")


def select_prs(root, state, upstream):
    """Network is confined to selection, before any candidate execution."""
    if state["selectionRule"]["mode"] != "open-prs":
        raise ValueError("This study froze a mainline selection rule")
    target = root / "selection"
    if target.exists():
        raise ValueError("Queue already selected or incomplete; use a new study")
    target.mkdir()
    repo = "huggingface/smolagents"
    selected = []
    page = 1
    skipped = 0
    while len(selected) < state["selectionRule"]["limit"]:
        pulls = json.loads(
            subprocess.check_output(
                [
                    "gh",
                    "api",
                    f"repos/{repo}/pulls?state=open&base=main&sort=created&direction=asc&per_page=100&page={page}",
                ],
                text=True,
                timeout=60,
            )
        )
        if not pulls:
            break
        for pr in pulls:
            files = json.loads(
                subprocess.check_output(
                    [
                        "gh",
                        "api",
                        "--paginate",
                        "--slurp",
                        f"repos/{repo}/pulls/{pr['number']}/files?per_page=100",
                    ],
                    text=True,
                    timeout=60,
                )
            )
            if not any(
                f["filename"] == state["selectionRule"]["path"]
                for batch in files
                for f in batch
            ):
                continue
            if skipped < state["selectionRule"].get("offset", 0):
                skipped += 1
                continue
            selected.append(
                {
                    "pullRequest": pr["number"],
                    "url": pr["html_url"],
                    "head": pr["head"]["sha"],
                    "createdAt": pr["created_at"],
                }
            )
            if len(selected) == state["selectionRule"]["limit"]:
                break
        if len(pulls) < 100:
            break
        page += 1
    # Save selection before fetching merges; unavailable or stale merge refs stay
    # in the denominator. Never choose a replacement based on evaluation results.
    queue = {
        "schema": 1,
        "selectedAt": now(),
        "tip": state["source"]["revision"],
        "base": state["source"]["revision"],
        "selectionRule": state["selectionRule"],
        "candidates": selected,
    }
    art.save(target / "queue.json", queue)
    for row in selected:
        phase = workflow.execute(
            [
                "git",
                "-C",
                upstream,
                "fetch",
                "origin",
                f"refs/pull/{row['pullRequest']}/merge",
            ],
            target,
            f"fetch-{row['pullRequest']}",
        )
        row["revision"] = f"pr-{row['pullRequest']}"
        row["parent"] = state["source"]["revision"]
        if phase["exit"] != 0:
            row["blocked"] = "upstream_test_merge_unavailable"
            continue
        sha = git(upstream, "rev-parse", "FETCH_HEAD")
        parents = git(upstream, "show", "-s", "--format=%P", sha).split()
        row["observedTestMerge"] = sha
        row["observedParents"] = parents
        if parents != [state["source"]["revision"], row["head"]]:
            row["blocked"] = "test_merge_is_stale_or_head_changed"
            continue
        row["revision"] = sha
        with (target / (sha + ".tar")).open("wb") as stream:
            subprocess.run(
                ["git", "-C", str(upstream), "archive", sha],
                stdout=stream,
                check=True,
                timeout=60,
            )
    art.save(target / "queue.json", queue)
    seal(target)
    print(f"Selected {len(selected)} oldest open PRs; blocked merges remain recorded")


def validate_queue(pinned):
    if pinned.get("schema") != 1:
        raise ValueError("Unsupported pinned queue schema")

    def sha(value):
        return isinstance(value, str) and re.fullmatch("[0-9a-f]{40}", value)

    if not sha(pinned.get("base")) or not 1 <= len(pinned.get("candidates", [])) <= 10:
        raise ValueError("Pinned queue needs a full base SHA and one to ten candidates")
    numbers = [r.get("pullRequest") for r in pinned["candidates"]]
    if any(type(n) is not int or n < 1 for n in numbers) or len(set(numbers)) != len(
        numbers
    ):
        raise ValueError("Pinned PR numbers must be positive and unique")
    for row in pinned["candidates"]:
        if not sha(row.get("head")):
            raise ValueError("Pinned PR heads must be full commit SHAs")
        if row.get("blocked"):
            if (
                row["blocked"]
                not in (
                    "test_merge_is_stale_or_head_changed",
                    "upstream_test_merge_unavailable",
                )
                or row["revision"] != f"pr-{row['pullRequest']}"
            ):
                raise ValueError("Unsupported pinned block classification")
        elif not sha(row.get("revision")) or not re.fullmatch(
            "[0-9a-f]{64}", pinned.get("archives", {}).get(row["revision"] + ".tar", "")
        ):
            raise ValueError("Pinned merge requires a full SHA and archive fingerprint")


def reproduce(root, binary, upstream, python, install, queue_path):
    """One recorded replay; no PR re-selection, hidden retry or provider call."""
    pinned = art.read(queue_path)
    validate_queue(pinned)
    if root.exists():
        raise ValueError("Preserve existing studies; choose an explicit new root")
    check_binary(binary)
    reference = root.with_name(root.name + "-reference")
    workflow.prepare(reference, binary, upstream, python, install, recorded=True)
    if not upstream:
        upstream = reference / "upstream"
    prepare(root, reference, binary, len(pinned["candidates"]), "open-prs")
    state = verify(root)
    if (
        pinned["base"] != state["source"]["revision"]
        or pinned["contractSha256"] != state["frozen"]["frozen"]["contracts.json"]
    ):
        raise ValueError("Pinned queue does not match frozen source and contracts")
    selection = root / "selection"
    selection.mkdir()
    for row in pinned["candidates"]:
        if row.get("blocked"):
            continue
        sha = row["revision"]
        if not re.fullmatch("[0-9a-f]{40}", sha):
            raise ValueError("Pinned revisions must be full commit SHAs")
        exists = subprocess.run(
            ["git", "-C", str(upstream), "cat-file", "-e", sha + "^{commit}"],
            capture_output=True,
            timeout=30,
        )
        if exists.returncode:
            if not install:
                raise ValueError(
                    "Pinned merge unavailable locally; use explicit --install for network setup"
                )
            subprocess.run(
                ["git", "-C", str(upstream), "fetch", "origin", sha],
                check=True,
                timeout=60,
            )
        parents = git(upstream, "show", "-s", "--format=%P", sha).split()
        if parents != [pinned["base"], row["head"]]:
            raise ValueError("Pinned test merge does not match frozen base and PR head")
        archive = selection / (sha + ".tar")
        with archive.open("wb") as stream:
            subprocess.run(
                ["git", "-C", str(upstream), "archive", sha],
                stdout=stream,
                check=True,
                timeout=60,
            )
        if art.digest(archive) != pinned["archives"][archive.name]:
            raise ValueError("Pinned source archive fingerprint changed")
    queue = {
        "schema": 1,
        "base": pinned["base"],
        "tip": pinned["base"],
        "selectionRule": {"mode": "pinned_reproduction", "batches": pinned["batches"]},
        "candidates": pinned["candidates"],
    }
    art.save(selection / "queue.json", queue)
    seal(selection)
    state["scope"] = "recorded_reproduction_of_frozen_upstream_queue"
    state["selectionRule"] = queue["selectionRule"]
    state["pinnedQueueSha256"] = art.digest(queue_path)
    art.save(root / "state.json", state)
    run(root, state)
    observed = {
        str(r["pullRequest"]): r["category"]
        for r in art.read(root / "assessment.json")["results"]
    }
    if observed != pinned.get("expectedCategories"):
        raise ValueError(
            "Recorded reproduction decisions differ; completed evidence is preserved for investigation"
        )


def classification(wraith_exit, upstream_exit, baseline_passed=True):
    if not baseline_passed:
        return "baseline_failure"
    if wraith_exit in (2, 130) or upstream_exit not in (0, 1):
        return "execution_or_setup_failure"
    if wraith_exit == 3:
        return "inconclusive"
    if wraith_exit == 1:
        return (
            "wraith_failure_needs_review" if upstream_exit == 0 else "both_checks_fail"
        )
    return "both_checks_pass" if upstream_exit == 0 else "upstream_failure_only"


def replay_selection(root, state, previous):
    old = verify(previous)
    if not (previous / "completion.json").exists():
        raise ValueError("Replay requires a completed preserved study")
    if (
        state["selectionRule"] != old["selectionRule"]
        or state["source"] != old["source"]
    ):
        raise ValueError("Replay must retain the original selection rule and source")
    if state["frozen"]["frozen"] != old["frozen"]["frozen"]:
        raise ValueError("Replay must retain all original fixtures")
    if (root / "selection").exists():
        raise ValueError("Selection already exists; preserve the study")
    shutil.copytree(previous / "selection", root / "selection")
    state["scope"] = "recorded_reproduction_of_frozen_upstream_queue"
    state["replayedSelectionSha256"] = art.digest(previous / "selection/queue.json")
    art.save(root / "state.json", state)


def run(root, state):
    if (root / "completion.json").exists():
        raise ValueError("Study complete; evidence cannot be overwritten")
    queue = art.read(root / "selection/queue.json")
    runs = root / "runs"
    runs.mkdir(exist_ok=True)
    for row in queue["candidates"]:
        sha = row["revision"]
        folder = runs / sha
        if folder.exists():
            if (folder / "seal.json").exists():
                continue
            raise ValueError(
                "Incomplete attempt preserved; use a new study, do not retry it"
            )
        folder.mkdir()
        if row.get("blocked"):
            art.save(
                folder / "result.json",
                {**row, "category": row["blocked"], "completedAt": now()},
            )
            seal(folder)
            print(sha[:12], row["blocked"], flush=True)
            continue
        source = folder / "source"
        source.mkdir()
        with tarfile.open(root / "selection" / (sha + ".tar")) as archive:
            archive.extractall(source, filter="data")
        # Prerequisite fixes are transparent local modifications, not upstream
        # commits or new candidate faults. Never resolve conflicts to force a run.
        patch = workflow.execute(
            ["git", "apply", "--no-index", str(root / "frozen/base.patch")],
            folder,
            "prerequisites",
            cwd=source,
        )
        if patch["exit"] != 0:
            result = {
                **row,
                "category": "prerequisite_patch_conflict",
                "patch": patch,
                "completedAt": now(),
            }
        else:
            for name in ("wraith.yaml", "wraith_adapter.py"):
                shutil.copyfile(root / "base" / name, source / name)
            source_before = art.manifest(source)
            upstream_tests = workflow.maintained.tests(root, state, source, folder)
            native = folder / "native"
            gate = workflow.execute(
                [
                    root / "runtime" / workflow.EXE,
                    "--config",
                    source / "wraith.yaml",
                    "ci",
                    "check",
                    "--base-config",
                    root / "base/wraith.yaml",
                    "--jobs",
                    "4",
                    "--artifacts",
                    native,
                    "--output",
                    "json",
                ],
                folder,
                "ci",
                workflow.environment(root, source),
            )
            if art.manifest(source) != source_before:
                raise ValueError(
                    "Evaluation modified source; preserve incomplete evidence"
                )
            native_result = (
                art.read(native / "ci.json") if (native / "ci.json").exists() else {}
            )
            result = {
                **row,
                "category": classification(
                    gate["exit"],
                    upstream_tests["exit"],
                    native_result.get("baselinePassed", True),
                ),
                "wraith": gate,
                "upstream": upstream_tests,
                "source": source_before,
                "completedAt": now(),
                "reviewedUsefulCatch": None if gate["exit"] == 1 else False,
            }
            if (folder / "upstream.xml").exists():
                result["upstreamCounts"] = workflow.maintained.junit(
                    folder / "upstream.xml"
                )
        art.save(folder / "result.json", result)
        seal(folder)
        print(sha[:12], result["category"], flush=True)
    report(root, state)
    art.save(
        root / "completion.json",
        {n: art.manifest(root / n) for n in ("selection", "runs")},
    )


def report(root, state):
    queue = art.read(root / "selection/queue.json")
    rows = [
        art.read(root / "runs" / r["revision"] / "result.json")
        for r in queue["candidates"]
        if (root / "runs" / r["revision"] / "result.json").exists()
    ]
    summary = {
        "schema": 1,
        "scope": state["scope"],
        "repository": state["source"]["repository"],
        "base": queue["base"],
        "tip": queue["tip"],
        "frozenAt": state["frozenAt"],
        "contractSha256": state["frozen"]["frozen"]["contracts.json"],
        "selectionRule": state["selectionRule"],
        "scenarios": len(art.read(root / "frozen/contracts.json")),
        "providerRequests": 0,
        "selected": len(queue["candidates"]),
        "completed": len(rows),
        "results": [
            {k: row[k] for k in ("revision", "parent", "category")}
            | {
                "pullRequest": row.get("pullRequest"),
                "url": row.get("url"),
                "wraithExit": row.get("wraith", {}).get("exit"),
                "upstreamExit": row.get("upstream", {}).get("exit"),
                "ciWallSeconds": row.get("wraith", {}).get("wallSeconds"),
                "upstreamCounts": row.get("upstreamCounts"),
            }
            for row in rows
        ],
        "limits": [
            "Historical upstream changes, not prospective discovery or independent adoption.",
            "Three frozen local prerequisite fixes remain applied; this is not untouched upstream.",
            "Only one agent/framework and sixteen scripted offline scenarios; no model quality estimate.",
            "No human time savings, reviewer effort, customer ROI, or demand measured.",
            "Failure entries require review; a matching unit test can detect the same behavior.",
        ],
    }
    art.save(root / "assessment.json", summary)
    lines = [
        "# Frozen-contract upstream change study",
        "",
        f"{len(rows)}/{summary['selected']} selected revisions completed; {summary['scenarios']} frozen cases per version; no provider requests.",
        "",
        "| Revision | Result | Wraith | Upstream subset | CI seconds |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in summary["results"]:
        lines.append(
            f"| `{row['revision'][:12]}` | {row['category']} | {row['wraithExit']} | {row['upstreamExit']} | {row['ciWallSeconds']} |"
        )
    lines += ["", *summary["limits"], ""]
    (root / "report.md").write_text("\n".join(lines))
    print(root / "report.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    setup.add_argument("--study", type=Path, required=True)
    setup.add_argument("--binary", type=Path, required=True)
    setup.add_argument("--mode", choices=("mainline", "open-prs"), default="mainline")
    setup.add_argument("--offset", type=int, choices=range(0, 101), default=0)
    setup.add_argument("--limit", type=int, choices=range(1, 11), default=5)
    selection = sub.add_parser("select")
    selection.add_argument("--upstream", type=Path, required=True)
    selection.add_argument("--tip", required=True)
    prs = sub.add_parser("select-prs")
    prs.add_argument("--upstream", type=Path, required=True)
    replay = sub.add_parser("replay-selection")
    replay.add_argument("--from-study", type=Path, required=True)
    reproduction = sub.add_parser("reproduce")
    reproduction.add_argument(
        "--binary", type=Path, default=REPO / "target/debug" / workflow.EXE
    )
    reproduction.add_argument("--upstream", type=Path)
    reproduction.add_argument("--python", type=Path)
    reproduction.add_argument("--install", action="store_true")
    reproduction.add_argument(
        "--queue", type=Path, default=REPO / "docs/evidence/upstream-queue.json"
    )
    for command in ("run", "report", "verify"):
        sub.add_parser(command)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "reproduce":
        reproduce(
            root,
            args.binary.resolve(),
            args.upstream,
            args.python,
            args.install,
            args.queue.resolve(),
        )
        return 0
    if args.command == "prepare":
        prepare(
            root,
            args.study.resolve(),
            args.binary.resolve(),
            args.limit,
            args.mode,
            args.offset,
        )
        return 0
    state = verify(root)
    if args.command == "select":
        select(root, state, args.upstream.resolve(), args.tip)
    elif args.command == "select-prs":
        select_prs(root, state, args.upstream.resolve())
    elif args.command == "replay-selection":
        replay_selection(root, state, args.from_study.resolve())
    elif args.command == "run":
        run(root, state)
    elif args.command == "report":
        report(root, state)
    else:
        print("Frozen source, selection, dependencies, and evidence verified")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
