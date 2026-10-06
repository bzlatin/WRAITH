"""Both versions pass scenario checks; exact trace gates catch their drift."""
import json
import os
import sys

request = json.loads(sys.stdin.readline())
candidate = os.environ.get("WRAITH_EXAMPLE_MODE") == "candidate"
print(json.dumps({
    "protocolVersion": 1, "scenarioId": request["scenarioId"],
    "output": {"text": "Employees receive 20 PTO days."},
    "toolCalls": [{"name": "search_documents", "arguments": {
        "query": "payroll" if candidate else "PTO policy"}, "success": True}],
    "retrievals": [{"source": "employee_handbook",
                    "documentId": "payroll" if candidate else "pto-policy"}],
}))
