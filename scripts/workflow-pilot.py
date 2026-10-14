#!/usr/bin/env python3
"""Evaluate a real feature from a green baseline, then measure workflow overhead."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
import statistics

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "examples/workflow-agent"
spec = importlib.util.spec_from_file_location(
    "maintained", REPO / "scripts/maintained-pilot.py"
)
maintained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintained)
art = maintained.artifacts
EXE = "wraith.exe" if os.name == "nt" else "wraith"


def execute(command, folder, label, env=None, cwd=None):
    start = time.monotonic()
    result = art.execute(command, folder, label, env, workdir=cwd)
    result["wallSeconds"] = round(time.monotonic() - start, 4)
    return result


def apply_patch(source, patch):
    headers = [
        s for s in patch.read_text().splitlines() if s.startswith(("--- ", "+++ "))
    ]
    if headers != ["--- a/src/smolagents/agents.py", "+++ b/src/smolagents/agents.py"]:
        raise ValueError("Patch must modify only the approved application module")
    subprocess.run(
        ["git", "apply", "--no-index", str(patch)],
        cwd=source,
        env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(source.parent)),
        check=True,
    )


def verify(root):
    state = art.read(root / "state.json")
    if state["schema"] != 1:
        raise ValueError("Unsupported workflow study schema")
    for name, expected in state["frozen"].items():
        if art.manifest(root / name) != expected:
            raise ValueError(f"Frozen study files changed: {name}")
    if maintained.application.packages(state["python"]) != state["packages"]:
        raise ValueError("Dependencies changed; use an explicit new study")
    for seal in root.glob("runs/*/seal.json"):
        actual = art.manifest(seal.parent)
        actual.pop("seal.json")
        if actual != art.read(seal):
            raise ValueError("Completed results changed")
    if (root / "completion.json").exists():
        saved = art.read(root / "completion.json")
        if art.manifest(root / "runs") != saved["runs"]:
            raise ValueError("Completed evidence disappeared or changed")
        if (
            "candidate" in saved
            and art.manifest(root / "candidate") != saved["candidate"]
        ):
            raise ValueError("Completed candidate changed")
    return state


def environment(root, source):
    env = maintained.environment(root, source)
    env["PYTHONPATH"] += os.pathsep + str(root / "frozen")
    return env


def prepare(root, binary, upstream, python, install, recorded=False):
    if root.exists():
        raise ValueError("Preserve existing experiments; select an explicit new root")
    root.mkdir(parents=True)
    shutil.copytree(
        FIXTURE, root / "frozen", ignore=shutil.ignore_patterns("__pycache__")
    )
    source = art.read(root / "frozen/source.json")
    if install:
        if upstream or python:
            raise ValueError("Choose --install or existing --upstream/--python")
        upstream = root / "upstream"
        subprocess.run(
            ["git", "clone", "--no-checkout", source["repository"], str(upstream)],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(upstream),
                "fetch",
                "--depth",
                "1",
                "origin",
                source["revision"],
            ],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "venv", str(root / "venv")], check=True)
        python = (
            root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "-r",
                str(root / "frozen/requirements.txt"),
            ],
            check=True,
        )
    if python is None or upstream is None:
        raise ValueError("Provide --install or --upstream and --python")
    python = python.absolute()  # Keep the venv interpreter symlink.
    runtime = root / "runtime"
    runtime.mkdir()
    shutil.copyfile(binary, runtime / EXE)
    (runtime / EXE).chmod(0o755)
    base = root / "base"
    base.mkdir()
    with (root / "source.tar").open("wb") as output:
        subprocess.run(
            ["git", "-C", str(upstream), "archive", source["revision"]],
            stdout=output,
            check=True,
        )
    with tarfile.open(root / "source.tar") as archive:
        archive.extractall(base, filter="data")
    apply_patch(base, root / "frozen/base.patch")
    setup = root / "setup"
    setup.mkdir()
    init = execute(
        [
            runtime / EXE,
            "init",
            "--entrypoint",
            str(root / "frozen/entrypoint.py") + ":evaluate",
            "--runtime",
            python,
            "--cases",
            root / "frozen/contracts.json",
            "--model",
            source["modelLabel"],
        ],
        setup,
        "init",
        cwd=base,
    )
    if init["exit"] != 0:
        raise ValueError("Init failed; preserve setup logs")
    state = {
        "schema": 1,
        "source": source,
        "python": str(python),
        "packages": maintained.application.packages(python),
        "frozenAt": datetime.now(timezone.utc).isoformat(),
        "scope": "recorded_reproduction"
        if recorded
        else "developer_selected_feature_after_contract_freeze",
    }
    env = environment(root, base)
    baseline = execute(
        [runtime / EXE, "--config", base / "wraith.yaml", "run", "--output", "json"],
        setup,
        "baseline",
        env,
    )
    upstream_result = maintained.tests(root, state, base, setup)
    acceptance = execute(
        [python, root / "frozen/acceptance.py"],
        setup,
        "new-feature-negative-control",
        env,
        cwd=base,
    )
    art.save(
        setup / "phases.json",
        {
            "init": init,
            "baseline": baseline,
            "upstream": upstream_result,
            "featureBeforeImplementation": acceptance,
        },
    )
    if baseline["exit"] != 0 or upstream_result["exit"] != 0 or acceptance["exit"] != 1:
        raise ValueError(
            "Require a green baseline/upstream tests and unmet feature acceptance; preserve logs"
        )
    state["frozen"] = {
        name: art.manifest(root / name)
        for name in ("base", "frozen", "runtime", "setup")
    }
    art.save(root / "state.json", state)
    # Only this candidate is editable, after the suite and acceptance freeze.
    shutil.copytree(base, root / "candidate")
    print(root / "candidate/src/smolagents/agents.py")


def validate_candidate(root, state):
    current, original = art.manifest(root / "candidate"), state["frozen"]["base"]
    allowed = art.read(root / "frozen/task.json")["files"]
    if set(current) != set(original) or any(
        v != original[k] for k, v in current.items() if k not in allowed
    ):
        raise ValueError("Only the returned candidate application module can change")
    return current


def evaluate(root, state):
    fingerprint = validate_candidate(root, state)
    folder = root / "runs" / ("feature-" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True)
    snapshot = folder / "source"
    shutil.copytree(root / "candidate", snapshot)
    env = environment(root, snapshot)
    phases = {
        "featureAcceptance": execute(
            [state["python"], root / "frozen/acceptance.py"],
            folder,
            "acceptance",
            env,
            cwd=snapshot,
        ),
        "upstream": maintained.tests(root, state, snapshot, folder),
    }
    phases["wraithRun"] = execute(
        [
            root / "runtime" / EXE,
            "--config",
            snapshot / "wraith.yaml",
            "run",
            "--output",
            "json",
        ],
        folder,
        "candidate",
        env,
    )
    shutil.copyfile(root / "setup/baseline.stdout", folder / "baseline.json")
    shutil.copyfile(folder / "candidate.stdout", folder / "candidate.json")
    phases["comparison"] = execute(
        [
            root / "runtime" / EXE,
            "compare",
            folder / "baseline.json",
            folder / "candidate.json",
            "--policy",
            root / "base/wraith.yaml",
            "--html",
            folder / "report.html",
            "--output",
            "json",
        ],
        folder,
        "comparison",
        env,
    )
    if art.manifest(snapshot) != fingerprint:
        raise ValueError("Evaluation changed its source; attempt remains incomplete")
    result = {
        "schema": 1,
        "phases": phases,
        "source": fingerprint,
        "comparison": art.read(folder / "comparison.stdout"),
        "upstream": maintained.junit(folder / "upstream.xml"),
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    art.save(folder / "result.json", result)
    art.save(folder / "seal.json", art.manifest(folder))
    print(json.dumps({"evidence": str(folder), "phases": phases}, indent=2))
    return max(phase["exit"] for phase in phases.values())


def benchmark(root, state, binary, repeats):
    fingerprint = validate_candidate(root, state)
    completed = sorted(
        root.glob("runs/feature-*/result.json"),
        key=lambda p: art.read(p)["completedAt"],
    )
    if (
        not completed
        or art.read(completed[-1])["source"] != fingerprint
        or any(p["exit"] for p in art.read(completed[-1])["phases"].values())
    ):
        raise ValueError("Require an evaluated passing feature before benchmarking")
    folder = root / "runs" / ("workflow-" + uuid.uuid4().hex[:12])
    folder.mkdir()
    runtime = folder / EXE
    shutil.copyfile(binary, runtime)
    runtime.chmod(0o755)
    candidate = folder / "source"
    shutil.copytree(root / "candidate", candidate)
    env = environment(root, candidate)
    rows = []
    for repeat in range(repeats):
        # Alternate order; descriptive machine timings, not a statistical study.
        for jobs in (1, 4) if repeat % 2 == 0 else (4, 1):
            trial = folder / f"repeat-{repeat + 1}-jobs-{jobs}"
            trial.mkdir()
            phase = execute(
                [
                    runtime,
                    "--config",
                    candidate / "wraith.yaml",
                    "ci",
                    "check",
                    "--base-config",
                    root / "base/wraith.yaml",
                    "--jobs",
                    str(jobs),
                    "--artifacts",
                    trial / "native",
                    "--output",
                    "json",
                ],
                trial,
                "ci",
                env,
            )
            if phase["exit"] != 0:
                raise ValueError(
                    "Unexpected integration failure; preserve incomplete benchmark"
                )
            result = art.read(trial / "ci.stdout")
            rows.append(
                {
                    "repeat": repeat + 1,
                    "jobs": jobs,
                    "wallSeconds": phase["wallSeconds"],
                    "exit": phase["exit"],
                    "native": result,
                }
            )
    upstream = maintained.tests(root, state, candidate, folder)
    # Restore previously reproduced upstream defects as an explicit calibration,
    # never as a naturally introduced feature regression.
    control = folder / "calibration-source"
    shutil.copytree(root / "base", control)
    subprocess.run(
        ["git", "apply", "--reverse", "--no-index", str(root / "frozen/base.patch")],
        cwd=control,
        env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(control.parent)),
        check=True,
    )
    calibration = folder / "calibration"
    calibration.mkdir()
    control_phase = execute(
        [
            runtime,
            "--config",
            control / "wraith.yaml",
            "ci",
            "check",
            "--base-config",
            root / "base/wraith.yaml",
            "--jobs",
            "4",
            "--artifacts",
            calibration / "native",
            "--output",
            "json",
        ],
        calibration,
        "ci",
        env,
    )
    control_tests = maintained.tests(root, state, control, calibration)
    if (
        upstream["exit"] != 0
        or control_phase["exit"] != 1
        or control_tests["exit"] != 0
    ):
        raise ValueError("Unexpected calibration or upstream-test outcome")
    if art.manifest(candidate) != fingerprint:
        raise ValueError("Benchmark modified feature source")
    result = {
        "schema": 1,
        "source": fingerprint,
        "binarySha256": art.digest(runtime),
        "rows": rows,
        "upstream": upstream,
        "upstreamCounts": maintained.junit(folder / "upstream.xml"),
        "calibration": {
            "category": "restored_known_upstream_defects",
            "phase": control_phase,
            "upstream": control_tests,
            "native": art.read(calibration / "ci.stdout"),
        },
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    art.save(folder / "result.json", result)
    art.save(folder / "seal.json", art.manifest(folder))
    print(folder / "result.json")


def report(root, state):
    paths = sorted(
        root.glob("runs/workflow-*/result.json"),
        key=lambda p: art.read(p)["completedAt"],
    )
    if not paths:
        raise ValueError("No completed workflow benchmark")
    measured = art.read(paths[-1])
    rows = measured["rows"]
    medians = {
        str(jobs): statistics.median(
            r["wallSeconds"] for r in rows if r["jobs"] == jobs
        )
        for jobs in (1, 4)
    }
    upstream = measured["upstream"]
    upstream_wall = (
        datetime.fromisoformat(upstream["endedAt"])
        - datetime.fromisoformat(upstream["startedAt"])
    ).total_seconds()
    feature = art.read(
        max(
            root.glob("runs/feature-*/result.json"),
            key=lambda p: art.read(p)["completedAt"],
        )
    )
    summary = {
        "schema": 1,
        "revision": state["source"]["revision"],
        "providerRequests": 0,
        "scope": state["scope"],
        "contractsFrozenAt": state["frozenAt"],
        "baselineModuleSha256": state["frozen"]["base"]["src/smolagents/agents.py"],
        "featureModuleSha256": feature["source"]["src/smolagents/agents.py"],
        "wraithBinarySha256": measured["binarySha256"],
        "incompleteFeatureAttempts": len(list(root.glob("runs/feature-*")))
        - len(list(root.glob("runs/feature-*/result.json"))),
        "scenarios": len(art.read(root / "frozen/contracts.json")),
        "contractSha256": state["frozen"]["frozen"]["contracts.json"],
        "feature": "current action visible to final-answer critic (upstream request #1374)",
        "featureAcceptanceExit": feature["phases"]["featureAcceptance"]["exit"],
        "newFeatureFailureEntries": len(
            [c for c in feature["comparison"]["changes"] if c["severity"] == "failure"]
        ),
        "reviewedUsefulFeatureCatches": 0
        if feature["phases"]["comparison"]["exit"] == 0
        else None,
        "selectedUpstreamTests": measured["upstreamCounts"],
        "selectedUpstreamWallSeconds": round(upstream_wall, 4),
        "comparisons": len(rows),
        "unexpectedComparisonFailures": sum(r["exit"] != 0 for r in rows),
        "medianCiSecondsByJobs": medians,
        "serialToParallelSpeedup": round(medians["1"] / medians["4"], 3),
        "calibration": {
            "category": measured["calibration"]["category"],
            "wraithExit": measured["calibration"]["phase"]["exit"],
            "upstreamExit": measured["calibration"]["upstream"]["exit"],
        },
        "timingScope": "Warm dependencies; external CLI wall time for base plus candidate and saved evidence. Existing-test timing covers one candidate test subset. No human authoring, review, installation, or CI queue time.",
        "limits": [
            "One developer-selected feature, not independent adoption.",
            "Repeated deterministic comparisons are mechanical stability observations, not a false-positive rate estimate.",
            "Calibration restores known defects; it is not prospective regression discovery.",
            "No buyer demand, human time savings, or ROI measured.",
        ],
    }
    art.save(root / "assessment.json", summary)
    (root / "report.md").write_text(
        "# Workflow integration study\n\n"
        + f"{summary['scenarios']} frozen scenarios; feature acceptance exit {summary['featureAcceptanceExit']}; {measured['upstreamCounts']['passed']} existing tests passed ({measured['upstreamCounts']['skipped']} skipped). Feature comparison produced {summary['newFeatureFailureEntries']} failure entries; findings need review before counting useful catches.\n\n"
        + f"{len(rows)} completed comparisons; {summary['unexpectedComparisonFailures']} unexpected gate failures. Median base+candidate CI time: {medians['1']:.2f}s sequential, {medians['4']:.2f}s with four jobs ({summary['serialToParallelSpeedup']:.2f}× in this environment). Selected upstream tests alone: {upstream_wall:.2f}s.\n\n"
        + "Known-defect restoration fails Wraith while selected ordinary upstream tests pass. This is calibration, not a newly discovered feature regression.\n\n"
        + summary["timingScope"]
        + "\n\n"
        + "\n".join(summary["limits"])
        + f"\n\n[Passed CI comparison]({paths[-1].parent.relative_to(root).as_posix()}/repeat-1-jobs-4/native/report.html) · [Calibration failure]({paths[-1].parent.relative_to(root).as_posix()}/calibration/native/report.html)\n"
        + "\n"
    )
    return summary


def finish(root, state):
    measured = art.read(
        max(
            root.glob("runs/workflow-*/result.json"),
            key=lambda p: art.read(p)["completedAt"],
        )
    )
    feature = art.read(
        max(
            root.glob("runs/feature-*/result.json"),
            key=lambda p: art.read(p)["completedAt"],
        )
    )
    current = validate_candidate(root, state)
    if measured["source"] != current or feature["source"] != current:
        raise ValueError("Candidate changed after its evaluated benchmark")
    if any(phase["exit"] for phase in feature["phases"].values()):
        raise ValueError("Latest feature evaluation has unresolved failures")
    summary = report(root, state)
    if summary["unexpectedComparisonFailures"]:
        raise ValueError("Study has unresolved comparison failures")
    art.save(
        root / "completion.json",
        {"schema": 1, "runs": art.manifest(root / "runs"), "candidate": current},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO / ".wraith/workflow-value")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "reproduce"):
        setup = sub.add_parser(name)
        setup.add_argument("--binary", type=Path, default=REPO / "target/debug" / EXE)
        setup.add_argument("--upstream", type=Path)
        setup.add_argument("--python", type=Path)
        setup.add_argument("--install", action="store_true")
        if name == "reproduce":
            setup.add_argument("--repeats", type=int, choices=range(1, 11), default=3)
    sub.add_parser("evaluate")
    sub.add_parser("verify")
    bench = sub.add_parser("benchmark")
    bench.add_argument("--binary", type=Path, required=True)
    bench.add_argument("--repeats", type=int, choices=range(1, 11), default=3)
    sub.add_parser("report")
    sub.add_parser("finish")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command in ("prepare", "reproduce"):
        prepare(
            root,
            args.binary.resolve(),
            args.upstream,
            args.python,
            args.install,
            recorded=args.command == "reproduce",
        )
        if args.command == "reproduce":
            state = verify(root)
            apply_patch(root / "candidate", root / "frozen/feature.patch")
            if evaluate(root, state) != 0:
                raise ValueError("Feature reproduction did not pass")
            verify(root)
            benchmark(root, state, args.binary.resolve(), args.repeats)
            verify(root)
            finish(root, state)
        return 0
    state = verify(root)
    if args.command == "verify":
        print("Frozen source, contracts, dependencies, and evidence verified")
        return 0
    if args.command == "report":
        report(root, state)
        print(root / "report.md")
        return 0
    if (root / "completion.json").exists():
        raise ValueError("Study complete; use an explicit new root")
    if args.command == "benchmark":
        benchmark(root, state, args.binary.resolve(), args.repeats)
        report(root, state)
        return 0
    if args.command == "finish":
        finish(root, state)
        print(root / "report.md")
        return 0
    return evaluate(root, state)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
