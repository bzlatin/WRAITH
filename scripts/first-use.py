#!/usr/bin/env python3
"""Compare mechanical setup steps using frozen application-pilot fixtures offline."""

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "pilot", REPO / "scripts/coverage-challenge.py"
)
challenge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(challenge)
app, art = challenge.app, challenge.art


def step(binary, cwd, logs, name, args, expected, env=None):
    result = art.execute([binary, *args], logs, name, env, workdir=cwd)
    if result["exit"] != expected:
        raise ValueError(
            f"{name}: expected exit {expected}, got {result['exit']}; inspect {logs}"
        )
    return result


def arm(root, label, binary, python, scenarios, source):
    folder = root / label
    project = folder / "project"
    project.mkdir(parents=True)
    shutil.copytree(root / "frozen", folder / "frozen")
    cases = folder / "cases.json"
    art.save(cases, scenarios)
    phases = {}
    args = [
        "init",
        "--entrypoint",
        str(folder / "frozen/entrypoint.py") + ":evaluate",
        "--language",
        "python",
        "--runtime",
        python,
        "--model",
        "echo-offline-fixture",
    ]
    if label == "after":
        args += ["--cases", cases]
    phases["init"] = step(binary, project, folder, "init", args, 0)
    edits = []
    if label == "before":
        config = art.read(project / "wraith.yaml")
        config["tests"] = scenarios
        art.save(project / "wraith.yaml", config)
        edits.append("replace generated starter tests in config")
    env = app.environment(folder, source)
    phases["doctor"] = step(
        binary, project, folder, "doctor", ["doctor", "--output", "json"], 0, env
    )
    args = [
        "cases",
        "add",
        "--id",
        "repeated-denial",
        "--from-run",
        root / "source-run.json",
        "--scenario",
        "sync-cancel",
    ]
    expectations = {
        "json": [
            {"path": p, "check": {"op": "equals", "value": v}}
            for p, v in [
                ("/executions", 1),
                ("/results/0/output", "Cancelled: denied"),
                ("/receipts/0/value", 2),
                ("/blockedNetworkAttempts", 0),
            ]
        ]
    }
    if label == "before":
        expect = folder / "expect.json"
        art.save(expect, expectations)
        args += ["--expect", expect]
        edits.append("author separate expectation file")
    else:
        for p, value in [
            ("/executions", "1"),
            ("/results/0/output", '"Cancelled: denied"'),
            ("/receipts/0/value", "2"),
            ("/blockedNetworkAttempts", "0"),
        ]:
            args += ["--json-equals", p, value]
    phases["case"] = step(binary, project, folder, "case", args, 0)
    phases["baseline"] = step(
        binary, project, folder, "baseline", ["baseline", "--output", "json"], 0, env
    )
    baseline_id = art.read(folder / "baseline.stdout")["record"]["id"]
    changes = {c["id"]: c for c in art.read(folder / "frozen/changes.json")}
    original = (source / "llm/models.py").read_text()
    for name, mutation, expected in [
        ("harmless", "copy-arguments", 0),
        ("regression", "sync-approval-bypass", 1),
        ("restored", None, 0),
    ]:
        snapshot = folder / name / "source"
        shutil.copytree(source, snapshot)
        if mutation:
            (snapshot / "llm/models.py").write_text(
                challenge.mutate(original, changes[mutation])
            )
        manifest = art.manifest(snapshot)
        phases[name] = step(
            binary,
            project,
            folder,
            name,
            ["check", "--output", "json"],
            expected,
            app.environment(folder, snapshot),
        )
        result = art.read(folder / f"{name}.stdout")
        if (
            result["record"]["baselineId"] != baseline_id
            or art.manifest(snapshot) != manifest
        ):
            raise ValueError("Source or fixed baseline changed")
    result = {
        "phases": phases,
        "manualFileOperations": edits,
        "baselineId": baseline_id,
        "config": art.read(project / "wraith.yaml"),
    }
    art.save(folder / "result.json", result)
    art.save(folder / "evidence.json", art.manifest(folder))
    print(label, "workflow passed", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--resources", type=Path, default=REPO / ".wraith/coverage-expanded-validated"
    )
    parser.add_argument("--before-binary", type=Path, required=True)
    parser.add_argument("--binary", type=Path, default=REPO / "target/debug/wraith")
    args = parser.parse_args()
    root, resources = args.root.resolve(), args.resources.resolve()
    upstream = app.verify(resources)
    root.mkdir(parents=True, exist_ok=False)
    start = datetime.now(timezone.utc)
    shutil.copytree(resources / "frozen", root / "frozen")
    shutil.copytree(resources / "base", root / "base")
    shutil.copyfile(Path(__file__), root / "runner.py")
    baseline = (
        resources
        / "project/.wraith/history"
        / upstream["baselineResult"]["record"]["id"]
        / "run.json"
    )
    shutil.copyfile(baseline, root / "source-run.json")
    binaries = root / "binaries"
    binaries.mkdir()
    for label, source in [
        ("before", args.before_binary.resolve()),
        ("after", args.binary.resolve()),
    ]:
        shutil.copyfile(source, binaries / label)
        (binaries / label).chmod(0o755)
    scenarios = art.read(resources / "project/wraith.yaml")["tests"]
    results = {
        label: arm(
            root, label, binaries / label, upstream["python"], scenarios, root / "base"
        )
        for label in ("before", "after")
    }
    if results["before"]["config"]["tests"] != results["after"]["config"]["tests"]:
        raise ValueError("Before/after suites differ")
    # A real application utility, deliberately distinguished from agent orchestration.
    utility = root / "input-only-utility"
    utility.mkdir()
    cases = utility / "cases.json"
    art.save(
        cases,
        [
            {
                "id": "schema",
                "input": "name, age int",
                "expect": {
                    "json": [
                        {
                            "path": "/properties/age/type",
                            "check": {"op": "equals", "value": "integer"},
                        }
                    ]
                },
            }
        ],
    )
    phases = {}
    phases["init"] = step(
        binaries / "after",
        utility,
        utility,
        "init",
        [
            "init",
            "--entrypoint",
            "llm.utils:schema_dsl",
            "--input-only",
            "--runtime",
            upstream["python"],
            "--cases",
            cases,
        ],
        0,
    )
    phases["baseline"] = step(
        binaries / "after",
        utility,
        utility,
        "baseline",
        ["baseline", "--output", "json"],
        0,
        app.environment(root, root / "base"),
    )
    summary = {
        "schema": 1,
        "source": upstream["source"],
        "packages": upstream["packages"],
        "binaries": {
            label: art.digest(binaries / label) for label in ("before", "after")
        },
        "startedAt": start.isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "manualFileOperations": {
            label: len(r["manualFileOperations"]) for label, r in results.items()
        },
        "nativeCommandsPerWorkflow": len(results["after"]["phases"]),
        "utility": phases,
        "scope": "Assisted mechanical replay with pre-authored cases and existing adapter/dependencies; not human onboarding time, independent user success, natural bug discovery, or incremental detection.",
    }
    art.save(root / "summary.json", summary)
    (root / "report.md").write_text(
        "# Assisted first-use benchmark\n\nBoth workflows passed baseline, harmless change, the same seeded regression, and restoration against fixed eighteen-case suites.\n\n| Workflow | Native commands | Manual config/expectation file operations |\n| --- | --- | --- |\n| Before | 7 | 2 |\n| After | 7 | 0 |\n\nThe reviewed seventeen-case dataset, application wrapper, source, dependency environment, and regression witness were already available. Case construction uses explicit typed rules, never observed output as truth. This measures removed mechanical steps, not human authoring time or complete cold-start integration.\n\nThe input-only utility check connects unmodified LLM schema_dsl in two commands with no wrapper. It is an application utility, not an agent-quality evaluation. Native before/after reports are in each project/.wraith/history directory. Source snapshots and all command results remain local. No provider requests ran.\n"
    )
    art.save(root / "evidence.json", art.manifest(root))
    print(root / "report.md")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(error, file=sys.stderr)
        sys.exit(2)
