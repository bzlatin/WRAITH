"""Feature acceptance is separate from the fixed Wraith regression gate."""

import asyncio
import copy
import json
from pathlib import Path
import sys

import llm
from llm.parts import Message, TextPart, ToolCallPart

source, task = Path(sys.argv[1]).resolve(), sys.argv[2]
assert Path(llm.__file__).resolve() == source / "llm/__init__.py"


async def resume():
    for is_async in (False, True):
        for via_conversation in (False, True):
            for enabled in (False, True):
                executed, hooks = [], []

                def operation(value: int):
                    executed.append(value)
                    return value * 2

                def before(tool, call):
                    hooks.append(call.tool_call_id)

                history = [
                    Message(role="user", parts=[TextPart(text="go")]),
                    Message(
                        role="assistant",
                        parts=[
                            ToolCallPart(
                                name="operation",
                                arguments={"value": 3},
                                tool_call_id="saved_3",
                            )
                        ],
                    ),
                ]
                original = copy.deepcopy(history)
                model = (
                    llm.get_async_model("echo") if is_async else llm.get_model("echo")
                )
                api = model.conversation() if via_conversation else model
                chain = api.chain(
                    None,
                    messages=history,
                    tools=[operation],
                    before_call=before,
                    resume_pending=enabled,
                )
                await chain.text() if is_async else chain.text()
                assert executed == ([3] if enabled else []), (
                    is_async,
                    via_conversation,
                    enabled,
                    executed,
                )
                assert hooks == (["saved_3"] if enabled else [])
                assert history == original
            # Opting out of history resume must not disable newly requested calls.
            chain = api.chain(
                json.dumps(
                    {"tool_calls": [{"name": "operation", "arguments": {"value": 4}}]}
                ),
                tools=[operation],
                resume_pending=False,
            )
            await chain.text() if is_async else chain.text()
            assert executed[-1] == 4


async def isolation():
    for is_async, async_tool in ((False, False), (True, False), (True, True)):
        seen = []

        def operation(items: list, llm_tool_call=None):
            assert llm_tool_call is call
            seen.append(llm_tool_call.arguments["items"][0]["value"])
            items[0]["value"] = "modified"
            items.append({"value": "new"})
            return items

        async def async_operation(items: list, llm_tool_call=None):
            return operation(items, llm_tool_call)

        tool = llm.Tool.function(
            async_operation if async_tool else operation, name="operation"
        )
        model = llm.get_async_model("echo") if is_async else llm.get_model("echo")
        response = model.prompt("observe", tools=[tool])
        await response.text() if is_async else response.text()
        arguments = {"items": [{"value": "original"}]}
        original = copy.deepcopy(arguments)
        call = llm.ToolCall("operation", arguments, "stable_id")

        def after(tool, tc, result):
            assert tc.arguments == original

        kwargs = {"tool_calls_list": [call], "after_call": after}
        results = (
            await response.execute_tool_calls(**kwargs)
            if is_async
            else response.execute_tool_calls(**kwargs)
        )
        assert arguments == original and call.arguments == original
        assert seen == ["original"]
        assert json.loads(results[0].output) == [
            {"value": "modified"},
            {"value": "new"},
        ]
        assert results[0].tool_call_id == "stable_id"


if __name__ == "__main__":
    asyncio.run({"resume-opt-out": resume, "argument-isolation": isolation}[task]())
    print("Feature acceptance passed:", task)
