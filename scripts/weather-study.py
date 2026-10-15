#!/usr/bin/env python3
"""Compare Wraith with conventional tests on the same real weather workflow."""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "examples/weather-workflow"
spec = importlib.util.spec_from_file_location(
    "art", REPO / "scripts/historical-pilot.py"
)
art = importlib.util.module_from_spec(spec)
spec.loader.exec_module(art)
SOURCE = {
    "repository": "https://github.com/pydantic/pydantic-ai.git",
    "revision": "0ba01f92be3fc361f89970502cd6e7dd3611aec3",
    "path": "examples/pydantic_ai_examples/weather_agent.py",
    "license": "MIT",
}
EXE = "wraith.exe" if os.name == "nt" else "wraith"


def env(root):
    return dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            map(str, [root / "frozen/offline", root / "frozen"])
        ),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONOPTIMIZE="0",
        LOGFIRE_SEND_TO_LOGFIRE="false",
        LOGFIRE_CONSOLE="false",
        OPENAI_API_KEY="offline-placeholder-never-sent",
    )


def execute(root, command, folder, label, source):
    start = time.monotonic()
    phase = art.execute(command, folder, label, env(root), workdir=source)
    phase["wallSeconds"] = round(time.monotonic() - start, 4)
    return phase


def verify(root):
    state = art.read(root / "state.json")
    if state["schema"] != 1:
        raise ValueError("Unsupported study schema")
    for name, expected in state["frozen"].items():
        if art.manifest(root / name) != expected:
            raise ValueError(
                "Frozen source, requirements, runtime or setup changed: " + name
            )
    packages = subprocess.check_output(
        [state["python"], "-m", "pip", "freeze"], text=True
    ).splitlines()
    if packages != state["packages"]:
        raise ValueError("Dependencies changed; preserve this study and use a new root")
    for result in root.glob("runs/*/result.json"):
        seal = result.parent / "seal.json"
        actual = art.manifest(result.parent)
        actual.pop("seal.json", None)
        if not seal.exists() or actual != art.read(seal):
            raise ValueError("Completed evidence changed")
    if (root / "completion.json").exists():
        completed = art.read(root / "completion.json")
        if (
            art.manifest(root / "runs") != completed["runs"]
            or art.manifest(root / "candidates") != completed["candidates"]
        ):
            raise ValueError("Completed evidence or candidates changed or disappeared")
    return state


def require_binary(binary):
    probe = subprocess.run(
        [binary, "ci", "check", "--help"], capture_output=True, text=True, timeout=30
    )
    if probe.returncode:
        raise ValueError("Build a current binary with native ci check first")


def prepare(root, binary, python, upstream):
    if root.exists():
        raise ValueError("Preserve prior studies; choose an explicit new root")
    require_binary(binary)
    if (
        subprocess.check_output(
            ["git", "-C", upstream, "rev-parse", "HEAD"], text=True
        ).strip()
        != SOURCE["revision"]
    ):
        raise ValueError(
            "Upstream clone must be at the pinned revision; existing checkouts are never reset"
        )
    root.mkdir(parents=True)
    shutil.copytree(
        FIXTURE, root / "frozen", ignore=shutil.ignore_patterns("__pycache__")
    )
    (root / "runtime").mkdir()
    shutil.copyfile(binary, root / "runtime" / EXE)
    (root / "runtime" / EXE).chmod(0o755)
    base = root / "base"
    base.mkdir()
    original = subprocess.check_output(
        ["git", "-C", upstream, "show", SOURCE["revision"] + ":" + SOURCE["path"]]
    )
    (base / "weather_agent.py").write_bytes(original)
    setup = root / "setup"
    setup.mkdir()
    init = execute(
        root,
        [
            root / "runtime" / EXE,
            "init",
            "--entrypoint",
            str(root / "frozen/adapter.py") + ":evaluate",
            "--runtime",
            python,
            "--cases",
            root / "frozen/cases.json",
            "--model",
            "scripted-offline-model",
        ],
        setup,
        "init",
        base,
    )
    baseline = execute(
        root,
        [
            root / "runtime" / EXE,
            "--config",
            base / "wraith.yaml",
            "run",
            "--jobs",
            "4",
            "--output",
            "json",
        ],
        setup,
        "baseline",
        base,
    )
    ordinary = execute(
        root,
        [python, root / "frozen/ordinary.py", setup / "ordinary.json"],
        setup,
        "ordinary",
        base,
    )
    negatives = {
        task: execute(
            root,
            [python, root / "frozen/acceptance.py", task],
            setup,
            "negative-" + task,
            base,
        )
        for task in ("retries", "units")
    }
    art.save(
        setup / "phases.json",
        {
            "init": init,
            "baseline": baseline,
            "ordinary": ordinary,
            "featureNegativeControls": negatives,
        },
    )
    if any(p["exit"] for p in (init, baseline, ordinary)) or any(
        p["exit"] != 1 for p in negatives.values()
    ):
        raise ValueError(
            "Require a green baseline and unmet feature acceptance; preserve setup logs"
        )
    packages = subprocess.check_output(
        [python, "-m", "pip", "freeze"], text=True
    ).splitlines()
    state = {
        "schema": 1,
        "scope": "developer_selected_application_features_against_equivalent_tests",
        "source": SOURCE,
        "python": str(python),
        "packages": packages,
        "frozenAt": datetime.now(timezone.utc).isoformat(),
        "frozen": {
            name: art.manifest(root / name)
            for name in ("base", "frozen", "runtime", "setup")
        },
    }
    art.save(root / "state.json", state)
    for task in ("retries", "units"):
        shutil.copytree(base, root / "candidates" / task)
        print(root / "candidates" / task / "weather_agent.py")


def candidate(root, state, task):
    source = root / "candidates" / task
    observed, original = art.manifest(source), state["frozen"]["base"]
    if set(observed) != set(original) or any(
        observed[n] != original[n] for n in original if n != "weather_agent.py"
    ):
        raise ValueError("Only the returned weather application module may change")
    return source, observed


def evaluate(root, state, task):
    if (root / "completion.json").exists():
        raise ValueError("Study complete; use a new explicit experiment")
    source, fingerprint = candidate(root, state, task)
    folder = root / "runs" / (task + "-" + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    snapshot = folder / "source"
    shutil.copytree(source, snapshot)
    phases = {}
    for label, directory in (
        ("ordinary-base", root / "base"),
        ("ordinary-candidate", snapshot),
    ):
        phases[label] = execute(
            root,
            [state["python"], root / "frozen/ordinary.py", folder / (label + ".json")],
            folder,
            label,
            directory,
        )
    phases["featureAcceptance"] = execute(
        root,
        [state["python"], root / "frozen/acceptance.py", task],
        folder,
        "acceptance",
        snapshot,
    )
    phases["wraith"] = execute(
        root,
        [
            root / "runtime" / EXE,
            "--config",
            snapshot / "wraith.yaml",
            "ci",
            "check",
            "--base-config",
            root / "base/wraith.yaml",
            "--jobs",
            "4",
            "--artifacts",
            folder / "native",
            "--output",
            "json",
        ],
        folder,
        "ci",
        snapshot,
    )
    if art.manifest(snapshot) != fingerprint:
        raise ValueError("Execution changed source; attempt remains incomplete")
    result = {
        "task": task,
        "source": fingerprint,
        "phases": phases,
        "ordinary": art.read(folder / "ordinary-candidate.json"),
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    art.save(folder / "result.json", result)
    art.save(folder / "seal.json", art.manifest(folder))
    print(
        json.dumps(
            {
                "task": task,
                "exits": {n: p["exit"] for n, p in phases.items()},
                "evidence": str(folder),
            }
        )
    )


def calibration(root, state):
    if (root / "completion.json").exists() or list(root.glob("runs/calibration-*")):
        raise ValueError(
            "Calibration already attempted or study complete; preserve evidence"
        )
    requirements = art.read(root / "frozen/requirements.json")
    definitions = {
        "coordinates": (
            "params={'lat': lat, 'lng': lng}",
            "params={'lat': lng, 'lng': lat}",
            sorted(c["id"] for c in requirements if c["expected"]["available"]),
        ),
        "status": (
            "    temp_response.raise_for_status()\n",
            "",
            ["forecast-unavailable"],
        ),
    }
    for name, (old, new, expected) in definitions.items():
        folder = root / "runs" / ("calibration-" + name)
        folder.mkdir(parents=True)
        source = folder / "source"
        shutil.copytree(root / "base", source)
        application = source / "weather_agent.py"
        text = application.read_text()
        if text.count(old) != 1:
            raise ValueError("Calibration patch no longer matches; preserve attempt")
        application.write_text(text.replace(old, new))
        before = art.manifest(source)
        ordinary = execute(
            root,
            [state["python"], root / "frozen/ordinary.py", folder / "ordinary.json"],
            folder,
            "ordinary",
            source,
        )
        gate = execute(
            root,
            [
                root / "runtime" / EXE,
                "--config",
                source / "wraith.yaml",
                "ci",
                "check",
                "--base-config",
                root / "base/wraith.yaml",
                "--jobs",
                "4",
                "--artifacts",
                folder / "native",
                "--output",
                "json",
            ],
            folder,
            "ci",
            source,
        )
        if art.manifest(source) != before:
            raise ValueError("Calibration execution modified source")
        observed = art.read(folder / "ordinary.json")
        native = folder / "native"
        native_result = (
            art.read(native / "ci.json") if (native / "ci.json").exists() else {}
        )
        failed = (
            sorted(
                {
                    c["scenarioId"]
                    for c in art.read(native / "comparison.json")["changes"]
                    if c["severity"] == "failure"
                }
            )
            if (native / "comparison.json").exists()
            else []
        )
        result = {
            "category": "seeded_calibration_not_discovery",
            "control": name,
            "ordinary": ordinary,
            "wraith": gate,
            "source": before,
            "ordinaryFailedCases": sorted(observed["failedCases"]),
            "wraithFailedCases": failed,
            "expectedCases": expected,
            "validated": ordinary["exit"] == 1
            and gate["exit"] == 1
            and native_result.get("baselinePassed") is True
            and not observed["executionErrors"]
            and sorted(observed["failedCases"]) == expected == failed,
        }
        art.save(folder / "result.json", result)
        art.save(folder / "seal.json", art.manifest(folder))
        if not result["validated"]:
            raise ValueError(
                "Calibration disagrees; preserved evidence needs investigation"
            )
        print(
            name, "both detect", len(failed), "failing cases; seeded calibration only"
        )


def finish(root, state):
    if (root / "completion.json").exists():
        raise ValueError("Study already completed")
    rows = []
    for task in ("retries", "units"):
        paths = sorted(
            root.glob("runs/" + task + "-*/result.json"),
            key=lambda p: art.read(p)["completedAt"],
        )
        if not paths:
            raise ValueError("Both features must be evaluated before completion")
        result = art.read(paths[-1])
        if result["source"] != candidate(root, state, task)[1] or any(
            p["exit"] for p in result["phases"].values()
        ):
            raise ValueError(
                "Latest feature has unresolved failures or changed since evaluation"
            )
        rows.append(result)
    controls = [
        art.read(root / "runs" / ("calibration-" + n) / "result.json")
        for n in ("coordinates", "status")
    ]
    if not all(c["validated"] for c in controls):
        raise ValueError(
            "Both labeled calibration controls must pass before completion"
        )
    summary = {
        "schema": 1,
        "scope": state["scope"],
        "source": SOURCE,
        "providerRequests": 0,
        "requirements": len(art.read(root / "frozen/requirements.json")),
        "requirementsSha256": state["frozen"]["frozen"]["requirements.json"],
        "tasks": [
            {
                "id": r["task"],
                "featureAcceptanceExit": r["phases"]["featureAcceptance"]["exit"],
                "ordinaryBaseAndCandidateSeconds": round(
                    sum(
                        r["phases"][n]["wallSeconds"]
                        for n in ("ordinary-base", "ordinary-candidate")
                    ),
                    4,
                ),
                "wraithBaseAndCandidateSeconds": r["phases"]["wraith"]["wallSeconds"],
                "sourceSha256": r["source"]["weather_agent.py"],
            }
            for r in rows
        ],
        "featureAttempts": [
            {
                "task": r["task"],
                "acceptanceExit": r["phases"]["featureAcceptance"]["exit"],
                "ordinaryExit": r["phases"]["ordinary-candidate"]["exit"],
                "wraithExit": r["phases"]["wraith"]["exit"],
            }
            for p in root.glob("runs/*/result.json")
            if (r := art.read(p)).get("task")
        ],
        "calibration": [
            {
                k: c[k]
                for k in (
                    "control",
                    "category",
                    "ordinaryFailedCases",
                    "wraithFailedCases",
                    "validated",
                )
            }
            for c in controls
        ],
        "limits": [
            "Equivalent tests share the requirements and observation adapter; oracle independence is not measured.",
            "Conventional tests use one process per version; Wraith isolates each scenario with four jobs.",
            "This is a developer-selected change to an upstream example, not independent adoption or an upstream contribution.",
            "Offline scripted model and HTTP; no live model quality, human time savings or paid demand measured.",
        ],
    }
    art.save(root / "assessment.json", summary)
    art.save(
        root / "completion.json",
        {
            "runs": art.manifest(root / "runs"),
            "candidates": art.manifest(root / "candidates"),
        },
    )
    print(root / "assessment.json")


def reproduce(root, binary, python, upstream, install):
    if root.exists():
        raise ValueError("Preserve prior studies; choose an explicit new root")
    require_binary(binary)
    if install:
        if python is not None or upstream is not None:
            raise ValueError("Use --install or existing --python/--upstream")
        bootstrap = root.with_name(root.name + "-bootstrap")
        if bootstrap.exists():
            raise ValueError("Preserve existing bootstrap; choose a new explicit root")
        bootstrap.mkdir(parents=True)
        upstream = bootstrap / "upstream"
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                SOURCE["repository"],
                upstream,
            ],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                upstream,
                "sparse-checkout",
                "set",
                "examples/pydantic_ai_examples",
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", upstream, "checkout", "--detach", SOURCE["revision"]],
            check=True,
        )
        subprocess.run([sys.executable, "-m", "venv", bootstrap / "venv"], check=True)
        python = (
            bootstrap
            / "venv"
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        subprocess.run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "-r",
                FIXTURE / "dependencies.txt",
            ],
            check=True,
        )
    if python is None or upstream is None:
        raise ValueError("Provide --install or both --python and --upstream")
    prepare(root, binary, python.absolute(), upstream.resolve())
    state = verify(root)
    state["scope"] = "recorded_reproduction_of_weather_feature_study"
    art.save(root / "state.json", state)
    for task in ("retries", "units"):
        patch = root / "frozen" / (task + ".patch")
        headers = [
            line
            for line in patch.read_text().splitlines()
            if line.startswith(("--- ", "+++ "))
        ]
        if headers != ["--- a/weather_agent.py", "+++ b/weather_agent.py"]:
            raise ValueError(
                "Recorded patch may change only the approved weather module"
            )
        directory = root / "candidates" / task
        subprocess.run(
            ["git", "apply", "--no-index", str(patch)],
            cwd=directory,
            env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(directory.parent)),
            check=True,
        )
        evaluate(root, state, task)
        verify(root)
    calibration(root, state)
    verify(root)
    finish(root, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("prepare")
    for flag in ("binary", "python", "upstream"):
        setup.add_argument("--" + flag, type=Path, required=True)
    replay = sub.add_parser("reproduce")
    replay.add_argument("--binary", type=Path, default=REPO / "target/debug" / EXE)
    replay.add_argument("--python", type=Path)
    replay.add_argument("--upstream", type=Path)
    replay.add_argument("--install", action="store_true")
    task = sub.add_parser("evaluate")
    task.add_argument("task", choices=("retries", "units"))
    for name in ("verify", "finish", "calibrate"):
        sub.add_parser(name)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "reproduce":
        reproduce(root, args.binary.resolve(), args.python, args.upstream, args.install)
    elif args.command == "prepare":
        prepare(
            root, args.binary.resolve(), args.python.absolute(), args.upstream.resolve()
        )
    else:
        state = verify(root)
        if args.command == "evaluate":
            evaluate(root, state, args.task)
        elif args.command == "calibrate":
            calibration(root, state)
        elif args.command == "finish":
            finish(root, state)
        else:
            print("Frozen requirements, source, dependencies, and evidence verified")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
