"""Offline fixture with a known varying pass rate; state is adapter-owned."""
import json
import os
from pathlib import Path
import sys

request = json.loads(sys.stdin.readline())
state = Path(".wraith/sampling-counter")
state.parent.mkdir(exist_ok=True)
counter = int(state.read_text()) if state.exists() else 0
state.write_text(str(counter + 1))
candidate = os.environ.get("WRAITH_EXAMPLE_MODE") == "candidate"
passes = counter % 4 < (1 if candidate else 3)
print(json.dumps({"protocolVersion": 1, "scenarioId": request["scenarioId"],
                  "output": {"text": "20 PTO days" if passes else "Unknown"},
                  "usage": {"inputTokens": 200, "outputTokens": 58}}))
