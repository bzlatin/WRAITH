#!/usr/bin/env python3
"""Finite application feature queue, frozen tests, optional 120-request live cap."""

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
EXE = "wraith.exe" if os.name == "nt" else "wraith"
spec = importlib.util.spec_from_file_location(
    "queue_artifacts", REPO / "scripts/historical-pilot.py"
)
art = importlib.util.module_from_spec(spec)
spec.loader.exec_module(art)
FILES = [
    "examples/live-agent/agent.py",
    "examples/live-agent/cases.json",
    "adapters/python/wraith_adapter.py",
    "scripts/tests/test_live_agent.py",
    "scripts/live-pilot.py",
    "scripts/historical-pilot.py",
    "docs/evidence/live-support.json",
    *[
        "examples/feature-queue/" + name
        for name in (
            "tasks.json",
            "entry.py",
            "check.py",
            "acceptance.py",
            "recorded-decisions.json",
        )
    ],
]


def tasks(root):
    return art.read(root / "frozen/examples/feature-queue/tasks.json")


def candidate_hashes(root):
    values = {}
    for task in tasks(root):
        directory = root / "candidates" / task["id"]
        if set(art.manifest(directory)) != {"agent.py"}:
            raise ValueError("Candidate changes are limited to agent.py")
        values[task["id"]] = art.digest(directory / "agent.py")
    return values


def verify(root):
    state = art.read(root / "state.json")
    if state["schema"] != 1 or state["requestCap"] != 120:
        raise ValueError("Unsupported queue state")
    if (
        art.manifest(root / "frozen") != state["frozen"]
        or art.digest(root / EXE) != state["binarySha256"]
    ):
        raise ValueError("Frozen source, tests, policy, or binary changed")
    for mode in ("prechange", "offline", "live"):
        directory = root / mode
        if (directory / "seal.json").exists():
            actual = art.manifest(directory)
            actual.pop("seal.json")
            if actual != art.read(directory / "seal.json"):
                raise ValueError("Completed queue evidence changed")
    candidate_hashes(root)
    return state


def prepare(root, binary):
    if root.exists():
        raise ValueError("Existing experiment retained; choose an explicit new root")
    root.mkdir(parents=True)
    for name in FILES:
        target = root / "frozen" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / name, target)
    shutil.copyfile(binary, root / EXE)
    (root / EXE).chmod(0o755)
    for task in tasks(root):
        directory = root / "candidates" / task["id"]
        directory.mkdir(parents=True)
        shutil.copyfile(
            root / "frozen/examples/live-agent/agent.py", directory / "agent.py"
        )
    art.save(
        root / "state.json",
        {
            "schema": 1,
            "requestCap": 120,
            "baseSourceCommit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
            ).strip(),
            "binarySha256": art.digest(root / EXE),
            "frozen": art.manifest(root / "frozen"),
        },
    )
    directory = root / "prechange"
    directory.mkdir()
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    env.pop("WRAITH_REQUEST_BUDGET", None)
    results = {
        task["id"]: test(root, directory, "baseline", task["id"], env)
        for task in tasks(root)
    }
    art.save(directory / "completion.json", results)
    art.save(directory / "seal.json", art.manifest(directory))
    print(root / "candidates")


def apply_reviewed(root):
    verify(root)
    if any((root / mode).exists() for mode in ("offline", "live")):
        raise ValueError("Do not edit candidates after evaluation starts")
    baseline = art.digest(root / "frozen/examples/live-agent/agent.py")
    for task in tasks(root):
        directory = root / "candidates" / task["id"]
        if art.digest(directory / "agent.py") != baseline:
            raise ValueError("Candidate already changed; preserve it")
        patch = REPO / "examples/feature-queue/changes" / (task["id"] + ".patch")
        headers = [
            line
            for line in patch.read_text().splitlines()
            if line.startswith(("--- ", "+++ "))
        ]
        if headers != ["--- a/agent.py", "+++ b/agent.py"]:
            raise ValueError("Reviewed patches must modify only agent.py")
        relative = directory.relative_to(REPO)
        subprocess.run(
            ["git", "apply", "--check", "--directory", relative.as_posix(), str(patch)],
            cwd=REPO,
            check=True,
        )
        subprocess.run(
            ["git", "apply", "--directory", relative.as_posix(), str(patch)],
            cwd=REPO,
            check=True,
        )
    print("Applied three independent reviewed feature changes")


def test(root, directory, variant, kind, env):
    path = (
        root / "frozen/examples/live-agent/agent.py"
        if variant == "baseline"
        else root / "candidates" / variant / "agent.py"
    )
    label = variant + "-" + kind
    outcome = art.execute(
        [
            sys.executable,
            root / "frozen/examples/feature-queue/check.py",
            kind,
            path,
            directory / (label + ".json"),
        ],
        directory,
        label,
        env,
    )
    return {**outcome, **art.read(directory / (label + ".json"))}


def summarize_native(path):
    value = art.read(path)
    scenarios = value.get("run", {}).get("scenarios", [])
    comparison = value.get("comparison")
    return {
        "cases": len(scenarios),
        "passed": sum(s["passed"] for s in scenarios),
        "comparisonPassed": comparison.get("passed") if comparison else None,
        "failures": [
            {
                "scenario": s["scenario"]["id"],
                "messages": [e["message"] for e in s["evaluations"] if not e["passed"]],
            }
            for s in scenarios
            if not s["passed"]
        ],
        "findings": [
            {k: c[k] for k in ("scenarioId", "classification", "severity")}
            for c in (comparison or {}).get("changes", [])
        ],
        "report": value.get("report"),
    }


def run(root, mode, authorize=False):
    verify(root)
    if mode == "live" and not authorize:
        raise ValueError(
            "Live queue requires separately authorized --allow-live spending"
        )
    hashes = candidate_hashes(root)
    if mode == "live":
        prior = root / "offline/completion.json"
        if (
            not prior.exists()
            or not (root / "offline/seal.json").exists()
            or art.read(prior)["candidateHashes"] != hashes
        ):
            raise ValueError("Run the same candidates offline first")
    directory = root / mode
    if directory.exists():
        raise ValueError(
            "Attempt already exists; preserve results and budget, do not retry"
        )
    directory.mkdir()
    art.save(
        directory / "attempt.json",
        {
            "schema": 1,
            "mode": mode,
            "requestCap": 120 if mode == "live" else 0,
            "candidateHashes": hashes,
        },
    )
    shutil.copyfile(Path(__file__), directory / "runner.py")
    project = directory / "project"
    project.mkdir()
    env = dict(os.environ)
    env.pop("WRAITH_REQUEST_BUDGET", None)
    env["WRAITH_CHANGE_MODE"] = mode
    env["WRAITH_LIVE_VARIANT"] = "baseline"  # same prompt in every feature version
    if mode == "offline":
        env.pop("OPENAI_API_KEY", None)
    entry = str(root / "frozen/examples/feature-queue/entry.py") + ":evaluate"
    args = [
        root / EXE,
        "init",
        "--entrypoint",
        entry,
        "--runtime",
        sys.executable,
        "--mode",
        "live" if mode == "live" else "offline",
        "--cases",
        root / "frozen/examples/live-agent/cases.json",
    ]
    if mode == "live":
        args += [
            "--model",
            "gpt-4.1-mini-2025-04-14",
            "--require-env",
            "OPENAI_API_KEY",
        ]
    init = art.execute(args, directory, "init", env, workdir=project)
    if init["exit"] != 0:
        raise ValueError("Native init failed; preserve this attempt")
    project_files = {
        name: art.digest(project / name)
        for name in ("wraith.yaml", "wraith.project.json", "wraith_adapter.py")
    }
    results = []
    count = len(art.read(root / "frozen/examples/live-agent/cases.json"))
    for variant in ["baseline", *[t["id"] for t in tasks(root)]]:
        verify(root)
        if candidate_hashes(root) != hashes:
            raise ValueError("Candidate source changed during evaluation")
        if any(
            art.digest(project / name) != digest
            for name, digest in project_files.items()
        ):
            raise ValueError("Trusted project files changed")
        env["WRAITH_CHANGE_VARIANT"] = variant
        test_env = dict(env)
        test_env.pop("OPENAI_API_KEY", None)
        component = test(root, directory, variant, "components", test_env)
        acceptance = (
            test(root, directory, variant, variant, test_env)
            if variant != "baseline"
            else None
        )
        row = {
            "variant": variant,
            "components": component,
            "acceptance": acceptance,
            "native": None,
        }
        results.append(row)
        if mode == "live" and (
            component["exit"] != 0 or (acceptance and acceptance["exit"] != 0)
        ):
            row["skipReason"] = (
                "Application/acceptance checks failed before live spending"
            )
            if variant == "baseline":
                break
            continue
        args = ["baseline"] if variant == "baseline" else ["check"]
        if mode == "live":
            args += ["--allow-live"]
        if mode == "live" and variant == "baseline":
            args += ["--max-requests", "120"]
        args += ["--output", "json"]
        native = art.execute(
            [root / EXE, *args],
            directory,
            variant + "-wraith",
            env,
            timeout=1200,
            workdir=project,
        )
        row["native"] = {
            **native,
            **summarize_native(directory / (variant + "-wraith.stdout")),
        }
        art.save(directory / "progress.json", results)
        if native["exit"] not in (0, 1):
            break
        if variant == "baseline" and (
            native["exit"] != 0
            or row["native"]["cases"] != count
            or row["native"]["passed"] != count
        ):
            break
    budget = None
    marker = project / ".wraith/live-baseline-attempt.json"
    if mode == "live" and marker.exists():
        identity = art.read(marker)["budgetId"]
        budget = art.read(
            project / ".wraith/history" / identity / "request-budget.json"
        )
        if not 0 <= budget["used"] <= budget["limit"] == 120:
            raise ValueError("Shared request budget invariant violated")
    result = {
        "schema": 1,
        "mode": mode,
        "candidateHashes": hashes,
        "budget": budget,
        "results": results,
        "overlap": {
            "wraithGateOnly": sum(
                r["native"] is not None
                and r["native"]["exit"] == 1
                and r["components"]["passed"]
                for r in results[1:]
            ),
            "componentTestsOnly": sum(
                r["native"] is not None
                and r["native"]["exit"] == 0
                and not r["components"]["passed"]
                for r in results[1:]
            ),
            "bothFailed": sum(
                r["native"] is not None
                and r["native"]["exit"] == 1
                and not r["components"]["passed"]
                for r in results[1:]
            ),
            "bothPassed": sum(
                r["native"] is not None
                and r["native"]["exit"] == 0
                and r["components"]["passed"]
                for r in results[1:]
            ),
            "unmeasured": sum(
                r["native"] is None or r["native"]["exit"] not in (0, 1)
                for r in results[1:]
            ),
        },
    }
    art.save(directory / "completion.json", result)
    lines = [
        "# Feature queue: " + mode,
        "",
        "Independent changes; same frozen ten-case suite. Runtime is machine execution time, not human triage time.",
        "",
        "| Version | Component tests | Feature acceptance | Wraith cases | Gate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in results:
        n = row["native"]
        a = row["acceptance"]
        c = row["components"]
        v = row["variant"]
        lines.append(
            f"| {v} | {c['tests']} tests, {'pass' if c['passed'] else 'fail'} | {'n/a' if a is None else 'pass' if a['passed'] else 'fail'} | {str(n['passed']) + '/' + str(n['cases']) if n else 'skipped'} | {n['exit'] if n else 'skipped'} |"
        )
        # Links follow the table so Markdown remains valid.
    lines += ["", "## Evidence"]
    for row in results:
        v = row["variant"]
        lines += ["", f"- [{v} component results]({v}-components.json)"]
        if row["acceptance"]:
            lines += [f"- [{v} feature acceptance]({v}-{v}.json)"]
        if row["native"]:
            lines += [
                f"- [{v} native JSON]({v}-wraith.stdout)",
                f"- [{v} HTML]({art.relative_report_path(row['native']['report'], directory)})",
            ]
    lines += [
        "",
        "Shared provider requests: "
        + (
            str(budget["used"]) + "/120"
            if budget
            else "0 (recorded-model replay)"
            if mode == "offline"
            else "0 (live queue stopped before requests)"
        ),
        "",
        "Component/Wraith gate overlap: " + str(result["overlap"]),
        "",
        "Component failures and Wraith failures are separate observations. Review overlap and each useful catch manually; do not infer false-alarm rates from all-pass results. Recorded replay does not ask the model to reconsider changed results. A passing synthetic queue does not establish incremental value, production accuracy, adoption, paid demand, or human time saved.",
    ]
    (directory / "report.md").write_text("\n".join(lines) + "\n")
    art.save(directory / "seal.json", art.manifest(directory))
    verify(root)
    print(directory / "report.md")
    if any(r["native"] and r["native"]["exit"] not in (0, 1) for r in results):
        return 2
    return (
        0
        if len(results) == 4
        and all(
            r["components"]["passed"]
            and (r["acceptance"] is None or r["acceptance"]["passed"])
            and r["native"]
            and r["native"]["exit"] == 0
            and r["native"]["cases"] == count
            and r["native"]["passed"] == count
            for r in results
        )
        else 1
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO / ".wraith/feature-queue-validated"
    )
    parser.add_argument("--binary", type=Path, default=REPO / "target/debug" / EXE)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "apply-reviewed", "offline"):
        sub.add_parser(name)
    sub.add_parser("live").add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        prepare(root, args.binary.resolve())
        return 0
    if args.command == "apply-reviewed":
        apply_reviewed(root)
        return 0
    return run(root, args.command, getattr(args, "allow_live", False))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        sys.exit(2)
