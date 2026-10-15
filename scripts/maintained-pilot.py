#!/usr/bin/env python3
"""Freeze and evaluate local fixes to a pinned maintained agent, without providers."""

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
import uuid
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "examples/maintained-agent"
spec = importlib.util.spec_from_file_location(
    "application", REPO / "scripts/application-pilot.py"
)
application = importlib.util.module_from_spec(spec)
spec.loader.exec_module(application)
artifacts = application.artifacts


def environment(root, source):
    return dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            map(str, [root / "frozen/offline", source / "src", source])
        ),
        WRAITH_APP_SOURCE=str(source),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONOPTIMIZE="0",
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_ADDOPTS="",
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        HF_TOKEN="offline-fixture",
        OPENAI_API_KEY="offline-fixture",
    )


def tests(root, state, source, folder, label="upstream", optimized=False, strict=False):
    nodes = state["source"]["optimizedControl" if optimized else "tests"]
    if strict:
        nodes = [
            "tests/test_agents.py::TestToolCallingAgent::test_toolcalling_agent_passes_both_tools_and_managed_agents"
        ]
    return artifacts.execute(
        [
            state["python"],
            *(["-O"] if optimized else []),
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "pytest_datadir.plugin",
            "-p",
            "no:cacheprovider",
            *(
                ["-W", "error::pytest.PytestUnraisableExceptionWarning"]
                if strict
                else []
            ),
            *[source / node for node in nodes],
            "-q",
            f"--junitxml={folder / (label + '.xml')}",
        ],
        folder,
        label,
        environment(root, source),
        workdir=source,
    )


def junit(path):
    suites = list(ET.parse(path).getroot().iter("testsuite"))
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    counts["passed"] = counts["tests"] - sum(
        counts[k] for k in ("failures", "errors", "skipped")
    )
    return counts


def verify(root):
    # Reuse the established binary/dependency/source/policy/history evidence seals.
    state = application.verify(root)
    for name, expected in state.get("setupEvidence", {}).items():
        if artifacts.digest(root / name) != expected:
            raise ValueError("Original setup/control evidence changed")
    for path in root.glob("tasks/*/attempt-*/result.json"):
        if not (path.parent / "evidence.json").exists():
            raise ValueError("Completed attempt has no evidence seal")
    if (root / "completion.json").exists():
        saved = artifacts.read(root / "completion.json")
        if artifacts.manifest(root / "tasks") != saved["taskEvidence"]:
            raise ValueError("Completed task evidence changed or disappeared")
    return state


def prepare(root, binary, upstream, python, install):
    if (root / "campaign.json").exists():
        return verify(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Preserve incomplete preparation; choose an explicit new root")
    root.mkdir(parents=True, exist_ok=True)
    source = artifacts.read(FIXTURE / "source.json")
    if install:
        if upstream is not None or python is not None:
            raise ValueError("Use --install or existing --upstream/--python, not both")
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
        python = (
            root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        subprocess.run([sys.executable, "-m", "venv", str(root / "venv")], check=True)
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
    if upstream is None or python is None:
        raise ValueError("Provide --upstream and --python, or use --install")
    # Resolving a venv symlink would select the system interpreter instead.
    python = python.absolute()
    state = {
        "schema": 1,
        "source": source,
        "python": str(python.absolute()),
        "binary": str(binary),
        "binarySha256": artifacts.digest(binary),
        "packages": application.packages(python),
        "preparedAt": datetime.now(timezone.utc).isoformat(),
    }
    archive = root / "source.tar"
    with archive.open("wb") as stream:
        subprocess.run(
            ["git", "-C", str(upstream), "archive", source["revision"]],
            stdout=stream,
            check=True,
        )
    base = root / "base"
    base.mkdir()
    with tarfile.open(archive) as stream:
        stream.extractall(base, filter="data")
    shutil.copytree(
        FIXTURE, root / "frozen", ignore=shutil.ignore_patterns("__pycache__")
    )
    project = root / "project"
    project.mkdir()
    setup = {
        "init": artifacts.execute(
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
                source["modelLabel"],
            ],
            project,
            "init",
        )
    }
    if setup["init"]["exit"] != 0:
        raise ValueError("Native init failed; preserve logs and use a new root")
    config = artifacts.read(project / "wraith.yaml")
    config["tests"] = artifacts.read(root / "frozen/contracts.json")
    artifacts.save(project / "wraith.yaml", config)
    setup["upstream"] = tests(root, state, base, project)
    setup["optimized"] = tests(root, state, base, project, "optimized", optimized=True)
    setup["strictWarnings"] = tests(
        root, state, base, project, "strict-warnings", strict=True
    )
    setup["callableUnitControl"] = artifacts.execute(
        [state["python"], root / "frozen/acceptance.py", "callable-diagnostics"],
        project,
        "callable-unit-control",
        environment(root, base),
    )
    setup["baseline"] = artifacts.execute(
        [binary, "baseline", "--output", "json"],
        project,
        "baseline",
        environment(root, base),
    )
    artifacts.save(root / "setup.json", setup)
    if setup["upstream"]["exit"] != 0 or any(
        setup[name]["exit"] != 1
        for name in ("baseline", "optimized", "strictWarnings", "callableUnitControl")
    ):
        raise ValueError(
            "Unexpected diagnostic/control outcome; preserve this root and inspect setup.json"
        )
    state.update(
        baselineResult=artifacts.read(project / "baseline.stdout"),
        setupEvidence={
            path.relative_to(root).as_posix(): artifacts.digest(path)
            for path in [root / "setup.json", *project.iterdir()]
            if path.is_file()
            and (
                path.suffix in (".stdout", ".stderr", ".xml")
                or path.name == "setup.json"
            )
        },
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
    )
    artifacts.save(root / "campaign.json", state)
    return state


def task_for(root, name):
    tasks = {t["id"]: t for t in artifacts.read(root / "frozen/tasks.json")}
    if name not in tasks:
        raise ValueError("Unknown task")
    return tasks[name]


def candidate(root, task):
    path = root / "tasks" / task["id"] / "candidate"
    shutil.copytree(root / "base", path)
    print(json.dumps(dict(task, candidate=str(path)), indent=2))
    return path


def validate_candidate(root, state, task):
    path = root / "tasks" / task["id"] / "candidate"
    current, original = artifacts.manifest(path), state["frozen"]["base"]
    if set(current) != set(original) or any(
        value != original[name]
        for name, value in current.items()
        if name not in task["files"]
    ):
        raise ValueError(
            "Candidate modified files outside approved application modules"
        )
    return path, current


def evaluate(root, state, task):
    path, fingerprint = validate_candidate(root, state, task)
    folder = path.parent / ("attempt-" + uuid.uuid4().hex[:12])
    folder.mkdir()
    snapshot = folder / "source"
    shutil.copytree(
        path, snapshot, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache")
    )
    phases = {
        "upstream": tests(root, state, snapshot, folder),
        "optimized": tests(root, state, snapshot, folder, "optimized", optimized=True),
        "strictWarnings": tests(
            root, state, snapshot, folder, "strict-warnings", strict=True
        ),
    }
    phases["acceptance"] = artifacts.execute(
        [state["python"], root / "frozen/acceptance.py", task["id"]],
        folder,
        "acceptance",
        environment(root, snapshot),
    )
    phases["check"] = artifacts.execute(
        [state["binary"], "check", "--output", "json"],
        folder,
        "check",
        environment(root, snapshot),
        workdir=root / "project",
    )
    if artifacts.manifest(snapshot) != fingerprint:
        raise ValueError("Source changed during evaluation; attempt remains incomplete")
    result = {
        "schema": 1,
        "task": task["id"],
        "source": fingerprint,
        "phases": phases,
        "category": "source_inspection_targeted_existing_defects",
        "wraith": artifacts.read(folder / "check.stdout"),
        "upstream": junit(folder / "upstream.xml"),
        "optimizedControl": junit(folder / "optimized.xml"),
        "strictWarningControl": junit(folder / "strict-warnings.xml"),
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    artifacts.save(folder / "result.json", result)
    artifacts.save(folder / "evidence.json", artifacts.manifest(folder))
    print(
        json.dumps(
            {"task": task["id"], "phases": phases, "evidence": str(folder)}, indent=2
        )
    )
    # Controls deliberately retain other known defects in partial fixes.
    expected = {
        "optimized": 0 if task["id"] in ("optimized-checks", "combined") else 1,
        "strictWarnings": 0 if task["id"] in ("stream-close", "combined") else 1,
    }
    if any(
        phase["exit"] != expected.get(name, 0)
        for name, phase in phases.items()
        if name != "check"
    ):
        return 1
    return phases["check"]["exit"]


def finish(root, state):
    rows = []
    for task in artifacts.read(root / "frozen/tasks.json"):
        paths = sorted(
            root.glob(f"tasks/{task['id']}/attempt-*/result.json"),
            key=lambda p: artifacts.read(p)["completedAt"],
        )
        if not paths:
            raise ValueError(f"No completed evaluation for {task['id']}")
        result = artifacts.read(paths[-1])
        _, current = validate_candidate(root, state, task)
        if current != result["source"]:
            raise ValueError("Candidate changed after evaluation")
        required = (
            ("upstream", "acceptance", "check", "optimized", "strictWarnings")
            if task["id"] == "combined"
            else ("upstream", "acceptance")
        )
        if any(result["phases"][name]["exit"] != 0 for name in required):
            raise ValueError(f"Unresolved checks: {task['id']}")
        expected_controls = {
            "optimized": 0 if task["id"] in ("optimized-checks", "combined") else 1,
            "strictWarnings": 0 if task["id"] in ("stream-close", "combined") else 1,
        }
        if any(
            result["phases"][name]["exit"] != code
            for name, code in expected_controls.items()
        ):
            raise ValueError("Unexpected upstream control result")
        expected_exit = 1 if task["id"] == "optimized-checks" else 0
        if result["phases"]["check"]["exit"] != expected_exit:
            raise ValueError(
                "Unexpected comparison decision; review before accepting reproduction"
            )
        if (
            result["phases"]["check"]["exit"] not in (0, 1)
            or result["wraith"]["comparison"]["executionErrors"]
        ):
            raise ValueError("Execution errors are not completed findings")
        if task["id"] == "combined" and not all(
            s["passed"] for s in result["wraith"]["run"]["scenarios"]
        ):
            raise ValueError("Combined fix retains failed expectations")
        if (
            result["wraith"]["record"]["baselineId"]
            != state["baselineResult"]["record"]["id"]
        ):
            raise ValueError("Comparison used a different diagnostic baseline")
        rows.append(result)
    artifacts.save(
        root / "completion.json",
        {
            "schema": 1,
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "nativeHistory": artifacts.manifest(root / "project/.wraith/history"),
            "taskEvidence": artifacts.manifest(root / "tasks"),
        },
    )
    return rows


def apply_reviewed(root, task):
    patch = root / "frozen/changes" / (task["id"] + ".patch")
    stats = subprocess.check_output(
        ["git", "apply", "--numstat", str(patch)], text=True
    )
    changed = []
    for line in stats.splitlines():
        added, removed, name = line.split("\t")
        if not added.isdigit() or not removed.isdigit() or name not in task["files"]:
            raise ValueError("Reviewed patch changes an unapproved file")
        changed.append(name)
    if not changed:
        raise ValueError("Reviewed patch is empty")
    path = candidate(root, task)
    subprocess.run(
        ["git", "apply", "--no-index", str(patch)],
        cwd=path,
        env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(path.parent)),
        check=True,
    )
    return path


def report(root, state):
    def summary(result, baseline=False):
        wraith = result if baseline else result["wraith"]
        scenarios = wraith["run"]["scenarios"]
        return {
            "version": "unmodified" if baseline else result["task"],
            "scenariosPassed": sum(s["passed"] for s in scenarios),
            "scenariosTotal": len(scenarios),
            "wraithExit": 1 if baseline else result["phases"]["check"]["exit"],
            "upstream": junit(root / "project/upstream.xml")
            if baseline
            else result["upstream"],
            "optimizedControl": junit(root / "project/optimized.xml")
            if baseline
            else result["optimizedControl"],
            "strictWarningControl": junit(root / "project/strict-warnings.xml")
            if baseline
            else result["strictWarningControl"],
            "newFailedAssertions": []
            if baseline
            else [
                {k: c[k] for k in ("scenarioId", "classification", "message")}
                for c in wraith["comparison"]["changes"]
                if c["severity"] == "failure"
            ],
            "sourceModuleSha256": state["frozen"]["base"]["src/smolagents/agents.py"]
            if baseline
            else result["source"]["src/smolagents/agents.py"],
            "report": artifacts.relative_report_path(wraith["report"], root),
        }

    rows = [summary(state["baselineResult"], baseline=True)]
    for task in artifacts.read(root / "frozen/tasks.json"):
        paths = sorted(
            root.glob(f"tasks/{task['id']}/attempt-*/result.json"),
            key=lambda p: artifacts.read(p)["completedAt"],
        )
        if paths:
            rows.append(summary(artifacts.read(paths[-1])))
    assessment = {
        "schema": 1,
        "upstream": state["source"]["repository"],
        "revision": state["source"]["revision"],
        "category": "source_inspection_targeted_existing_defects_and_local_fix_interaction",
        "completed": (root / "completion.json").exists(),
        "providerRequests": 0,
        "existingRootCauses": 3,
        "contractsSha256": state["frozen"]["frozen"]["contracts.json"],
        "results": rows,
        "limits": [
            "Contracts were selected after source inspection; not blind or prospective defect discovery.",
            "Two newly failing errorType assertions expose one latent callable crash in already-failing optimized scenarios.",
            "Existing tests also detect optimization defects under -O and the stream issue with strict warnings; new targeted unit tests cover callables.",
            "Passing comparisons can retain existing failed contracts; only the combined fix passes all nine scenarios.",
            "No production model quality, complete upstream-suite coverage, maintainer adoption, buyer demand, or human review time measured.",
        ],
    }
    artifacts.save(root / "assessment.json", assessment)
    lines = [
        "# Maintained-agent evaluation",
        "",
        f"Pinned smolagents: `{state['source']['revision']}`.",
        "",
        "Real ToolCallingAgent orchestration with a scripted offline model. Three existing root causes; seven failed scenarios before fixes. No provider requests.",
        "",
        "| Version | Contracts passed | Wraith exit | Existing tests passed / skipped | Existing tests under -O passed | Strict stream test passed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| [{row['version']}]({row['report']}) | {row['scenariosPassed']}/{row['scenariosTotal']} | {row['wraithExit']} | {row['upstream']['passed']} / {row['upstream']['skipped']} | {row['optimizedControl']['passed']}/2 | {row['strictWarningControl']['passed']}/1 |"
        )
    lines += [
        "",
        "The optimization-only fix exposes the callable crash. Wraith blocks two new error assertions even though ordinary and optimized function tests pass. Both affected scenarios already failed answer/check-count requirements before this change.",
        "",
        "The original baseline deliberately records failed requirements for diagnosis; it is not an approved CI baseline. Other partial fixes pass relative comparison while retaining debt. The combined fix passes all nine requirements and all selected upstream controls.",
        "",
        *assessment["limits"],
        "",
        "Raw logs, unchanged upstream tests, source fingerprints, native JSON/HTML history, and sealed attempts remain local. assessment.json omits local paths, environment values, and hostnames.",
    ]
    (root / "report.md").write_text("\n".join(lines) + "\n")
    return assessment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO / ".wraith/maintained-agent-study"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "reproduce"):
        setup = sub.add_parser(name)
        setup.add_argument("--binary", type=Path, default=REPO / "target/debug/wraith")
        setup.add_argument("--upstream", type=Path)
        setup.add_argument("--python", type=Path)
        setup.add_argument("--install", action="store_true")
    for name in ("candidate", "evaluate", "apply-reviewed"):
        sub.add_parser(name).add_argument("id")
    sub.add_parser("finish")
    sub.add_parser("verify")
    sub.add_parser("report")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command in ("prepare", "reproduce"):
        state = prepare(
            root, args.binary.resolve(), args.upstream, args.python, args.install
        )
        if args.command == "reproduce" and not (root / "completion.json").exists():
            if (root / "tasks").exists():
                raise ValueError(
                    "Incomplete tasks preserved; evaluate them explicitly or choose a new root"
                )
            for task in artifacts.read(root / "frozen/tasks.json"):
                apply_reviewed(root, task)
                validate_candidate(root, state, task)
                code = evaluate(root, state, task)
                if code not in (0, 1):
                    return code
                verify(root)
            finish(root, state)
        report(root, state)
        print(root / "report.md")
        return 0
    state = verify(root)
    if args.command == "verify":
        print("Frozen inputs, dependencies, baseline, and completed evidence verified")
        return 0
    if args.command == "report":
        report(root, state)
        print(root / "report.md")
        return 0
    if (root / "completion.json").exists():
        raise ValueError("Finite experiment complete; use an explicit new root")
    if args.command == "finish":
        finish(root, state)
        report(root, state)
        print(root / "completion.json")
        return 0
    task = task_for(root, args.id)
    if args.command == "candidate":
        candidate(root, task)
        return 0
    if args.command == "apply-reviewed":
        apply_reviewed(root, task)
        validate_candidate(root, state, task)
        return 0
    return evaluate(root, state, task)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
