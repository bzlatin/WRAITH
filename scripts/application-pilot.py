#!/usr/bin/env python3
"""Operate a finite prospective pilot on pinned LLM application source, offline."""

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
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "examples/application-pilot"
spec = importlib.util.spec_from_file_location(
    "pilot_artifacts", REPO / "scripts/historical-pilot.py"
)
artifacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifacts)


def packages(python):
    code = 'import importlib.metadata,json; print(json.dumps(sorted((d.metadata["Name"].lower().replace("_","-"),d.version) for d in importlib.metadata.distributions())))'
    return json.loads(subprocess.check_output([str(python), "-c", code], text=True))


def environment(root, source):
    return dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            map(str, [root / "frozen/offline", source, root / "frozen"])
        ),
        WRAITH_APP_SOURCE=str(source),
        LLM_LOAD_PLUGINS="llm-echo",
        LLM_USER_PATH=str(root / "unused-user-directory"),
        OPENAI_API_KEY="pilot-offline",
        PYTEST_OPENAI_API_KEY="pilot-offline",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_ADDOPTS="",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )


def upstream_tests(root, state, source, folder):
    # Test files and snapshots are kept intact. Exclude recorded provider tests.
    return artifacts.execute(
        [
            state["python"],
            "-m",
            "pytest",
            "-p",
            "pytest_asyncio.plugin",
            "-p",
            "pytest_httpx2",
            "-p",
            "syrupy",
            "-p",
            "no:cacheprovider",
            *[source / name for name in state["source"]["tests"]],
            "-m",
            state["source"]["markers"],
            "-q",
            f"--junitxml={folder / 'upstream.xml'}",
        ],
        folder,
        "upstream-tests",
        environment(root, source),
        workdir=source,
    )


def verify(root):
    state = artifacts.read(root / "campaign.json")
    if state["schema"] != 1:
        raise ValueError("Unsupported application pilot schema")
    if artifacts.digest(Path(state["binary"])) != state["binarySha256"]:
        raise ValueError("Binary changed; use an explicit new campaign")
    if packages(state["python"]) != state["packages"]:
        raise ValueError("Dependency versions changed; use an explicit new campaign")
    for name, expected in state["frozen"].items():
        if artifacts.manifest(root / name) != expected:
            raise ValueError(f"Frozen inputs changed: {name}")
    for name, expected in state["projectFiles"].items():
        if artifacts.digest(root / "project" / name) != expected:
            raise ValueError(f"Trusted project policy/adapter changed: {name}")
    if (
        artifacts.digest(root / "project/.wraith/baseline.json")
        != state["baselinePointerSha256"]
    ):
        raise ValueError("Accepted baseline pointer changed")
    for evidence in root.glob("**/evidence.json"):
        observed = artifacts.manifest(evidence.parent)
        observed.pop("evidence.json", None)
        if observed != artifacts.read(evidence):
            raise ValueError(f"Immutable evidence changed: {evidence.parent}")
    for path, expected in state["baselineHistory"].items():
        if artifacts.digest(Path(path)) != expected:
            raise ValueError("Accepted baseline history changed")
    completion = root / "completion.json"
    if completion.exists():
        saved = artifacts.read(completion)
        if saved["schema"] != 1:
            raise ValueError("Unsupported completion schema")
        if (
            artifacts.manifest(root / "project/.wraith/history")
            != saved["nativeHistory"]
        ):
            raise ValueError("Completed native history changed")
    return state


def prepare(root, binary, install):
    if (root / "campaign.json").exists():
        verify(root)
        return
    start = time.monotonic()
    source = artifacts.read(FIXTURE / "source.json")
    root.mkdir(parents=True, exist_ok=True)
    upstream = root / "upstream"
    python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if install:
        if not upstream.exists():
            subprocess.run(
                ["git", "clone", "--no-checkout", source["repository"], str(upstream)],
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(upstream),
                    "checkout",
                    "--detach",
                    source["revision"],
                ],
                check=True,
            )
        if not python.exists():
            subprocess.run(
                [sys.executable, "-m", "venv", str(root / "venv")], check=True
            )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "-r",
                str(FIXTURE / "requirements.txt"),
            ],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-build-isolation",
                "-e",
                str(upstream),
            ],
            check=True,
        )
    actual = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != source["revision"]:
        raise ValueError(
            "Existing upstream checkout has a different revision; refusing to reset it"
        )
    if not python.exists():
        raise ValueError("Run prepare --install to create the isolated environment")
    base = root / "base"
    base.mkdir(exist_ok=False)
    archive = root / "source.tar"
    with archive.open("wb") as stream:
        subprocess.run(
            ["git", "-C", str(upstream), "archive", source["revision"]],
            stdout=stream,
            check=True,
        )
    with tarfile.open(archive) as stream:
        stream.extractall(base, filter="data")
    shutil.copytree(
        FIXTURE, root / "frozen", ignore=shutil.ignore_patterns("__pycache__")
    )
    project = root / "project"
    project.mkdir(exist_ok=False)
    state = {
        "schema": 1,
        "source": source,
        "python": str(python),
        "binary": str(binary),
        "binarySha256": artifacts.digest(binary),
        "packages": packages(python),
        "preparedAt": datetime.now(timezone.utc).isoformat(),
    }
    phases = {}
    phases["init"] = artifacts.execute(
        [
            binary,
            "init",
            "--entrypoint",
            str(root / "frozen/entrypoint.py") + ":evaluate",
            "--language",
            "python",
            "--runtime",
            python,
            "--model",
            "echo-offline-fixture",
        ],
        project,
        "init",
    )
    if phases["init"]["exit"] != 0:
        raise ValueError("Native init failed; inspect project/init.stderr")
    config = artifacts.read(project / "wraith.yaml")
    config["tests"] = artifacts.read(root / "frozen/contracts.json")
    artifacts.save(project / "wraith.yaml", config)
    env = environment(root, base)
    phases["doctor"] = artifacts.execute([binary, "doctor"], project, "doctor", env)
    phases["upstreamTests"] = upstream_tests(root, state, base, project)
    phases["baseline"] = artifacts.execute(
        [binary, "baseline", "--output", "json"], project, "baseline", env
    )
    if any(phase["exit"] != 0 for phase in phases.values()):
        artifacts.save(
            root / "setup-failure.json", {"phases": phases, "accepted": False}
        )
        raise ValueError(
            "Setup did not pass; preserve this root and inspect logs before starting a new campaign"
        )
    result = artifacts.read(project / "baseline.stdout")
    state.update(
        phases=phases,
        baselineResult=result,
        frozen={name: artifacts.manifest(root / name) for name in ("base", "frozen")},
        projectFiles={
            name: artifacts.digest(project / name)
            for name in ("wraith.yaml", "wraith.project.json", "wraith_adapter.py")
        },
        baselinePointerSha256=artifacts.digest(project / ".wraith/baseline.json"),
        baselineHistory={
            str(path): artifacts.digest(path)
            for path in (project / ".wraith/history").rglob("*")
            if path.is_file()
        },
        measuredPreparationSeconds=round(time.monotonic() - start, 3),
        timingScope="Preparation only; discovery and earlier bootstrap excluded. Contract draft-to-freeze wall span overlaps harness work; not human authoring time.",
    )
    if (root / "effort-start.json").exists():
        state["effort"] = artifacts.read(root / "effort-start.json")
        state["effort"]["contractsFrozenAt"] = datetime.now(timezone.utc).isoformat()
    artifacts.save(root / "campaign.json", state)
    report(root, state)


def evaluate(root, state, task):
    candidate = root / "tasks" / task["id"] / "candidate"
    manifest = artifacts.manifest(candidate)
    original = state["frozen"]["base"]
    if set(manifest) != set(original) or any(
        value != original[name]
        for name, value in manifest.items()
        if name not in task["files"]
    ):
        raise ValueError(
            "Candidate changed frozen files outside its approved application modules"
        )
    folder = candidate.parent / ("attempt-" + uuid.uuid4().hex[:12])
    folder.mkdir()
    snapshot = folder / "source"
    shutil.copytree(
        candidate,
        snapshot,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    shutil.copyfile(Path(__file__), folder / "runner.py")
    env = environment(root, snapshot)
    phases = {"upstreamTests": upstream_tests(root, state, snapshot, folder)}
    phases["acceptance"] = artifacts.execute(
        [state["python"], root / "frozen/acceptance.py", snapshot, task["id"]],
        folder,
        "acceptance",
        env,
    )
    phases["check"] = artifacts.execute(
        [state["binary"], "check", "--output", "json"],
        folder,
        "check",
        env,
        workdir=root / "project",
    )
    result = {
        "schema": 1,
        "task": task["id"],
        "phases": phases,
        "source": manifest,
        "category": "prospective_application_development",
        "upstreamRevision": state["source"]["revision"],
        "runnerSha256": artifacts.digest(folder / "runner.py"),
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    if (folder / "check.stdout").stat().st_size:
        check = artifacts.read(folder / "check.stdout")
        result["wraith"] = check
    if artifacts.manifest(snapshot) != manifest:
        raise ValueError(
            "Evaluation modified its own source snapshot; attempt remains incomplete"
        )
    artifacts.save(folder / "result.json", result)
    artifacts.save(folder / "evidence.json", artifacts.manifest(folder))
    report(root, state)
    print(
        json.dumps(
            {"task": task["id"], "phases": phases, "evidence": str(folder)}, indent=2
        )
    )
    exits = [phase["exit"] for phase in phases.values()]
    return (
        2
        if any(code not in (0, 1, 3) for code in exits)
        else 3
        if 3 in exits
        else 1
        if 1 in exits
        else 0
    )


def finish(root, state):
    tasks = artifacts.read(root / "frozen/tasks.json")
    for task in tasks:
        results = [
            artifacts.read(path)
            for path in root.glob(f"tasks/{task['id']}/attempt-*/result.json")
        ]
        if not results:
            raise ValueError(f"No completed evaluation for {task['id']}")
        latest = max(results, key=lambda item: item["completedAt"])
        if latest["source"] != artifacts.manifest(
            root / "tasks" / task["id"] / "candidate"
        ):
            raise ValueError(f"Candidate changed after its evaluation: {task['id']}")
        if any(phase["exit"] != 0 for phase in latest["phases"].values()):
            raise ValueError(f"Task has unresolved failed checks: {task['id']}")
        if (
            latest["wraith"]["record"]["baselineId"]
            != state["baselineResult"]["record"]["id"]
        ):
            raise ValueError("Task comparison used a different baseline")
    artifacts.save(
        root / "completion.json",
        {
            "schema": 1,
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "tasks": [task["id"] for task in tasks],
            "nativeHistory": artifacts.manifest(root / "project/.wraith/history"),
        },
    )
    report(root, state)


def report(root, state):
    rows = []
    for path in sorted(root.glob("tasks/*/attempt-*/result.json")):
        result = artifacts.read(path)
        phase = result["phases"]
        xml = path.parent / "upstream.xml"
        suites = list(ET.parse(xml).getroot().iter("testsuite")) if xml.exists() else []
        count = sum(int(s.attrib.get("tests", 0)) for s in suites)
        skipped = sum(int(s.attrib.get("skipped", 0)) for s in suites)
        history_id = result.get("wraith", {}).get("record", {}).get("id")
        target = (
            f"project/.wraith/history/{history_id}/report.html"
            if history_id
            else f"{path.parent.relative_to(root)}/result.json"
        )
        rows.append(
            f"| [{result['task']}]({target}) | {count} ({skipped} skipped) | {phase['upstreamTests']['exit']} | {phase['acceptance']['exit']} | {phase['check']['exit']} |"
        )
    lines = [
        "# LLM application pilot",
        "",
        f"Pinned source: {state['source']['repository']} at `{state['source']['revision']}` (Apache-2.0).",
        "",
        "Actual application CLI and tool orchestration; offline Echo model, harmless local tools, and a cooperative socket guard. Model quality, production randomness, and maintainer adoption are outside this experiment.",
        "",
        f"Finite queue complete: {(root / 'completion.json').exists()}.",
        "",
        "| Task / attempt | Selected upstream tests | Upstream exit | Acceptance exit | Wraith check exit |",
        "| --- | --- | --- | --- | --- |",
        *rows,
        "",
        f"Measured preparation: {state['measuredPreparationSeconds']} seconds. {state['timingScope']}",
        "",
        "Contracts were frozen before source edits. The upstream test subset is test_tools.py plus test_pause_resume.py with provider cassette tests excluded (`not vcr`), unchanged in every candidate. Feature acceptance is separate from the regression gate.",
        "",
        "Native Wraith history and HTML reports are in project/.wraith/history; its index is project/.wraith/index.html. Baseline pointer, source, policy, adapters, dependency versions, and prior evidence are checked before reuse.",
        "",
        "Git metadata in native history identifies the harness checkout; exact application provenance is the pinned upstream revision plus the recorded full source fingerprint. No environment values or provider usage estimates are saved.",
        "",
        "Passing comparisons alone do not establish incremental value. Human contract-writing effort, developer report-review time, and repeat adoption are unmeasured. A failure requires review before being counted as useful or a false alarm.",
    ]
    (root / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO / ".wraith/app-pilot-validated"
    )
    parser.add_argument(
        "--binary", type=Path, default=Path.home() / ".local/bin/wraith"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = sub.add_parser("prepare")
    prepare_cmd.add_argument("--install", action="store_true")
    for name in ("task", "evaluate"):
        sub.add_parser(name).add_argument("id")
    sub.add_parser("status")
    sub.add_parser("finish")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        prepare(root, args.binary.resolve(), args.install)
        return 0
    state = verify(root)
    if args.command == "finish":
        if not (root / "completion.json").exists():
            finish(root, state)
        print(root / "report.md")
        return 0
    tasks = {task["id"]: task for task in artifacts.read(root / "frozen/tasks.json")}
    if args.command == "status":
        report(root, state)
        print(root / "report.md")
        return 0
    if (root / "completion.json").exists():
        raise ValueError(
            "Finite queue is complete; use an explicit new campaign for more work"
        )
    if args.id not in tasks:
        raise ValueError("Unknown task")
    task = tasks[args.id]
    if args.command == "task":
        candidate = root / "tasks" / task["id"] / "candidate"
        shutil.copytree(root / "base", candidate)
        print(json.dumps(dict(task, candidate=str(candidate)), indent=2))
        return 0
    return evaluate(root, state, task)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
