#!/usr/bin/env python3
"""Reproduce a real upstream approval bug and evaluate isolated application changes.

Network is used only by --install. Evaluation uses a FunctionModel and in-memory
receipts. This is trusted local execution, not a network/filesystem sandbox.
"""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/historical-approval"
PATHS = [
    "pydantic_ai_slim",
    "pydantic_graph",
    "tests",
    "pyproject.toml",
    "uv.lock",
    "LICENSE",
]


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(directory):
    files = {}
    for path in directory.rglob("*"):
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        if path.is_symlink():
            raise ValueError(f"Symlink not accepted in evidence: {path}")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = digest(path)
    return files


def execute(command, cwd, label, env=None, timeout=180, workdir=None):
    start = datetime.now(timezone.utc).isoformat()
    with (
        (cwd / f"{label}.stdout").open("w") as stdout,
        (cwd / f"{label}.stderr").open("w") as stderr,
    ):
        result = subprocess.run(
            [str(x) for x in command],
            cwd=workdir or cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            timeout=timeout,
            check=False,
        )
    return {
        "exit": result.returncode,
        "startedAt": start,
        "endedAt": datetime.now(timezone.utc).isoformat(),
    }


def verify(root):
    state = read(root / "campaign.json")
    if state["schema"] != 1:
        raise ValueError("Unsupported campaign schema")
    if digest(Path(state["binary"])) != state["binarySha256"]:
        raise ValueError("Wraith binary changed; use an explicit new campaign")
    for name, expected in state["frozen"].items():
        if manifest(root / name) != expected:
            raise ValueError(f"Frozen inputs changed: {name}")
    installed = subprocess.check_output(
        [state["python"], "-m", "pip", "--no-cache-dir", "freeze", "--all"], text=True
    )
    if installed != state["installedDependencies"]:
        raise ValueError("Dependency environment changed; use an explicit new campaign")
    for evidence in root.glob("**/evidence.json"):
        observed = manifest(evidence.parent)
        observed.pop("evidence.json", None)
        if observed != read(evidence):
            raise ValueError(f"Completed evidence changed: {evidence.parent}")
    return state


def environment(root, revision, app):
    source = root / "sources" / revision
    return dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        LOGFIRE_SEND_TO_LOGFIRE="false",
        PYTHONPATH=os.pathsep.join(
            str(source / name) for name in ("pydantic_ai_slim", "pydantic_graph")
        ),
        WRAITH_APPROVAL_APP=str(app),
        PYTEST_ADDOPTS="",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    )


def prepare(root, binary, install, selected_python=None):
    if (root / "campaign.json").exists():
        verify(root)
        return
    source = read(EXAMPLE / "source.json")
    root.mkdir(parents=True, exist_ok=True)
    python = selected_python or root / "venv" / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    if install:
        clone = root / "upstream"
        if not clone.exists():
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    source["repository"],
                    str(clone),
                ],
                check=True,
            )
        for name, sha in source["revisions"].items():
            target = root / "sources" / name
            archive = root / f"{name}.tar"
            # Export exact commits; never reset an existing checkout or source copy.
            if target.exists():
                if not archive.exists():
                    raise ValueError(
                        "Existing source export has no archive; use a new root"
                    )
                continue
            subprocess.run(
                ["git", "-C", str(clone), "fetch", "--depth", "1", "origin", sha],
                check=True,
            )
            with archive.open("wb") as stream:
                subprocess.run(
                    ["git", "-C", str(clone), "archive", sha, *PATHS],
                    stdout=stream,
                    check=True,
                )
            target.mkdir(parents=True)
            with tarfile.open(archive) as content:
                content.extractall(target, filter="data")
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
                str(EXAMPLE / "requirements.txt"),
            ],
            check=True,
        )
    if not python.exists():
        raise ValueError("Missing isolated environment; run prepare --install")
    frozen = root / "frozen"
    frozen.mkdir(exist_ok=False)
    for name in (
        "approval_agent.py",
        "invoke.py",
        "contracts.json",
        "source.json",
        "tasks.json",
        "acceptance.py",
        "requirements.txt",
    ):
        shutil.copyfile(EXAMPLE / name, frozen / name)
    shutil.copyfile(
        REPO / "adapters/python/wraith_adapter.py", frozen / "wraith_adapter.py"
    )
    # Check that archives really represent the declared SHAs, including existing exports.
    for name, sha in source["revisions"].items():
        archive = root / f"{name}.tar"
        comment = (
            subprocess.check_output(
                ["git", "get-tar-commit-id"], input=archive.read_bytes()
            )
            .decode()
            .strip()
        )
        if comment != sha:
            raise ValueError(f"Wrong source archive: {name}")
        check = root / f"verify-{name}"
        check.mkdir(exist_ok=False)
        try:
            with tarfile.open(archive) as content:
                content.extractall(check, filter="data")
            if manifest(check) != manifest(root / "sources" / name):
                raise ValueError(f"Modified source export: {name}")
        finally:
            shutil.rmtree(check)
    version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    state = {
        "schema": 1,
        "binary": str(binary),
        "binaryVersion": version,
        "binarySha256": digest(binary),
        "python": str(python),
        "source": source,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "frozen": {
            name: manifest(root / name)
            for name in ("frozen", "sources/before", "sources/buggy", "sources/fixed")
        },
    }
    result = execute([python, "-m", "pip", "check"], root, "dependency-check")
    if result["exit"] != 0:
        raise ValueError("Dependency check failed; inspect dependency-check.stdout")
    execute([python, "-m", "pip", "freeze", "--all"], root, "installed-dependencies")
    state["installedDependencies"] = (
        root / "installed-dependencies.stdout"
    ).read_text()
    save(root / "campaign.json", state)


def suite(root, state):
    frozen = root / "frozen"
    return {
        "version": 1,
        "agent": {
            "command": shlex.join(
                [
                    state["python"],
                    str(frozen / "wraith_adapter.py"),
                    str(frozen / "invoke.py") + ":evaluate",
                ]
            ),
            "timeout_ms": 15000,
        },
        "tests": read(frozen / "contracts.json"),
    }


def evaluate(root, state, revision, app, folder, task=None):
    if set(manifest(app)) != {"approval_agent.py"} and app != root / "frozen":
        raise ValueError("Candidate may contain only approval_agent.py")
    folder.mkdir(parents=True, exist_ok=False)
    snapshot = folder / "evaluated"
    snapshot.mkdir()
    shutil.copyfile(Path(__file__), folder / "runner.py")
    shutil.copyfile(app / "approval_agent.py", snapshot / "approval_agent.py")
    env = environment(root, revision, snapshot)
    config = folder / "wraith.json"
    save(config, suite(root, state))
    phases = {}
    # Run each revision's own unchanged tests with the same selection. Snapshots
    # legitimately evolve across revisions; counts and overlaps must be reported.
    tests = root / "sources" / revision
    phases["upstreamTests"] = execute(
        [
            state["python"],
            "-m",
            "pytest",
            "-p",
            "anyio.pytest_plugin",
            "-p",
            "pytest_mock",
            "-p",
            "pytest_recording.plugin",
            "-p",
            "inline_snapshot.pytest_plugin",
            "-p",
            "no:cacheprovider",
            *[str(tests / name) for name in state["source"]["testFiles"]],
            "-k",
            state["source"]["testSelection"],
            "-q",
            f"--junitxml={folder / 'upstream.xml'}",
        ],
        folder,
        "upstream-tests",
        env,
        workdir=tests,
    )
    if task:
        phases["acceptance"] = execute(
            [state["python"], root / "frozen/acceptance.py", snapshot, task],
            folder,
            "acceptance",
            env,
        )
    phases["wraith"] = execute(
        [
            state["binary"],
            "--config",
            config,
            "run",
            "--save",
            "run",
            "--output",
            "json",
        ],
        folder,
        "run",
        env,
    )
    record = {
        "schema": 1,
        "revision": revision,
        "commit": state["source"]["revisions"][revision],
        "category": "prospective_development" if task else "historical_reproduction",
        "task": task,
        "source": manifest(snapshot),
        "phases": phases,
        "runnerSha256": digest(Path(__file__)),
        "complete": task is None,
        "providerRequests": 0,
    }
    save(folder / "result.json", record)
    return record


def compare(root, state, baseline, candidate, label):
    result = execute(
        [
            state["binary"],
            "compare",
            baseline / ".wraith/runs/run.json",
            candidate / ".wraith/runs/run.json",
            "--policy",
            baseline / "wraith.json",
            "--html",
            candidate / f"{label}.html",
            "--output",
            "json",
        ],
        candidate,
        label,
    )
    record = read(candidate / "result.json")
    record["comparison"] = result
    record["complete"] = True
    save(candidate / "result.json", record)
    return result


def historical(root, state):
    target = root / "historical"
    if target.exists():
        raise ValueError("Historical evidence already exists; refusing to overwrite")
    for name in ("before", "buggy", "fixed"):
        evaluate(root, state, name, root / "frozen", target / name)
    compare(root, state, target / "before", target / "buggy", "regression")
    compare(root, state, target / "before", target / "fixed", "fix")
    # The exact upstream test body, with compatible imports supplied by this harness.
    generated = root / "regression-test"
    generated.mkdir(exist_ok=False)
    source = (root / "sources/fixed/tests/test_agent.py").read_text()
    node = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == state["source"]["newRegressionTest"]
    )
    imports = """import pytest
from dirty_equals import IsStr
from inline_snapshot import snapshot
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.models.function import AgentInfo, FunctionModel
pytestmark = pytest.mark.anyio
"""
    (generated / "test_upstream.py").write_text(
        imports + "\n" + ast.get_source_segment(source, node) + "\n"
    )
    (generated / "conftest.py").write_text(
        "import pytest\n@pytest.fixture\ndef anyio_backend():\n    return 'asyncio'\n"
    )
    shutil.copyfile(root / "sources/fixed/LICENSE", generated / "LICENSE")
    # Positive control: the maintainers' later-added regression test on buggy and fixed code.
    for name in ("buggy", "fixed"):
        folder = target / name
        test = generated / "test_upstream.py"
        result = execute(
            [
                state["python"],
                "-m",
                "pytest",
                "-p",
                "anyio.pytest_plugin",
                "-p",
                "pytest_mock",
                "-p",
                "pytest_recording.plugin",
                "-p",
                "inline_snapshot.pytest_plugin",
                "-p",
                "no:cacheprovider",
                f"{test}::{state['source']['newRegressionTest']}",
                "-q",
            ],
            folder,
            "fix-added-test",
            environment(root, name, root / "frozen"),
            workdir=generated,
        )
        record = read(folder / "result.json")
        record["fixAddedTest"] = result
        save(folder / "result.json", record)
    save(target / "evidence.json", manifest(target))
    for name, expected in [("before", 0), ("buggy", 1), ("fixed", 0)]:
        record = read(target / name / "result.json")
        if record["phases"]["wraith"]["exit"] != expected:
            raise ValueError(
                f"Historical reproduction failed at {name}; inspect preserved results"
            )
    if (
        read(target / "buggy/result.json")["comparison"]["exit"] != 1
        or read(target / "fixed/result.json")["comparison"]["exit"] != 0
    ):
        raise ValueError("Unexpected historical comparison decision; inspect evidence")
    if (
        read(target / "buggy/result.json")["fixAddedTest"]["exit"] != 1
        or read(target / "fixed/result.json")["fixAddedTest"]["exit"] != 0
    ):
        raise ValueError(
            "Upstream regression-test control did not reproduce; inspect evidence"
        )
    report = read(target / "buggy/regression.stdout")
    failed = {
        change["scenarioId"]
        for change in report["changes"]
        if change["severity"] == "failure"
    }
    if failed != {"resume", "resume-unicode"}:
        raise ValueError("Unexpected failing scenarios; inspect preserved comparison")


def write_report(root, state):
    rows = []
    development = []
    for path in sorted(root.glob("**/result.json")):
        result = read(path)
        phases = result["phases"]
        xml = path.parent / "upstream.xml"
        tests = "unavailable"
        if xml.exists():
            suites = list(ET.parse(xml).getroot().iter("testsuite"))
            count = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
            failures = sum(
                int(suite.attrib.get("failures", 0))
                + int(suite.attrib.get("errors", 0))
                for suite in suites
            )
            tests = f"{count - failures}/{count}"
        name = result["task"] or result["revision"]
        comparison = result.get("comparison", {}).get("exit", "baseline")
        link = path.parent.relative_to(root).as_posix()
        report_name = (
            "comparison"
            if result["task"]
            else ("regression" if result["revision"] == "buggy" else "fix")
        )
        label = (
            f"[{name}]({link}/{report_name}.html)" if comparison != "baseline" else name
        )
        acceptance = phases.get("acceptance", {}).get("exit", "—")
        rows.append(
            f"| {label} | {tests} | {acceptance} | {phases['wraith']['exit']} | {comparison} |"
        )
        if result["task"]:
            development.append(result)
    historical_complete = all(
        (root / "historical" / name / "result.json").exists()
        for name in ("before", "buggy", "fixed")
    )
    reproduced = historical_complete and all(
        read(root / "historical" / name / "result.json")["phases"]["wraith"]["exit"]
        == exit_code
        for name, exit_code in [("before", 0), ("buggy", 1), ("fixed", 0)]
    )
    if reproduced:
        buggy = read(root / "historical/buggy/result.json")
        fixed = read(root / "historical/fixed/result.json")
        reproduced = (
            buggy.get("comparison", {}).get("exit") == 1
            and fixed.get("comparison", {}).get("exit") == 0
            and buggy.get("fixAddedTest", {}).get("exit") == 1
            and fixed.get("fixAddedTest", {}).get("exit") == 0
        )
    lines = [
        "# Upstream approval pilot",
        "",
        "Scope: retrospective reproduction of one documented framework bug, followed by isolated Codex changes to a small offline workflow. No production discovery, full upstream test-suite, model-quality, or adoption claim.",
        "",
        f"Wraith: {state['binaryVersion']}. Runtime dependencies and source/binary hashes are recorded in `campaign.json`.",
        "",
        "| Revision / task | Upstream subset passed | Feature acceptance exit | Wraith run exit | Comparison exit |",
        "| --- | --- | --- | --- | --- |",
        *rows,
        "",
        "Exit 0 passes; 1 is a behavioral/test failure; 2 is an execution/setup failure; 3 is inconclusive. The buggy historical revision is expected to fail. Test subsets use each revision's own unchanged tests, with the same selection; they are not identical test suites.",
        "",
        "## Historical finding",
        "",
        f"Reproduction verified: {reproduced}. One historical defect appears in two resumed-history scenarios; these are not two independent bugs.",
        "",
        f"Upstream provenance: [issue #3350]({state['source']['issue']}), [introduction]({state['source']['introduction']}), [fix]({state['source']['fix']}). Source is MIT licensed; LICENSE is retained with every source export.",
        "",
        "The required behavior is to defer an unapproved action. Inspect `historical/buggy/regression.html` for the observed execution count, pending-approval count, status, and actual recorded tool activity before and after the introducing change.",
        "",
        "The maintainers' later regression-test body is extracted unchanged with compatible imports. Its separate buggy/fixed control logs are preserved. This demonstrates that a targeted unit test can express the same rule; Wraith adds a reusable workflow contract and before/after evidence, not a unique bug-detection algorithm.",
        "",
        "## Prospective changes",
        "",
        f"Completed candidate comparisons: {len(development)}. Passing development comparisons: {sum(all(p['exit'] == 0 for p in r['phases'].values()) and r.get('comparison', {}).get('exit') == 0 for r in development)}.",
        "",
        "Tasks are independent branches of the fixed baseline, not a combined application release. Feature acceptance is separate from regression gating. Failures and repairs remain separate immutable attempts. Passing changes do not establish incremental value; noise and miss rates are not estimated from this small deterministic suite.",
        "",
        "## Decision",
        "",
        (
            "A reproducible historical finding supports testing approval and resumed-state contracts with Wraith. Prospective customer usefulness remains unproven. Next: use one independently maintained agent application during legitimate changes, measure contract-authoring effort and report usefulness, and compare with its existing tests. Avoid expanding the mock merely to manufacture a failing change."
            if reproduced
            else "Reproduction is incomplete or unverified. Inspect setup/execution results before drawing a product conclusion."
        ),
        "",
        "Provider requests: zero; FunctionModel and in-memory receipt tools only. Evidence remains local. These runs do not test unattended automation or native Linux/Windows execution.",
    ]
    (root / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO / ".wraith/historical-approval-validated"
    )
    parser.add_argument(
        "--binary", type=Path, default=Path.home() / ".local/bin/wraith"
    )
    parser.add_argument(
        "--python", type=Path, help="Existing isolated dependency environment"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("prepare")
    install.add_argument("--install", action="store_true")
    sub.add_parser("historical")
    task = sub.add_parser("task")
    task.add_argument("id")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("id")
    sub.add_parser("status")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "prepare":
        prepare(
            root,
            args.binary.resolve(),
            args.install,
            args.python.absolute() if args.python else None,
        )
    else:
        state = verify(root)
        tasks = {task["id"]: task for task in read(root / "frozen/tasks.json")}
        if args.command == "historical":
            historical(root, state)
            write_report(root, state)
        elif args.command in ("task", "evaluate"):
            if args.id not in tasks:
                raise ValueError("Unknown task")
            directory = root / "development" / args.id
            candidate = directory / "candidate"
            if args.command == "task":
                candidate.mkdir(parents=True, exist_ok=False)
                shutil.copyfile(
                    root / "frozen/approval_agent.py", candidate / "approval_agent.py"
                )
                print(
                    json.dumps(dict(tasks[args.id], candidate=str(candidate)), indent=2)
                )
            else:
                attempt = directory / ("attempt-" + uuid.uuid4().hex[:12])
                record = evaluate(root, state, "fixed", candidate, attempt, args.id)
                compare(root, state, root / "historical/fixed", attempt, "comparison")
                record = read(attempt / "result.json")
                save(attempt / "evidence.json", manifest(attempt))
                print(json.dumps(record, indent=2))
                write_report(root, state)
                exits = [phase["exit"] for phase in record["phases"].values()] + [
                    record["comparison"]["exit"]
                ]
                if any(value not in (0, 1, 3) for value in exits):
                    return 2
                if 3 in exits:
                    return 3
                if 1 in exits:
                    return 1
        else:
            write_report(root, state)
            for path in sorted(root.glob("**/result.json")):
                print(path.relative_to(root), json.dumps(read(path)))


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
