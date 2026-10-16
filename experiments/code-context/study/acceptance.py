"""Unchanged upstream acceptance files with an explicit isolated runner config.

This selected subset is not the repositories' full CI or type-checking commands.
"""
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from mcp_client import clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TOOLS = HERE / "tools"


def check_hashes(folder, task):
    import hashlib
    for file, expected in task["acceptance_sha256"].items():
        if hashlib.sha256((folder / file).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen acceptance test changed")


def prepare(folder, task, root, fixed=False):
    folder = folder.resolve()
    if folder.exists():
        raise ValueError("Preserve old worktrees: destination already exists")
    commit = task["fix_commit"] if fixed else task["base_commit"]
    subprocess.run(["git", "-c", "core.hooksPath=", "-C", str(root / task["repository"]), "worktree", "add", "--detach", str(folder), commit],
                   check=True, capture_output=True, text=True, env=clean_env())
    for file in task["acceptance_test_paths"]:
        raw = subprocess.check_output(["git", "-C", str(root / task["repository"]), "show", task["fix_commit"] + ":" + file])
        (folder / file).write_bytes(raw)
    runner = TOOLS / "zod" if task["repository"] == "zod" else TOOLS
    (folder / "node_modules").symlink_to(runner / "node_modules", target_is_directory=True)
    # Serena baseline is given a matched, explicit TypeScript-only setup.
    (folder / ".serena").mkdir(exist_ok=True)
    (folder / ".serena/project.yml").write_text("project_name: " + folder.name + "\nlanguage_servers:\n- typescript\nencoding: utf-8\n")
    check_hashes(folder, task)


def capture(command, folder, timeout=90):
    started = time.monotonic()
    process = None
    if os.name != 'posix':
        raise RuntimeError('Historical test controller requires POSIX process-group containment')
    try:
        process = subprocess.Popen(command, cwd=folder, env=clean_env(), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            record = dict(status="passed" if process.returncode == 0 else "failed", exit_code=process.returncode,
                          stdout=stdout, stderr=stderr)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=5)
            record = dict(status="execution_error", error="Test process group exceeded its deadline and was terminated",
                          stdout=stdout, stderr=stderr)
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    record["seconds"] = time.monotonic() - started
    return record


def run(folder, task, artifact):
    if artifact.exists() or artifact.with_suffix('.config.mjs').exists():
        raise ValueError('Preserve old acceptance evidence: choose a new artifact path')
    check_hashes(folder, task)
    runner = TOOLS / "zod" if task["repository"] == "zod" else TOOLS
    config = artifact.with_suffix(".config.mjs")
    config.parent.mkdir(parents=True, exist_ok=True)
    # Explicit mapping to checked-in source; no generated build output or provider
    # substitutions. Tests and application modules are not rewritten by the runner.
    aliases = [
        dict(find="zod/v4", replacement=str(folder / "packages/zod/src/v4/index.ts")),
        dict(find="zod", replacement=str(folder / "packages/zod/src/index.ts")),
    ]
    code = "export default " + json.dumps(dict(root=str(folder), resolve=dict(alias=aliases),
        test=dict(globals=True, environment="node", include=task["acceptance_test_paths"],
                  testTimeout=10000, hookTimeout=10000, maxWorkers=1)))
    # Regex alias handles tRPC's documented source imports.
    code += ";\n"
    if task["repository"] == "trpc":
        code = code.replace('"alias": [', '"alias": [{find:/^@trpc\\/server\\/(.*)$/,replacement:' + json.dumps(str(folder / "packages/server/src") + '/$1') + '},')
        # Match vitest.shared.ts at the frozen upstream commit; never update the
        # test's inline snapshots to accommodate a different formatter.
        code = code.replace('"globals": true', '"globals": true, "snapshotFormat":{"printBasicPrototype":true}, "restoreMocks":true')
    config.write_text(code)
    node = os.environ.get("WRAITH_STUDY_NODE", "node")
    command = [node, str(runner / "node_modules/vitest/vitest.mjs"), "run", "--config", str(config), "--configLoader", "native"]
    started = time.monotonic()
    record = capture(command, folder)
    record.update(schema_version=1, task=task["id"], seconds=time.monotonic() - started,
                  command=command, scope="Selected unchanged upstream acceptance file; explicit external config; no full project CI/type checking")
    check_hashes(folder, task)
    artifact.write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    root = (REPO / ".wraith/code-context-study").resolve()
    tasks = json.loads((HERE / "agent-tasks.json").read_text())["tasks"]
    for task in tasks:
        for state in ("base", "fixed"):
            folder = root / "qualification" / (task["repository"] + "-" + state)
            prepare(folder, task, root, fixed=state == "fixed")
            result = run(folder, task, root / "qualification" / (task["repository"] + "-" + state + ".json"))
            print(task["repository"], state, result["status"], round(result["seconds"], 2), flush=True)
