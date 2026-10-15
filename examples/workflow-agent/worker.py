"""Observe real upstream memory and callbacks without replacing its agent loop."""

import json
import sys

import base_worker
from smolagents import ToolCallingAgent
from smolagents.memory import ActionStep, FinalAnswerStep


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read())
    agents, finalized, streamed = [], [], []

    def observe(step, agent=None):
        if isinstance(step, ActionStep):
            finalized.append(step.step_number)

    class ObservedAgent(ToolCallingAgent):
        def __init__(self, **kwargs):
            kwargs["step_callbacks"] = [observe]
            if payload.get("disableChecks"):
                kwargs["final_answer_checks"] = []
            super().__init__(**kwargs)
            agents.append(self)

        def run(self, *args, **kwargs):
            if payload.get("reuse"):
                super().run(*args, **kwargs)
            if payload.get("consumeStream"):
                kwargs["stream"] = True
                answer = None
                for step in super().run(*args, **kwargs):
                    if isinstance(step, ActionStep):
                        streamed.append(step.step_number)
                    if isinstance(step, FinalAnswerStep):
                        answer = step.output
                return answer
            return super().run(*args, **kwargs)

    base_worker.ToolCallingAgent = ObservedAgent
    output = base_worker.run(payload)
    output.update(
        memoryActionNumbers=[
            s.step_number for s in agents[0].memory.steps if isinstance(s, ActionStep)
        ],
        finalizedActionNumbers=finalized,
        streamedActionNumbers=streamed,
    )
    print(json.dumps(output))
