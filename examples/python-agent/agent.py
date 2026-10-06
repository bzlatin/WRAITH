"""Synthetic, deterministic WRAITH v1 agent. No dependencies or API keys."""
import json
import os
import sys


def respond(request, candidate=False):
    scenario = request["scenarioId"]
    tools, retrievals = [], []
    if scenario == "find-pto-policy":
        text = "Employees receive 20 PTO days."
        tools = [{"name": "web_search" if candidate else "search_documents",
                  "arguments": {"query": "PTO policy"}, "success": True}]
        retrievals = [{"source": "employee_handbook",
                       "documentId": "employee-handbook", "score": 0.92}]
    elif scenario == "delete-files-protection":
        text = "I cannot delete repository documents."
    elif scenario == "weather-tool-selection":
        text = "Arlington is sunny, 72 F."
        tools = [{"name": "get_weather", "arguments": {"city": "Arlington"},
                  "success": True}]
    else:
        text = "Unknown synthetic scenario."
    return {"protocolVersion": 1, "scenarioId": scenario,
            "output": {"text": text}, "toolCalls": tools, "retrievals": retrievals,
            "usage": {"inputTokens": 200, "outputTokens": 58},
            "estimatedCostUsd": 0.001, "metadata": {"synthetic": True}}


if __name__ == "__main__":
    request = json.loads(sys.stdin.readline())
    if request.get("protocolVersion") != 1:
        print("Unsupported protocol version", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(respond(request, "--candidate" in sys.argv or
                             os.environ.get("WRAITH_EXAMPLE_MODE") == "candidate")))
