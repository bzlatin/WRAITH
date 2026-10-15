#!/usr/bin/env python3
"""Finite, offline mutation calibration using the existing application pilot."""

import argparse
import ast
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/application-challenge"
spec = importlib.util.spec_from_file_location(
    "app_pilot", REPO / "scripts/application-pilot.py"
)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
art = app.artifacts


def mutate(source, change):
    """Reject ambiguous/stale anchors; never patch tests or arbitrary modules."""
    if change["file"] != "llm/models.py":
        raise ValueError("Only the approved application module may change")
    start = source.index(change["scope"])
    # Function boundaries from AST include nested functions: find the declared scope.
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and sum(map(len, lines[: n.lineno - 1]))
        <= start
        < sum(map(len, lines[: n.lineno]))
    )
    end = sum(map(len, lines[: node.end_lineno]))
    section = source[start:end]
    if section.count(change["old"]) != 1:
        raise ValueError("Mutation anchor missing or ambiguous: " + change["id"])
    result = (
        source[:start] + section.replace(change["old"], change["new"], 1) + source[end:]
    )
    ast.parse(result)
    return result


def provision(root, resources, binary, expanded, development=False):
    if (root / "campaign.json").exists():
        state = app.verify(root)
        if art.read(root / "challenge.json")["expanded"] != expanded:
            raise ValueError("Suite mode changed; use an explicit new root")
        if art.read(root / "challenge.json").get("development", False) != development:
            raise ValueError("Campaign purpose changed; use an explicit new root")
        return state
    if root.exists():
        raise ValueError("Incomplete root retained; choose an explicit new --root")
    root.mkdir(parents=True)
    for name in ("upstream", "venv"):
        (root / name).symlink_to((resources / name).resolve(), target_is_directory=True)
    draft = root / "fixture-draft"
    shutil.copytree(app.FIXTURE, draft, ignore=shutil.ignore_patterns("__pycache__"))
    (draft / "entrypoint.py").rename(draft / "cli_entrypoint.py")
    for name in ("entrypoint.py", "oracle.py", "changes.json"):
        shutil.copyfile(EXAMPLE / name, draft / name)
    if development:
        for name in ("tasks.json", "acceptance.py"):
            shutil.copyfile(EXAMPLE / name, draft / name)
    shutil.copyfile(EXAMPLE / "contracts.json", draft / "extra-contracts.json")
    app.prepare(
        root,
        binary,
        False,
        fixture=draft,
        reviewed_cases=draft / "extra-contracts.json" if expanded else None,
    )
    state = app.verify(root)
    oracle = art.execute(
        [state["python"], root / "frozen/oracle.py"],
        root,
        "baseline-oracle",
        app.environment(root, root / "base"),
    )
    if oracle["exit"] != 0:
        raise ValueError("Baseline witness checks failed; preserve root")
    art.save(
        root / "challenge.json",
        {
            "schema": 1,
            "expanded": expanded,
            "development": development,
            "oracle": oracle,
            "planSha256": art.digest(root / "frozen/changes.json"),
        },
    )
    return state


def classify(category, oracle, upstream, check, witness_failed):
    if oracle not in (0, 1) or upstream not in (0, 1) or check not in (0, 1):
        return "execution_error"
    if category == "seeded_fault" and (oracle != 1 or not witness_failed):
        return "unvalidated_fault"
    if category == "benign_control":
        return (
            "control_pass"
            if (oracle, upstream, check) == (0, 0, 0)
            else "control_failure"
        )
    return "caught" if check == 1 else "missed"


def run(root, state):
    if (root / "completion.json").exists():
        print(root / "report.md")
        return 0 if art.read(root / "completion.json")["validCalibration"] else 2
    for change in art.read(root / "frozen/changes.json"):
        folder = root / "changes" / change["id"]
        if folder.exists():
            if (folder / "result.json").exists() and (
                folder / "evidence.json"
            ).exists():
                continue
            raise ValueError("Partial change retained; choose a new root")
        folder.mkdir(parents=True)
        source = folder / "source"
        shutil.copytree(root / "base", source)
        path = source / change["file"]
        path.write_text(mutate(path.read_text(), change))
        before = art.manifest(source)
        shutil.copyfile(Path(__file__), folder / "runner.py")
        env = app.environment(root, source)
        phases = {
            "oracle": art.execute(
                [state["python"], root / "frozen/oracle.py"], folder, "oracle", env
            )
        }
        phases["upstreamTests"] = app.upstream_tests(root, state, source, folder)
        phases["check"] = art.execute(
            [state["binary"], "check", "--output", "json"],
            folder,
            "check",
            env,
            workdir=root / "project",
        )
        witness = False
        if phases["oracle"]["exit"] in (0, 1):
            witness = any(
                f["case"] == change.get("witness")
                for f in art.read(folder / "oracle.stdout")["failures"]
            )
        decision = classify(
            change["category"],
            phases["oracle"]["exit"],
            phases["upstreamTests"]["exit"],
            phases["check"]["exit"],
            witness,
        )
        result = {
            "change": change,
            "phases": phases,
            "decision": decision,
            "witnessFailed": witness,
            "source": before,
            "completedAt": datetime.now(timezone.utc).isoformat(),
        }
        if (folder / "check.stdout").stat().st_size:
            result["wraith"] = art.read(folder / "check.stdout")
            if (
                result["wraith"]["record"]["baselineId"]
                != state["baselineResult"]["record"]["id"]
            ):
                raise ValueError("Check used a different baseline")
        if before != art.manifest(source):
            raise ValueError("Source changed during evaluation")
        art.save(folder / "result.json", result)
        art.save(folder / "evidence.json", art.manifest(folder))
        print(change["id"], decision, flush=True)
        app.verify(root)
    results = [art.read(p) for p in sorted(root.glob("changes/*/result.json"))]
    invalid = [
        r["change"]["id"]
        for r in results
        if r["decision"] in ("execution_error", "unvalidated_fault", "control_failure")
    ]
    art.save(
        root / "completion.json",
        {
            "schema": 1,
            "nativeHistory": art.manifest(root / "project/.wraith/history"),
            "changeEvidence": art.manifest(root / "changes"),
            "validCalibration": not invalid,
            "invalidChanges": invalid,
        },
    )
    report(root)
    app.verify(root)
    return 2 if invalid else 0


def report(root):
    lines = [
        "# Application coverage challenge",
        "",
        "Deliberately seeded application faults and benign controls. These are calibration results, not natural discoveries, general accuracy rates, model quality, or adoption evidence.",
        "",
        "The separate witness runner executes the reviewed contracts directly; Wraith separately evaluates them through its native adapter. The original suite has nine scenarios; the expanded suite has seventeen. Existing upstream tests are the unchanged 60-test offline subset, not the full suite.",
        "",
        "| Change | Witness exit | Upstream exit | Wraith exit | Reviewed classification |",
        "| --- | --- | --- | --- | --- |",
    ]
    for p in sorted(root.glob("changes/*/result.json")):
        r = art.read(p)
        phases = r["phases"]
        run_id = r.get("wraith", {}).get("record", {}).get("id")
        link = (
            f"project/.wraith/history/{run_id}/report.html"
            if run_id
            else str(p.relative_to(root))
        )
        lines.append(
            f"| [{r['change']['id']}]({link}) | {phases['oracle']['exit']} | {phases['upstreamTests']['exit']} | {phases['check']['exit']} | {r['decision']} |"
        )
    lines += [
        "",
        "All comparisons use an explicit fixed baseline. Setup/execution errors and faults whose named witness did not fail are excluded from catches. Controls must pass the witness checks, upstream subset, and Wraith. Inputs, source, tests, policy, dependencies, runner snapshots, prior attempts, and native history are retained locally. Offline socket guard is cooperative, not a security sandbox. No provider calls are permitted.",
    ]
    (root / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--resources", type=Path, default=REPO / ".wraith/app-pilot-validated"
    )
    parser.add_argument(
        "--binary", type=Path, default=Path.home() / ".local/bin/wraith"
    )
    parser.add_argument("--expanded", action="store_true")
    parser.add_argument(
        "--development",
        action="store_true",
        help="Prepare the separate development queue instead of applying seeded faults",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.development and not args.expanded:
        raise ValueError("Development requires the expanded reviewed suite")
    state = provision(
        root,
        args.resources.resolve(),
        args.binary.resolve(),
        args.expanded,
        args.development,
    )
    if args.development:
        print(
            "Prepared development queue; use application-pilot.py --root",
            root,
            "task/evaluate/finish",
        )
        return
    code = run(root, state)
    print(root / "report.md")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError) as ex:
        print(ex, file=sys.stderr)
        sys.exit(2)
