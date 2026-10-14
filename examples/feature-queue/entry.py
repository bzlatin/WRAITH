"""Campaign entrypoint; the recorded-model mode never calls a provider."""

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # copied to frozen/examples/feature-queue
TASKS = json.loads((Path(__file__).with_name("tasks.json")).read_text())
CAMPAIGN = ROOT.parent
variant = os.environ.get("WRAITH_CHANGE_VARIANT", "baseline")
if variant != "baseline" and variant not in {task["id"] for task in TASKS}:
    raise ValueError("Unknown feature variant")
path = (
    ROOT / "examples/live-agent/agent.py"
    if variant == "baseline"
    else CAMPAIGN / "candidates" / variant / "agent.py"
)
spec = importlib.util.spec_from_file_location("selected_application", path)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def evaluate(payload, context):
    if os.environ.get("WRAITH_CHANGE_MODE") == "live":
        return agent.evaluate(payload, context)
    records = json.loads(
        Path(__file__).with_name("recorded-decisions.json").read_text()
    )["cases"]
    recorded = records[context.scenario_id]
    if payload != recorded["input"]:
        raise ValueError("Recorded decisions do not match this scenario input")
    calls = iter(recorded["calls"])
    previous = None

    def replay(request, context):
        nonlocal previous
        if previous is not None:
            observed = json.loads(request["input"][-1]["output"])
            if observed != previous["result"]:
                raise RuntimeError(
                    "Recorded tool result changed; replay needs live reevaluation"
                )
        call = next(calls, None) if "tools" in request else None
        previous = call
        if call:
            return {
                "output": [
                    {
                        "type": "function_call",
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"]),
                        "call_id": "recorded-decision",
                    }
                ]
            }
        return {
            "model": "recorded-model-replay",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": json.dumps(recorded["draft"])}
                    ],
                }
            ],
        }

    agent.provider = replay
    result = agent.evaluate(payload, context)
    result["evaluationMode"] = "recorded-model-replay"
    return result
