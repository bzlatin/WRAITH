"""Verify selected upstream test commands inside actual Codex sandbox, no model.

Creates new disposable worktrees and preserves results. The selected test files
are unchanged; Hono's imported helper is excluded as a standalone test suite.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "study"))
import acceptance
import codex_compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--node", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tasks = json.loads((HERE.parent / "study/codex-tasks.json").read_text())["tasks"]
    root = HERE.parents[2] / ".wraith/code-context-study"
    records = []
    for task in tasks:
        for state in ("base", "fixed"):
            folder = output / (task["repository"] + "-" + state)
            acceptance.prepare(folder, task, root, fixed=state == "fixed")
            # Generate and validate the same selected-test config outside the
            # sandbox first, retaining that control separately.
            artifact = output / (folder.name + "-host.json")
            host = codex_compare.run_acceptance(folder, task, artifact)
            config = folder / ".wraith-study/vitest.config.mjs"
            config.parent.mkdir()
            shutil.copyfile(artifact.with_suffix(".config.mjs"), config)
            runner = acceptance.TOOLS / "zod" if task["repository"] == "zod" else acceptance.TOOLS
            test_command = [args.node, str(runner / "node_modules/vitest/vitest.mjs"), "run",
                            "--config", str(config), "--configLoader", "native"]
            command = [args.codex, "sandbox", "-P", ":workspace", "-C", str(folder),
                       "-c", "mcp_servers={}", "--", *test_command]
            result = acceptance.capture(command, folder)
            acceptance.check_hashes(folder, task)
            codex_compare.write_new(output / (folder.name + "-sandbox.json"), result)
            row = dict(repository=task["repository"], state=state, host=host["status"],
                       sandbox=result["status"], seconds=result["seconds"],
                       expected="failed" if state == "base" else "passed")
            records.append(row)
            print(row, flush=True)
    valid = all(row["host"] == row["sandbox"] == row["expected"] for row in records)
    codex_compare.write_new(output / "result.json", dict(schema_version=1, passed=valid,
        model_turns_started=0, scope="Selected unchanged tests under workspace sandbox; no full repository CI", records=records))
    if not valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
