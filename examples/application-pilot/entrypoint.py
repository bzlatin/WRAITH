"""Exercise the actual LLM CLI and schema builder against its offline Echo model."""

import asyncio
import json
import io
import os
from pathlib import Path
import re
import tempfile
import sys

import llm
from click.testing import CliRunner
from llm.cli import cli
import tool_runtime

TOOLS = Path(__file__).with_name("tool_functions.py")


class TerminalInput(io.BytesIO):
    def isatty(self):
        return True


def run(payload, context):
    source = Path(os.environ["WRAITH_APP_SOURCE"]).resolve()
    if Path(llm.__file__).resolve() != source / "llm/__init__.py":
        raise RuntimeError("Application imported from an unexpected source directory")
    tool_runtime.context = context
    tool_runtime.receipts = []
    if payload["kind"] == "schema":

        def sample(title: str, count: int = 2, llm_tool_call=None):
            """Describe a sample."""
            return title * count

        tool = llm.Tool.function(sample, name="sample")
        return {
            "name": tool.name,
            "schema": tool.input_schema,
            "description": tool.description,
            "argumentNames": sorted(tool.input_schema["properties"]),
        }
    with tempfile.TemporaryDirectory(prefix="wraith-llm-user-") as user_dir:
        runner = CliRunner(env={"LLM_USER_PATH": user_dir})
        if payload["kind"] == "catalog":
            result = runner.invoke(
                cli,
                ["tools", "list", "--json", "--functions", str(TOOLS)],
                catch_exceptions=False,
            )
            data = json.loads(result.stdout)
            return {
                "exitCode": result.exit_code,
                "toolNames": [tool["name"] for tool in data["tools"]],
            }
        args = [
            "-m",
            "echo",
            "--no-stream",
            "--functions",
            str(TOOLS),
            json.dumps({"tool_calls": payload["calls"]}, ensure_ascii=False),
        ]
        if "approve" in payload:
            args += ["--tools-approve"]
        answers = payload.get(
            "answer", "y\n" if payload.get("approve") else "n\n"
        ) * len(payload["calls"])
        result = runner.invoke(
            cli, args, input=TerminalInput(answers.encode()), catch_exceptions=False
        )
        # Echo emits random tool-call IDs. Retain the response apart from those IDs.
        output = re.sub(r"tc_[0-9a-z]{26}", "tc_GENERATED", result.stdout)
        return {
            "exitCode": result.exit_code,
            "text": output,
            "diagnostics": re.sub(r"tc_[0-9a-z]{26}", "tc_GENERATED", result.stderr),
            "executions": len(tool_runtime.receipts),
            "receipts": tool_runtime.receipts,
        }


async def evaluate(payload, context):
    # CLI paths may execute async tools via asyncio.run(); give them their own thread.
    guard = sys.modules.get("sitecustomize")
    if guard is None or not hasattr(guard, "blocked_attempts"):
        raise RuntimeError("Offline socket guard was not loaded")
    result = await asyncio.to_thread(run, payload, context)
    result["blockedNetworkAttempts"] = guard.blocked_attempts
    return result
