"""New feature acceptance; deliberately separate from old-behavior contracts."""

import asyncio
import json
import sys
import adapter
from ordinary import Context

payload = {"city": "London", "coordinates": [51.5, -0.1], "temperature": 20}
if sys.argv[1] == "units":
    payload["unit"] = "F"
    expected = "68 °F"
else:
    payload["transientFailures"] = {"/number": 1}
    expected = "20 °C"
result = asyncio.run(adapter.evaluate(payload, Context()))
print(json.dumps(result))
raise SystemExit(
    0
    if result["errorClass"] is None
    and result["forecasts"] == [{"temperature": expected, "description": "Sunny"}]
    else 1
)
