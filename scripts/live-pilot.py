#!/usr/bin/env python3
"""Prepare or execute one explicitly authorized, fixed 40-request live pilot."""

import argparse
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "pilot_artifacts", REPO / "scripts/historical-pilot.py"
)
art = importlib.util.module_from_spec(spec)
spec.loader.exec_module(art)


def budget(root):
    marker = root / "project/.wraith/live-baseline-attempt.json"
    if not marker.exists():
        return None
    identity = art.read(marker)["budgetId"]
    path = root / "project/.wraith/history" / identity / "request-budget.json"
    return {"id": identity, **art.read(path)}


def verify(root):
    state = art.read(root / "state.json")
    if state["schema"] != 1 or state["cap"] != 40:
        raise ValueError("Unsupported pilot state")
    if art.digest(Path(state["binary"])) != state["binarySha256"]:
        raise ValueError("Pilot binary changed")
    if art.manifest(root / "frozen") != state["frozen"]:
        raise ValueError("Frozen cases, agent, or prompt versions changed")
    for name, digest in state["projectFiles"].items():
        if art.digest(root / "project" / name) != digest:
            raise ValueError("Trusted project files changed")
    if (root / "completion.json").exists():
        saved = art.read(root / "completion.json")
        if art.manifest(root / "project/.wraith/history") != saved["history"]:
            raise ValueError("Completed live evidence changed")
    return state


def prepare(root, binary):
    if root.exists():
        raise ValueError("Existing root retained; choose an explicit new experiment")
    root.mkdir(parents=True)
    shutil.copytree(
        REPO / "examples/live-agent",
        root / "frozen",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    executable = root / ("wraith.exe" if os.name == "nt" else "wraith")
    shutil.copyfile(binary, executable)
    executable.chmod(0o755)
    project = root / "project"
    project.mkdir()
    phases = {
        "init": art.execute(
            [
                executable,
                "init",
                "--entrypoint",
                str(root / "frozen/agent.py") + ":evaluate",
                "--runtime",
                sys.executable,
                "--mode",
                "live",
                "--model",
                "gpt-4.1-mini-2025-04-14",
                "--require-env",
                "OPENAI_API_KEY",
                "--cases",
                root / "frozen/cases.json",
            ],
            project,
            "init",
        )
    }
    if phases["init"]["exit"] != 0:
        raise ValueError("Native initialization failed; preserve this root")
    phases["doctor"] = art.execute(
        [executable, "doctor", "--output", "json"], project, "doctor"
    )
    state = {
        "schema": 1,
        "cap": 40,
        "binary": str(executable),
        "binarySha256": art.digest(executable),
        "frozen": art.manifest(root / "frozen"),
        "projectFiles": {
            name: art.digest(project / name)
            for name in ("wraith.yaml", "wraith.project.json", "wraith_adapter.py")
        },
        "phases": phases,
        "plan": "10 cases, baseline then shorter equivalent prompt, one observation each; max two attempts per case; no retries or extra comparisons",
        "preparedAt": datetime.now(timezone.utc).isoformat(),
    }
    art.save(root / "state.json", state)
    print(root / "state.json")


def run(root, authorize):
    if not authorize:
        raise ValueError("Live calls require explicit --allow-live authorization")
    state = verify(root)
    if (root / "attempt.json").exists():
        raise ValueError(
            "Live experiment already attempted; preserve its budget and results"
        )
    if state["phases"]["doctor"]["exit"] != 0:
        raise ValueError(
            "Doctor failed; fix setup in a separately authorized new experiment"
        )
    art.save(
        root / "attempt.json",
        {
            "cap": 40,
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "automaticRetries": False,
        },
    )
    shutil.copyfile(Path(__file__), root / "runner.py")
    phases = {}
    for phase, args in [
        (
            "baseline",
            ["baseline", "--allow-live", "--max-requests", "40", "--output", "json"],
        ),
        ("candidate", ["check", "--allow-live", "--output", "json"]),
    ]:
        env = dict(os.environ)
        env.pop("WRAITH_REQUEST_BUDGET", None)
        env["WRAITH_LIVE_VARIANT"] = phase
        phases[phase] = art.execute(
            [state["binary"], *args],
            root,
            phase,
            env,
            timeout=1200,
            workdir=root / "project",
        )
        if phases[phase]["exit"] not in (0, 1):
            break
    observed = budget(root)
    if observed and not 0 <= observed["used"] <= observed["limit"] == 40:
        raise ValueError("Budget invariant violated")
    result = {
        "schema": 1,
        "phases": phases,
        "budget": observed,
        "history": art.manifest(root / "project/.wraith/history"),
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    art.save(root / "completion.json", result)
    lines = [
        "# Live support-agent pilot",
        "",
        state["plan"],
        "",
        "Actual OpenAI tool selection and final JSON answers; synthetic requests, policy documents, and in-memory actions. No production or customer application is tested.",
        "",
        "| Version | Exit | Passing scenarios | Recorded provider attempts |",
        "| --- | --- | --- | --- |",
    ]
    reports = []
    for phase, outcome in phases.items():
        p = root / f"{phase}.stdout"
        value = art.read(p) if p.stat().st_size else {}
        scenarios = value.get("run", {}).get("scenarios", [])
        passed = sum(s["passed"] for s in scenarios)
        calls = sum(
            s["run"]
            .get("response", {})
            .get("metadata", {})
            .get("wraith", {})
            .get("modelCalls", 0)
            for s in scenarios
            if s["run"].get("response")
        )
        lines.append(
            f"| {phase} | {outcome['exit']} | {passed}/{len(scenarios)} | {calls} |"
        )
        if value.get("report"):
            reports.append(
                f"[{phase} native report]({Path(value['report']).relative_to(root)})"
            )
    lines += ["", *reports]
    lines += [
        "",
        f"Shared budget: {observed}.",
        "",
        "A request is reserved before HTTP, including failed attempts. No automatic retries. A provider error stops subsequent requests. The budget is authoritative when an interrupted/error response lacks usage metadata. One observation per case is a functional smoke check, not an accuracy estimate or statistical evidence of a regression. A new failure must be reviewed against tool evidence; this cannot separate prompt effects from model variability. The candidate is an intended equivalent prompt refactor, not an injected fault or independent customer change.",
    ]
    (root / "report.md").write_text("\n".join(lines) + "\n")
    verify(root)
    print(root / "report.md")
    exits = [phase["exit"] for phase in phases.values()]
    return 2 if any(code not in (0, 1, 3) for code in exits) else exits[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO / ".wraith/live-support")
    parser.add_argument("--binary", type=Path, default=REPO / "target/debug/wraith")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare")
    sub.add_parser("run").add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root.resolve(), args.binary.resolve())
        return 0
    return run(args.root.resolve(), args.allow_live)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        sys.exit(2)
