"""Run the upstream agent, including its real final-answer validation and retries."""

import functools
import json
import os
from pathlib import Path
import sys

import smolagents
from smolagents import ToolCallingAgent
from smolagents.default_tools import FinalAnswerTool
from smolagents.models import (
    Model,
    ChatMessage,
    ChatMessageToolCall,
    ChatMessageToolCallFunction,
    MessageRole,
)


def run(payload):
    source = Path(os.environ["WRAITH_APP_SOURCE"]).resolve()
    if Path(smolagents.__file__).resolve() != source / "src/smolagents/__init__.py":
        raise RuntimeError("Imported an unexpected application source")
    events = []
    checks = []

    class RecordedFinalAnswer(FinalAnswerTool):
        def forward(self, answer):
            result = super().forward(answer)
            events.append(
                {
                    "name": "final_answer",
                    "arguments": {"answer": answer},
                    "result": result,
                    "success": True,
                }
            )
            return result

    class OfflineModel(Model):
        def __init__(self):
            super().__init__(model_id="scripted-offline-model")
            self.calls = 0

        def generate(self, messages, **kwargs):
            self.calls += 1
            answer = (
                "APPROVED" if payload["firstValid"] or self.calls > 1 else "REJECTED"
            )
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                content="",
                tool_calls=[
                    ChatMessageToolCall(
                        id=f"call-{self.calls}",
                        type="function",
                        function=ChatMessageToolCallFunction(
                            name="final_answer", arguments={"answer": answer}
                        ),
                    )
                ],
            )

    def require_approved(answer, memory, agent, expected="APPROVED"):
        checks.append(answer)
        return answer == expected

    class Checker:
        def __call__(self, answer, memory, agent):
            return require_approved(answer, memory, agent)

    check = {
        "function": require_approved,
        "partial": functools.partial(require_approved, expected="APPROVED"),
        "callable": Checker(),
    }[payload["checker"]]
    model = OfflineModel()
    agent = ToolCallingAgent(
        tools=[RecordedFinalAnswer()],
        model=model,
        final_answer_checks=[check],
        max_steps=3,
        verbosity_level=-1,
    )
    result, error_type, message = None, None, None
    stream = None
    try:
        if payload.get("operation") == "close_stream":
            stream = agent.run("Return an approved answer.", stream=True)
            next(stream)
            stream.close()
        else:
            result = agent.run(
                "Return an approved answer; retry when validation fails."
            )
    except Exception as error:
        error_type, message = type(error).__name__, str(error)
    finally:
        if stream is not None:
            stream.close()  # Release a generator whose first close failed.
    guard = sys.modules.get("sitecustomize")
    if guard is None or not hasattr(guard, "blocked_attempts"):
        raise RuntimeError("Offline socket guard was not loaded")
    return {
        "answer": str(result) if result is not None else None,
        "errorType": error_type,
        "errorMessage": message,
        "checkCalls": len(checks),
        "checkedAnswers": checks,
        "modelFixtureCalls": model.calls,
        "optimized": bool(sys.flags.optimize),
        "blockedNetworkAttempts": guard.blocked_attempts,
        "events": events,
    }


if __name__ == "__main__":
    print(json.dumps(run(json.loads(sys.stdin.read()))))
