"""Frozen acceptance checks for new task behavior, separate from regression gates."""

import ast
import json
from pathlib import Path
import sys
import tempfile


def check(app, task):
    sys.path.insert(0, str(app))
    from support_agent import agent, catalog

    spec = task["acceptance"]
    if spec.get("rankingProbe"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.json"
            docs = [
                dict(
                    id="a-repeat",
                    title="refund refund refund",
                    text="refund",
                    status="current",
                    audience="public",
                ),
                dict(
                    id="b-two",
                    title="refund shipping",
                    text="two topics",
                    status="current",
                    audience="public",
                ),
            ]
            path.write_text(json.dumps(docs))
            catalog.CORPUS = path
            assert catalog.search("refund shipping", "public")[0]["id"] == "b-two", (
                "Distinct-topic ranking is not implemented"
            )
    elif spec.get("responseHelper"):
        helper = getattr(agent, "make_response", None)
        assert callable(helper), (
            "make_response(status, text, citations=None) is missing"
        )
        assert helper("answered", "example", ["doc"]) == {
            "status": "answered",
            "text": "example",
            "citations": ["doc"],
        }
        assert helper("escalated", "help") == {
            "status": "escalated",
            "text": "help",
            "citations": [],
        }
        tree = ast.parse((app / "support_agent/agent.py").read_text())
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "make_response"
        ]
        assert len(calls) >= 3, "Answered and escalated paths must use the constructor"
    else:
        result = agent.evaluate(spec["input"])
        assert all(r["status"] == spec["status"] for r in result["responses"]), (
            "New task behavior is missing"
        )
        if "text" in spec:
            assert spec["text"] in result["responses"][0]["text"]
        if "maxSearches" in spec:
            assert result["searches"] <= spec["maxSearches"], (
                "Repeated retrieval was not cached"
            )


if __name__ == "__main__":
    app, tasks, task_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    task = next(t for t in json.loads(tasks.read_text())["tasks"] if t["id"] == task_id)
    try:
        check(app, task)
    except AssertionError as error:
        print(json.dumps({"passed": False, "reason": str(error)}))
        sys.exit(1)
    print(json.dumps({"passed": True}))
