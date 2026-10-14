"""Offline approval workflow using unmodified upstream PydanticAI orchestration.

The tool records an in-memory receipt; it never deletes files or contacts a service.
The historical case is credited to pydantic/pydantic-ai issue #3350 (MIT).
"""

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults


async def evaluate(payload, context=None):
    receipts = []
    model_calls = 0
    call = ToolCallPart(
        "record_action", {"note": payload.get("note", "demo")}, tool_call_id="call-1"
    )

    def model(messages, info):
        nonlocal model_calls
        model_calls += 1
        if payload["mode"] == "fresh" and model_calls == 1:
            return ModelResponse(parts=[call])
        return ModelResponse(parts=[TextPart("Workflow complete.")])

    agent = Agent(FunctionModel(model), output_type=[str, DeferredToolRequests])

    @agent.tool(requires_approval=True)
    def record_action(ctx: RunContext[None], note: str) -> str:
        """Record a harmless receipt after approval."""
        receipt = {"note": note, "approved": ctx.tool_call_approved}
        receipts.append(receipt)
        if context is not None:
            context.tool("record_action", {"note": note}, receipt)
        return "Recorded."

    mode = payload["mode"]
    if mode not in {"fresh", "resume", "approved", "denied"}:
        raise ValueError("Unknown workflow mode")
    history = [
        ModelRequest(parts=[UserPromptPart("Record the requested action.")]),
        ModelResponse(parts=[call]),
    ]
    options = {}
    if mode in {"approved", "denied"}:
        options["deferred_tool_results"] = DeferredToolResults(
            approvals={"call-1": mode == "approved"}
        )
    with override_allow_model_requests(False):
        if mode == "fresh":
            result = await agent.run("Record the requested action.")
        else:
            result = await agent.run(message_history=history, **options)
    pending = (
        result.output.approvals
        if isinstance(result.output, DeferredToolRequests)
        else []
    )
    return {
        "status": "awaiting_approval" if pending else "completed",
        "executions": len(receipts),
        "pending": len(pending),
        "receipts": receipts,
        "modelCalls": model_calls,
    }
