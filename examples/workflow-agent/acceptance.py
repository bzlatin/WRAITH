"""Acceptance for an existing upstream request, separate from regression cases."""

import json
from unittest.mock import Mock

from smolagents import ToolCallingAgent
from smolagents.memory import ActionStep
from smolagents.models import (
    Model,
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
)

model = Mock(spec=Model)
model.generate.return_value = ChatMessage(
    role=MessageRole.ASSISTANT,
    content="",
    tool_calls=[
        ChatMessageToolCall(
            id="answer",
            type="function",
            function=ChatMessageToolCallFunction(
                name="final_answer", arguments={"answer": "APPROVED"}
            ),
        )
    ],
)
observed = []


def critic(answer, memory, agent):
    current = [step for step in memory.steps if isinstance(step, ActionStep)]
    observed.append(current[-1].step_number if current else None)
    return bool(current) and current[-1].step_number == agent.step_number


agent = ToolCallingAgent(
    model=model, tools=[], final_answer_checks=[critic], max_steps=3, verbosity_level=-1
)
answer = agent.run("Return an approved answer.")
result = {
    "answer": str(answer),
    "criticSawSteps": observed,
    "modelFixtureCalls": model.generate.call_count,
}
print(json.dumps(result))
raise SystemExit(
    0
    if observed == [1] and model.generate.call_count == 1 and str(answer) == "APPROVED"
    else 1
)
