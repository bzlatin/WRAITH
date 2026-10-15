#!/usr/bin/env python3
"""Operate a finite offline support-agent trial; Codex edits isolated candidates."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import signal
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "examples/support-agent"
DEFAULT = REPO / ".wraith/trial"
SCHEMA = 1


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(directory):
    return {
        p.relative_to(directory).as_posix(): digest(p)
        for p in sorted(Path(directory).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and ".git" not in p.parts
    }


def identity(directory):
    return hashlib.sha256(
        json.dumps(manifest(directory), sort_keys=True).encode()
    ).hexdigest()


def copy_app(source, target):
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".wraith"),
    )


@contextmanager
def lock(root):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "trial.lock"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ValueError(
            f"Trial is locked: {path}. Verify the prior process stopped before removing its lock."
        ) from error
    try:
        with os.fdopen(fd, "w") as file:
            json.dump({"pid": os.getpid(), "startedAt": stamp()}, file)
        yield
    finally:
        path.unlink(missing_ok=True)


def load(root):
    state = read(root / "state.json")
    if state.get("version") != SCHEMA:
        raise ValueError("Unsupported trial state version")
    if manifest(root / "frozen") != state["frozenFiles"]:
        raise ValueError(
            "Frozen trial inputs changed; start a separate --root experiment"
        )
    if manifest(root / "baseline") != state["baselineFiles"]:
        raise ValueError("Baseline evidence or policy changed; refusing comparison")
    for task in state["tasks"]:
        for name in task["attempts"]:
            folder = root / "tasks" / task["id"] / name
            journal = folder / "attempt.json"
            if journal.is_file():
                attempt = read(journal)
                if attempt.get("status") == "complete" and "evidenceFiles" in attempt:
                    current = {
                        k: v
                        for k, v in manifest(folder).items()
                        if k not in ("attempt.json", "triage.json")
                    }
                    if current != attempt["evidenceFiles"]:
                        raise ValueError(
                            "Completed attempt evidence changed; refusing reuse"
                        )
    if digest(state["binary"]) != state["binarySha256"]:
        raise ValueError("Wraith binary changed; start a separate --root experiment")
    return state


def binary_path(argument):
    candidates = (
        [argument]
        if argument
        else [
            shutil.which("wraith"),
            Path.home() / ".local/bin/wraith",
            REPO / "target/debug" / ("wraith.exe" if os.name == "nt" else "wraith"),
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise ValueError("Install Wraith or supply --binary /path/to/wraith")


def execute(args, folder, label, cwd=None, timeout=None):
    # Do not serialize the inherited environment. Disable bytecode in disposable copies.
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    started = stamp()
    process = subprocess.Popen(
        [str(a) for a in args],
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **(
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {}
        ),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except (KeyboardInterrupt, subprocess.TimeoutExpired) as error:
        # Give Wraith time to execute its own contained-tree cleanup before fallback.
        if process.poll() is None:
            try:
                process.send_signal(
                    signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
                )
                process.communicate(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.communicate()
        if isinstance(error, KeyboardInterrupt):
            raise
        (folder / (label + ".stderr")).write_text(
            "Process exceeded its deadline.\n", encoding="utf-8"
        )
        return {"exit": 2, "startedAt": started, "endedAt": stamp(), "error": "timeout"}
    (folder / (label + ".stdout")).write_text(stdout, encoding="utf-8")
    (folder / (label + ".stderr")).write_text(stderr, encoding="utf-8")
    return {"exit": process.returncode, "startedAt": started, "endedAt": stamp()}


def unit(app, folder, label):
    return execute(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        folder,
        label,
        cwd=app,
        timeout=60,
    )


def run_config(frozen, app):
    suite = dict(
        version=1,
        agent=dict(timeout_ms=10000),
        tests=read(frozen / "app/contracts.json")["tests"],
    )
    suite["agent"]["command"] = shlex.join(
        [sys.executable, str(frozen / "invoke.py"), str(app)]
    )
    return suite


def start(root, argument):
    if (root / "state.json").exists():
        state = load(root)
        calibrate(root, state)
        render(root, state)
        return state
    if any(p.name != "trial.lock" for p in root.iterdir()):
        raise ValueError("Incomplete setup exists; preserve it and choose a new --root")
    contracts = read(APP / "contracts.json")
    queue = read(APP / "tasks.json")
    if contracts.get("version") != 1 or queue.get("version") != 1:
        raise ValueError("Unsupported application contract/task schema")
    ids = [t["id"] for t in queue["tasks"]]
    if (
        not ids
        or len(set(ids)) != len(ids)
        or any(not re.fullmatch(r"[a-z0-9_-]+", i) for i in ids)
    ):
        raise ValueError("Task IDs must be unique safe names")
    binary = binary_path(argument)
    version = subprocess.check_output([str(binary), "--version"], text=True).strip()
    frozen = root / "frozen"
    frozen.mkdir()
    copy_app(APP, frozen / "app")
    shutil.copyfile(
        REPO / "adapters/python/wraith_adapter.py", frozen / "wraith_adapter.py"
    )
    shutil.copyfile(REPO / "scripts/trial_acceptance.py", frozen / "acceptance.py")
    # One fresh subprocess per scenario; multiple requests share application session state.
    (frozen / "invoke.py").write_text(
        "import asyncio,sys\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\nsys.path.insert(0, str(Path(__file__).resolve().parent))\nfrom wraith_adapter import run\nasyncio.run(run('support_agent.agent:evaluate'))\n",
        encoding="utf-8",
    )
    baseline = root / "baseline"
    baseline.mkdir()
    suite = run_config(frozen, frozen / "app")
    save(baseline / "wraith.json", suite)
    base_unit = unit(frozen / "app", baseline, "unit")
    base_run = execute(
        [
            binary,
            "--config",
            baseline / "wraith.json",
            "run",
            "--save",
            "baseline",
            "--output",
            "json",
        ],
        baseline,
        "run",
    )
    if base_unit["exit"] or base_run["exit"]:
        raise ValueError(f"Baseline setup failed; inspect {baseline}")
    tasks = read(frozen / "app/tasks.json")["tasks"]
    state = dict(
        version=SCHEMA,
        id=uuid.uuid4().hex,
        createdAt=stamp(),
        binary=str(binary),
        binaryVersion=version,
        binarySha256=digest(binary),
        frozenFiles=manifest(frozen),
        baselineSource=identity(frozen / "app"),
        repositoryCommit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        repositoryDirty=bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=REPO, text=True
            ).strip()
        ),
        baselineUnit=base_unit,
        baselineRun=base_run,
        baselineFiles=manifest(baseline),
        setupComplete=False,
        tasks=[dict(t, status="pending", attempts=[]) for t in tasks],
        controls=[],
    )
    save(root / "state.json", state)
    calibrate(root, state)
    render(root, state)
    return state


def calibrate(root, state):
    # Controls exercise transport/evidence; they do not represent product validation.
    frozen = root / "frozen"
    for control in state["controls"]:
        if control["result"]["comparisonExit"] != control["expectedGate"]:
            raise ValueError(
                "Saved calibration failed; start a new experiment after fixing setup"
            )
    complete = {c["name"] for c in state["controls"]}
    for name in ["unchanged", "harmless-wording", "injected-ownership"]:
        if name in complete:
            continue
        control = root / "controls" / name
        control.mkdir(parents=True, exist_ok=True)
        if not (control / "candidate").exists():
            copy_app(frozen / "app", control / "candidate")
        if name == "harmless-wording":
            p = control / "candidate/support_agent/agent.py"
            s = (frozen / "app/support_agent/agent.py").read_text()
            s, count = re.subn(
                r"(['\"])text\1: document\[(['\"])text\2\]",
                lambda m: m.group(0).split(":", 1)[0]
                + ': "Here is the policy: " + document["text"]',
                s,
            )
            if count != 1:
                raise ValueError(
                    "Harmless calibration could not locate the answer rendering"
                )
            p.write_text(s)
        if name == "injected-ownership":
            p = control / "candidate/support_agent/orders.py"
            s = (frozen / "app/support_agent/orders.py").read_text()
            s, count = re.subn(
                r"order is None or order\[(['\"])customer\1\] != customer",
                "order is None",
                s,
            )
            if count != 1:
                raise ValueError(
                    "Fault calibration could not locate the ownership check"
                )
            p.write_text(s)
        number = 1
        while (control / f"attempt-{number:03}").exists():
            number += 1
        folder = control / f"attempt-{number:03}"
        result = evaluate_copy(
            root, state, control / "candidate", folder, None, "calibration"
        )
        expected = 1 if name == "injected-ownership" else 0
        if result["comparisonExit"] != expected or result["outcome"] in (
            "execution_error",
            "inconclusive",
        ):
            raise ValueError(f"Calibration failed: {name}; inspect {folder}")
        state["controls"].append(dict(name=name, expectedGate=expected, result=result))
        save(root / "state.json", state)
    state["setupComplete"] = True
    save(root / "state.json", state)


def validate_candidate(root, candidate):
    base = manifest(root / "frozen/app")
    current = manifest(candidate)
    if set(base) != set(current):
        raise ValueError(
            "Candidate file set changed; only existing application .py modules may be edited"
        )
    for name in base:
        if base[name] != current[name] and not (
            name.startswith("support_agent/") and name.endswith(".py")
        ):
            raise ValueError(f"Candidate changed frozen data/tests/policy: {name}")


def evaluate_copy(root, state, candidate, folder, task, category):
    folder.mkdir(parents=True, exist_ok=True)
    evaluation = folder / "evaluated"
    copy_app(candidate, evaluation)
    candidate_hash = identity(evaluation)
    snapshot_files = manifest(evaluation)
    candidate_unit = unit(evaluation, folder, "unit")
    acceptance = {"exit": 0}
    if task:
        acceptance = execute(
            [
                sys.executable,
                root / "frozen/acceptance.py",
                evaluation,
                root / "frozen/app/tasks.json",
                task["id"],
            ],
            folder,
            "acceptance",
            timeout=60,
        )
    suite = run_config(root / "frozen", evaluation)
    save(folder / "wraith.json", suite)
    run = execute(
        [
            state["binary"],
            "--config",
            folder / "wraith.json",
            "run",
            "--save",
            "candidate",
            "--output",
            "json",
        ],
        folder,
        "run",
    )
    comparison = execute(
        [
            state["binary"],
            "compare",
            root / "baseline/.wraith/runs/baseline.json",
            folder / ".wraith/runs/candidate.json",
            "--policy",
            root / "baseline/wraith.json",
            "--html",
            folder / "report.html",
            "--output",
            "json",
        ],
        folder,
        "comparison",
    )
    report = (
        read(folder / "comparison.stdout") if comparison["exit"] in (0, 1, 3) else {}
    )
    failures = [c for c in report.get("changes", []) if c.get("severity") == "failure"]
    outcome = (
        "execution_error"
        if run["exit"] not in (0, 1)
        or comparison["exit"] == 2
        or candidate_unit["exit"] not in (0, 1)
        or acceptance["exit"] not in (0, 1)
        else "inconclusive"
        if comparison["exit"] == 3
        else "needs_review"
        if comparison["exit"] == 1
        else "task_acceptance_failure"
        if acceptance["exit"]
        else "component_test_failure"
        if candidate_unit["exit"]
        else "no_observed_regression"
    )
    if manifest(evaluation) != snapshot_files:
        raise ValueError(
            "Application modified its evaluated source/data; result refused"
        )
    result = dict(
        version=SCHEMA,
        category=category,
        createdAt=stamp(),
        sourceSha256=candidate_hash,
        baselineSourceSha256=state["baselineSource"],
        binaryVersion=state["binaryVersion"],
        binarySha256=state["binarySha256"],
        runnerSha256=digest(Path(__file__)),
        phases={
            "componentTests": candidate_unit,
            "acceptance": acceptance,
            "wraithRun": run,
            "comparison": comparison,
        },
        baselineUnitExit=state["baselineUnit"]["exit"],
        unitExit=candidate_unit["exit"],
        acceptanceExit=acceptance["exit"],
        runExit=run["exit"],
        comparisonExit=comparison["exit"],
        outcome=outcome,
        failures=failures,
        report=str(folder / "report.html"),
        source=str(evaluation),
        mode="offline",
        liveBudgetEnabled=False,
    )
    save(folder / "result.json", result)
    return result


def next_task(root, state):
    for task in state["tasks"]:
        if task["status"] == "complete":
            continue
        directory = root / "tasks" / task["id"]
        candidate = directory / "candidate"
        if not candidate.exists():
            directory.mkdir(parents=True, exist_ok=True)
            copy_app(root / "frozen/app", candidate)
        task["status"] = "in_progress"
        save(root / "state.json", state)
        prompt = f"Task: {task['title']}\n\nEdit only existing Python modules under {candidate / 'support_agent'}.\nRead the frozen requirements in {candidate / 'requirements.md'}. Preserve original tests, data, and contracts.\nImplement the feature correctly; do not introduce deliberate regressions.\nRun python3 scripts/trial.py --root {root} evaluate\nInvestigate any failures before marking the task complete.\n"
        (directory / "task.md").write_text(prompt, encoding="utf-8")
        render(root, state)
        return dict(
            task=task["id"],
            title=task["title"],
            candidate=str(candidate),
            instructions=str(directory / "task.md"),
        )
    render(root, state)
    return dict(status="complete", report=str(root / "report.md"))


def active(state):
    return next((t for t in state["tasks"] if t["status"] == "in_progress"), None)


def evaluate(root, state):
    task = active(state)
    if not task:
        raise ValueError("Run next to claim a task first")
    directory = root / "tasks" / task["id"]
    candidate = directory / "candidate"
    validate_candidate(root, candidate)
    source = identity(candidate)
    for attempt in task["attempts"]:
        path = directory / attempt / "result.json"
        if (
            path.is_file()
            and (directory / attempt / "attempt.json").is_file()
            and read(directory / attempt / "attempt.json")["status"] == "complete"
            and read(path)["sourceSha256"] == source
        ):
            task["currentAttempt"] = attempt
            save(root / "state.json", state)
            print("Reusing immutable result:", path)
            return read(path)
    number = 1
    while (directory / f"attempt-{number:03}").exists():
        number += 1
    folder = directory / f"attempt-{number:03}"
    folder.mkdir()
    task["attempts"].append(folder.name)
    task["currentAttempt"] = folder.name
    save(root / "state.json", state)
    save(
        folder / "attempt.json",
        dict(startedAt=stamp(), status="started", sourceSha256=source),
    )
    try:
        result = evaluate_copy(
            root, state, candidate, folder, task, "codex_development"
        )
    except KeyboardInterrupt:
        save(folder / "attempt.json", dict(status="interrupted", sourceSha256=source))
        raise
    if identity(candidate) != source:
        save(
            folder / "attempt.json",
            dict(status="candidate_changed", sourceSha256=source),
        )
        raise ValueError("Candidate changed during evaluation; result not accepted")
    save(
        folder / "attempt.json",
        dict(
            status="complete",
            startedAt=read(folder / "attempt.json").get("startedAt"),
            endedAt=stamp(),
            sourceSha256=source,
            evidenceFiles={
                k: v
                for k, v in manifest(folder).items()
                if k not in ("attempt.json", "triage.json")
            },
        ),
    )
    render(root, state)
    return result


def finish(root, state):
    task = active(state)
    if not task or not task["attempts"]:
        raise ValueError("No evaluated active task")
    directory = root / "tasks" / task["id"]
    result = read(
        directory / task.get("currentAttempt", task["attempts"][-1]) / "result.json"
    )
    if result["outcome"] != "no_observed_regression":
        raise ValueError(
            "Resolve failed/inconclusive checks before completing the task"
        )
    if identity(directory / "candidate") != result["sourceSha256"]:
        raise ValueError("Candidate changed since evaluation")
    task["status"] = "complete"
    save(root / "state.json", state)
    render(root, state)
    return dict(
        completed=task["id"],
        remaining=sum(t["status"] != "complete" for t in state["tasks"]),
    )


def triage(root, state, file):
    value = read(file)
    task = active(state)
    if not task or not task["attempts"]:
        raise ValueError("No attempt to triage")
    folder = (
        root / "tasks" / task["id"] / task.get("currentAttempt", task["attempts"][-1])
    )
    result = read(folder / "result.json")
    allowed = [
        "actionable_regression",
        "false_alarm",
        "known_debt",
        "execution_error",
        "unresolved",
    ]
    if (
        value.get("classification") not in allowed
        or not value.get("reason")
        or not value.get("evidence")
    ):
        raise ValueError(
            "Triage requires classification, reason, and concrete evidence"
        )
    if (
        value["classification"] in ("actionable_regression", "false_alarm")
        and result["comparisonExit"] != 1
    ):
        raise ValueError("This attempt has no failing regression gate")
    # Reasons and evidence are preserved as provisional agent judgment, not oracle labels.
    path = folder / "triage.json"
    if path.exists():
        raise ValueError("Triage is immutable; preserve the original interpretation")
    save(path, dict(value, version=SCHEMA, provisional=True, createdAt=stamp()))
    render(root, state)
    return dict(triage=str(path))


def render(root, state):
    observations = []
    for task in state["tasks"]:
        for attempt in task["attempts"]:
            folder = root / "tasks" / task["id"] / attempt
            if (folder / "result.json").is_file():
                observations.append((task, folder, read(folder / "result.json")))
    reviewed = []
    for task, folder, result in observations:
        if (folder / "triage.json").is_file():
            reviewed.append((result, read(folder / "triage.json")))
    unique = [
        (r, t)
        for r, t in reviewed
        if t["classification"] == "actionable_regression" and r["unitExit"] == 0
    ]
    complete = all(t["status"] == "complete" for t in state["tasks"])
    recommendation = (
        "Investigate the reproducible workflow findings in an independent agent next."
        if unique
        else "Insufficient evidence of incremental value: no reviewed regression beyond component tests."
        if complete
        else "Trial in progress; no product verdict yet."
    )
    lines = [
        "# Automated support-agent trial",
        "",
        f"Experiment: `{state['id']}`",
        f"Wraith: {state['binaryVersion']}",
        "Scope: offline mock application; Codex-created changes and provisional triage. No adoption or live-model accuracy claims.",
        "",
        f"Completed tasks: {sum(t['status'] == 'complete' for t in state['tasks'])}/{len(state['tasks'])}",
        f"Development comparisons completed: {len(observations)}",
        f"Reviewed failing comparisons: {len(reviewed)}",
        f"Reviewed actionable regression comparisons beyond component tests: {len(unique)}",
        "Mode: offline fixture with no provider backend; not a network sandbox.",
        "",
        "## Calibration controls",
        "",
    ]
    for control in state["controls"]:
        lines.append(
            f"- {control['name']}: gate {control['result']['comparisonExit']} (expected {control['expectedGate']}); component tests {control['result']['unitExit']}."
        )
    lines += [
        "",
        "## Development evidence",
        "",
        "| Task / attempt | Component exit | Acceptance exit | Wraith exit | Outcome |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task, folder, r in observations:
        link = os.path.relpath(
            folder / "report.html" if (folder / "report.html").exists() else folder,
            root,
        ).replace(os.sep, "/")
        lines.append(
            f"| [{task['id']} / {folder.name}]({link}) | {r['unitExit']} | {r['acceptanceExit']} | {r['comparisonExit']} | {r['outcome']} |"
        )
    measured = []
    for _, _, result in observations:
        phases = result.get("phases", {})
        if phases:
            durations = [
                (
                    datetime.fromisoformat(p["endedAt"])
                    - datetime.fromisoformat(p["startedAt"])
                ).total_seconds()
                for p in phases.values()
                if "startedAt" in p and "endedAt" in p
            ]
            measured.append(sum(durations))
    if measured:
        lines.append(
            f"Measured subprocess time: {sum(measured):.2f}s across {len(measured)}/{len(observations)} comparisons with timing records."
        )
    lines += ["", "Reviewed classifications (per failing comparison):"]
    if reviewed:
        for classification in [
            "actionable_regression",
            "false_alarm",
            "known_debt",
            "execution_error",
            "unresolved",
        ]:
            lines.append(
                f"- {classification}: {sum(t['classification'] == classification for _, t in reviewed)}/{len(reviewed)} reviewed comparisons"
            )
    else:
        lines.append(
            "No failing comparisons reviewed; false-alarm frequency is unknown."
        )
    lines.append(
        f"Unreviewed failing regression comparisons: {sum(r['comparisonExit'] == 1 and not (f / 'triage.json').exists() for _, f, r in observations)}"
    )
    lines += [
        "",
        "## Decision",
        "",
        recommendation,
        "",
        "False alarms and useful catches require reviewed evidence; unreviewed failures stay unresolved.",
        "Passing development tasks show repeatable operation, not independent customer value. Baselines and prior decisions remain fixed.",
    ]
    (root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT)
    parser.add_argument("--binary", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["start", "next", "evaluate", "finish", "status"]:
        sub.add_parser(name)
    tri = sub.add_parser("triage")
    tri.add_argument("file", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    with lock(root):
        if args.command == "start":
            result = start(root, args.binary)
        else:
            state = load(root)
            if not state["setupComplete"]:
                raise ValueError("Calibration is incomplete; resume with start")
            if args.command == "next":
                result = next_task(root, state)
            elif args.command == "evaluate":
                result = evaluate(root, state)
            elif args.command == "finish":
                result = finish(root, state)
            elif args.command == "triage":
                result = triage(root, state, args.file)
            else:
                render(root, state)
                result = dict(
                    tasks=[
                        {"id": t["id"], "status": t["status"]} for t in state["tasks"]
                    ],
                    report=str(root / "report.md"),
                )
    if args.command == "start":
        print(
            json.dumps(
                {
                    "experiment": result["id"],
                    "report": str(root / "report.md"),
                    "next": "python3 scripts/trial.py next",
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(result, indent=2))
    if args.command == "evaluate":
        return (
            0
            if result["outcome"] == "no_observed_regression"
            else (
                3
                if result["outcome"] == "inconclusive"
                else 2
                if result["outcome"] == "execution_error"
                else 1
            )
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (
        ValueError,
        OSError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as error:
        print(f"Trial setup/execution error: {error}", file=sys.stderr)
        sys.exit(2)
