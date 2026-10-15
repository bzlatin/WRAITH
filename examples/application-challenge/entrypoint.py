"""Observe LLM's real sync/async execution and saved-history resume paths."""

import asyncio
import json
import os
from pathlib import Path
import sys

import llm
from llm.parts import Message, TextPart, ToolCallPart, ToolResultPart
from cli_entrypoint import evaluate as cli_evaluate


async def evaluate(payload, context):
    if payload.get("kind") != "sdk":
        return await cli_evaluate(payload, context)
    if (
        Path(llm.__file__).resolve()
        != Path(os.environ["WRAITH_APP_SOURCE"]) / "llm/__init__.py"
    ):
        raise RuntimeError("Unexpected application source")
    guard = sys.modules.get("sitecustomize")
    if guard is None or not hasattr(guard, "blocked_attempts"):
        raise RuntimeError("Offline guard missing")
    mode = payload["mode"]
    receipts, hooks = [], []

    def operation(value: int, llm_tool_call=None):
        """Record a harmless local operation."""
        item = {"value": value, "callId": getattr(llm_tool_call, "tool_call_id", None)}
        receipts.append(item)
        context.tool("operation", {"value": value}, value * 2)
        return value * 2

    async def async_operation(value: int):
        # Finish in a different order to check result correlation, not timing.
        await asyncio.sleep(0.01 if value == 1 else 0)
        return operation(value)

    def fail():
        receipts.append({"failed": True})
        context.tool("fail", {}, "fixture failure", success=False)
        raise ValueError("fixture failure")

    async def pause():
        raise llm.PauseChain("approval needed")

    def before(tool, call):
        hooks.append("before:" + call.name)
        if mode.endswith("cancel") and call.arguments.get("value") == 1:
            raise llm.CancelToolCall("denied")

    def after(tool, call, result):
        hooks.append("after:" + result.name)

    is_async = mode.startswith("async")
    model = llm.get_async_model("echo") if is_async else llm.get_model("echo")
    tools = [async_operation] if is_async else [operation]
    # Fix the tool name across implementations; traces are emitted by the body.
    tools = [llm.Tool.function(tools[0], name="operation")]
    calls = [llm.ToolCall("operation", {"value": v}, f"call_{v}") for v in (1, 2)]
    result = {"receipts": receipts, "hooks": hooks, "paused": False}
    if mode.startswith("resume"):
        history = [
            Message(role="user", parts=[TextPart(text="perform operations")]),
            Message(
                role="assistant",
                parts=[
                    ToolCallPart(
                        name="operation",
                        arguments={"value": v},
                        tool_call_id=f"call_{v}",
                    )
                    for v in (1, 2)
                ],
            ),
            Message(
                role="tool",
                parts=[
                    ToolResultPart(name="operation", output="2", tool_call_id="call_1")
                ],
            ),
        ]
        if mode == "resume-stale":
            history.append(Message(role="user", parts=[TextPart(text="never mind")]))
        chain = model.chain(
            None, messages=history, tools=tools, before_call=before, after_call=after
        )
        output = chain.text()
        result["modelOutput"] = json.loads(output)
    else:
        if mode == "sync-error":
            tools = [fail]
            calls = [llm.ToolCall("fail", {}, "call_fail")]
        if mode == "async-pause":
            tools.append(pause)
            calls = [llm.ToolCall("pause", {}, "call_pause"), calls[1]]
        response = model.prompt("observe", tools=tools)
        if is_async:
            await response.text()
        else:
            response.text()
        try:
            kwargs = {
                "tool_calls_list": calls,
                "before_call": before,
                "after_call": after,
            }
            results = (
                await response.execute_tool_calls(**kwargs)
                if is_async
                else response.execute_tool_calls(**kwargs)
            )
        except llm.PauseChain as ex:
            result["paused"] = True
            results = ex.tool_results
        result["results"] = [
            {"name": r.name, "output": r.output, "callId": r.tool_call_id}
            for r in results
        ]
    result["executions"] = len(receipts)
    result["blockedNetworkAttempts"] = guard.blocked_attempts
    return result
