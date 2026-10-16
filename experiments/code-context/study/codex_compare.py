"""Finite actual Codex/MCP study. Never invokes an API-key benchmark runner.

Qualification and model execution are separate explicit commands. Completed or
interrupted evidence is never overwritten. The controller requires POSIX groups.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import acceptance
from mcp_client import clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ROOT = REPO / ".wraith/code-context-study"
OUTPUT = ROOT / "actual-codex-mcp-2026-10-16"
PROTOCOL = HERE / "codex-protocol.json"
TASKS = HERE / "codex-tasks.json"
NODE = Path(os.environ.get("WRAITH_STUDY_NODE", "node"))
CODEX = Path(os.environ.get("WRAITH_STUDY_CODEX", "codex"))
PAYLOAD = REPO / ".wraith/code-context-preview/install-smoke-home/lib/wraith-context"


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as file:
        json.dump(value, file, indent=2)
        file.write("\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    """Metadata and frozen test bytes only; do not read future production code."""
    protocol = json.loads(PROTOCOL.read_text())
    specs = [
        ("hono", "ae401f080004872678100e890fd3398d3df09e67", "src/helper/css/common.ts",
         ["src/helper/css/index.test.tsx", "src/helper/css/common.case.test.tsx"]),
        ("zod", "dcbcf0529ca1e5424541d5d4b58e0a7b79507f51", "packages/zod/src/v4/core/doc.ts",
         ["packages/zod/src/v4/core/tests/compile.test.ts", "packages/zod/src/v4/core/tests/compile-global.test.ts"]),
    ]
    tasks = []
    for name, fix, module, tests in specs:
        def git(*args):
            return subprocess.check_output(["git", "-C", str(ROOT / name), *args])
        task = dict(id=name + "-actual-codex", repository=name, fix_commit=fix,
                    base_commit=git("rev-parse", fix + "^").decode().strip(),
                    task=git("show", "-s", "--format=%s", fix).decode().strip(),
                    approved_edit_paths=[module], acceptance_test_paths=tests,
                    acceptance_sha256={p: hashlib.sha256(git("show", fix + ":" + p)).hexdigest() for p in tests},
                    classification="Historical reproduction; new task paths, not blind discovery or customer evidence")
        tasks.append(task)
    if TASKS.exists():
        if json.loads(TASKS.read_text()) != dict(schema_version=1, tasks=tasks):
            raise ValueError("Existing frozen tasks differ")
    else:
        write_new(TASKS, dict(schema_version=1, tasks=tasks))
    write_new(OUTPUT / "frozen.json", dict(protocol=protocol, protocol_sha256=digest(PROTOCOL),
        tasks_sha256=digest(TASKS), engine_sha256={p: digest(HERE.parent / p) for p in
            ["cli.cjs", "lib/index.cjs", "lib/repository.cjs"]},
        bundle_sha256=digest(PAYLOAD / "wraith-context.cjs")))


def frozen():
    record = json.loads((OUTPUT / "frozen.json").read_text())
    if record["protocol_sha256"] != digest(PROTOCOL) or record["tasks_sha256"] != digest(TASKS):
        raise ValueError("Frozen protocol/tasks changed")
    for path, sha in record["engine_sha256"].items():
        if digest(HERE.parent / path) != sha:
            raise ValueError("Frozen retrieval implementation changed")
    if digest(PAYLOAD / "wraith-context.cjs") != record["bundle_sha256"]:
        raise ValueError("Installed preview changed")
    return record, {t["repository"]: t for t in json.loads(TASKS.read_text())["tasks"]}


def qualify():
    _, tasks = frozen()
    records = []
    for task in tasks.values():
        for state in ["base", "fixed"]:
            folder = OUTPUT / "qualification" / (task["repository"] + "-" + state)
            acceptance.prepare(folder, task, ROOT, fixed=state == "fixed")
            result = run_acceptance(folder, task, folder.with_suffix(".json"))
            records.append(dict(repository=task["repository"], state=state, status=result["status"]))
            print(task["repository"], state, result["status"], flush=True)
    qualified = all(r["status"] == ("failed" if r["state"] == "base" else "passed") for r in records)
    write_new(OUTPUT / "qualification.json", dict(qualified=qualified, records=records))


def run_acceptance(folder, task, artifact):
    """Explicit source aliases and upstream helper-file exclusion, no test edits."""
    acceptance.check_hashes(folder, task)
    config = artifact.with_suffix(".config.mjs")
    runner = acceptance.TOOLS / "zod" if task["repository"] == "zod" else acceptance.TOOLS
    aliases = {"zod/compile": "packages/zod/src/compile.ts", "zod/v4/core": "packages/zod/src/v4/core/index.ts",
               "zod/v4": "packages/zod/src/v4/index.ts", "zod": "packages/zod/src/index.ts"}
    data = dict(root=str(folder), resolve=dict(alias=[dict(find=k, replacement=str(folder / v)) for k, v in aliases.items()]),
                test=dict(globals=True, environment="node", include=task["acceptance_test_paths"],
                          exclude=["**/*.case.test.*"], testTimeout=10000, hookTimeout=10000, maxWorkers=1))
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open("x") as file:
        file.write("export default " + json.dumps(data) + ";\n")
    command = [str(NODE), str(runner / "node_modules/vitest/vitest.mjs"), "run", "--config", str(config), "--configLoader", "native"]
    result = acceptance.capture(command, folder)
    acceptance.check_hashes(folder, task)
    write_new(artifact, dict(schema_version=1, scope="Unchanged selected tests, explicit source aliases; imported helper excluded as standalone suite following upstream", **result))
    return result


def events_summary(events):
    completed = [e for e in events if e.get("type") == "item.completed"]
    tools = [e["item"] for e in completed if e.get("item", {}).get("type") == "mcp_tool_call"]
    commands = [e["item"] for e in completed if e.get("item", {}).get("type") == "command_execution"]
    turns = [e for e in events if e.get("type") == "turn.completed"]
    return dict(mcp_calls=[dict(server=t.get("server"), tool=t.get("tool"), status=t.get("status"),
                               error=t.get("error"), result_is_error=(t.get("result") or {}).get("isError")) for t in tools],
                command_count=len(commands), usage=[e.get("usage") for e in turns],
                turn_completed=bool(turns), turn_failed=any(e.get("type") == "turn.failed" for e in events))


def execute():
    record, tasks = frozen()
    protocol = record["protocol"]
    if not json.loads((OUTPUT / "qualification.json").read_text())["qualified"]:
        raise ValueError("Qualification failed: no model sessions authorized by protocol")
    attempted = sum(len(list(path.glob("sessions/*.started.json"))) for path in ROOT.glob("actual-codex-mcp*"))
    if len(protocol["order"]) > protocol["maximum_sessions"] or attempted + len(protocol["order"]) > 8:
        raise ValueError("Shared eight-session ceiling would be exceeded; failed attempts remain consumed")
    # Exclusive sentinel survives interruption. No retry/resume entry point.
    write_new(OUTPUT / "attempted.json", dict(maximum_sessions=protocol["maximum_sessions"], started=True))
    stopped = False
    for number, (name, lane, repetition) in enumerate(protocol["order"], 1):
        result_path = OUTPUT / "sessions" / f"{number:02d}-{name}-{lane}-{repetition}.json"
        if stopped:
            write_new(result_path, dict(status="not_run_after_stop", repository=name, lane=lane, repetition=repetition))
            continue
        task = tasks[name]
        auth = subprocess.run([str(CODEX), "login", "status"], env=clean_env(), capture_output=True, text=True, timeout=20)
        if auth.returncode or "Logged in using ChatGPT" not in auth.stdout + auth.stderr:
            write_new(result_path, dict(status="authentication_blocked", repository=name, lane=lane, repetition=repetition))
            stopped = True
            continue
        folder = OUTPUT / "worktrees" / result_path.stem
        acceptance.prepare(folder, task, ROOT)
        prompt = ("Implement this bug fix in this checkout: " + task["task"] + "\n"
                  "Use the current source and tests. Do not inspect Git history, future commits, other worktrees or external sources. "
                  "Do not change tests, configuration or dependencies. Only edit the production module that needs the fix. "
                  "The controller will run unchanged upstream tests after you finish. Keep the patch minimal.\n")
        if lane == "context":
            prompt += "Before editing, call the Wraith MCP code_context tool with this task; use native search if needed.\n"
        else:
            prompt += "Before editing, locate the relevant code using your native search tools.\n"
        command = [str(CODEX), "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--json",
                   "--sandbox", "workspace-write", "-C", str(folder), "--model", protocol["model"]]
        settings = dict(forced_login_method="chatgpt", model_provider="openai", model_reasoning_effort=protocol["reasoning_effort"],
                        approval_policy="never", web_search="disabled", project_doc_max_bytes=0,
                        **{"features.multi_agent": False, "features.apps": False})
        if lane == "context":
            settings.update({"mcp_servers.wraith_context.command": str(NODE),
                             "mcp_servers.wraith_context.args": [str(PAYLOAD / "wraith-context.cjs"), "mcp", "--root", str(folder)],
                             "mcp_servers.wraith_context.required": True})
        for key, value in settings.items():
            command += ["-c", key + "=" + json.dumps(value)]
        command += ["-"]
        write_new(result_path.with_suffix(".started.json"), dict(repository=name, lane=lane, repetition=repetition,
            command=command, prompt=prompt, auth="ChatGPT", protocol_sha256=record["protocol_sha256"]))
        stdout_path = result_path.with_suffix(".events.jsonl")
        stderr_path = result_path.with_suffix(".stderr.txt")
        started = time.monotonic()
        timed_out = False
        with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
            process = subprocess.Popen(command, cwd=folder, env=clean_env(), stdin=subprocess.PIPE,
                stdout=out, stderr=err, start_new_session=True)
            try:
                process.communicate(prompt.encode(), timeout=protocol["session_timeout_seconds"])
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
        seconds = time.monotonic() - started
        events = [json.loads(line) for line in stdout_path.read_text().splitlines() if line.strip()]
        summary = events_summary(events)
        changed = subprocess.check_output(["git", "-C", str(folder), "diff", "--name-only"], text=True).splitlines()
        # Frozen tests copied from the fix are expected modifications to base.
        disallowed = sorted(set(changed) - set(task["approved_edit_paths"]) - set(task["acceptance_test_paths"]))
        patch = subprocess.check_output(["git", "-C", str(folder), "diff", "--", *task["approved_edit_paths"]])
        result_path.with_suffix(".patch").write_bytes(patch)
        try:
            checked = run_acceptance(folder, task, result_path.with_suffix(".acceptance.json"))
            status = "passed" if checked["status"] == "passed" and not disallowed and patch else "failed"
        except ValueError:
            status = "frozen_test_changed"
        if timed_out or process.returncode or not summary["turn_completed"] or summary["turn_failed"]:
            status = "timeout" if timed_out else "execution_error"
            stopped = True
        result = dict(repository=name, lane=lane, repetition=repetition, status=status, seconds=seconds,
                      exit_code=process.returncode, disallowed_paths=disallowed, patch_sha256=hashlib.sha256(patch).hexdigest(), **summary)
        write_new(result_path, result)
        print(result_path.stem, status, round(seconds, 2), summary["mcp_calls"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "qualify", "execute"])
    parser.add_argument("--supported-model", action="store_true", help="Explicit preflight repair variant; original attempt remains immutable")
    parser.add_argument("--compatible-model", action="store_true", help="Final compatibility repair inside the shared eight-session ceiling")
    args = parser.parse_args()
    if args.supported_model:
        OUTPUT = ROOT / "actual-codex-mcp-supported-2026-10-16"
        PROTOCOL = HERE / "codex-supported-model-protocol.json"
    if args.compatible_model:
        OUTPUT = ROOT / "actual-codex-mcp-compatible-2026-10-16"
        PROTOCOL = HERE / "codex-compatible-model-protocol.json"
    if os.name != "posix":
        raise SystemExit("This experiment controller requires POSIX containment")
    {"freeze": freeze, "qualify": qualify, "execute": execute}[args.action]()
