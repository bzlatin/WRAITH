"""New-feature acceptance checks, distinct from frozen behavioral contracts."""

import importlib.util
import asyncio
import json
from pathlib import Path
import sys


async def check(directory, task):
    spec = importlib.util.spec_from_file_location(
        "candidate_app", Path(directory) / "approval_agent.py"
    )
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    note = 'résumé "note"'
    if task == "history-roundtrip":
        encoded = app.encode_history(note)
        assert isinstance(encoded, str)
        history = app.decode_history(encoded)
        assert history[-1].parts[0].args_as_dict() == {"note": note}
        calls = []
        encode, decode = app.encode_history, app.decode_history

        def observed_encode(value):
            calls.append("encode")
            return encode(value)

        def observed_decode(value):
            calls.append("decode")
            return decode(value)

        app.encode_history, app.decode_history = observed_encode, observed_decode
        await app.evaluate({"mode": "resume", "note": note})
        assert calls == ["encode", "decode"], calls
    elif task == "receipt-summary":
        for mode in ("fresh", "resume", "approved", "denied"):
            result = await app.evaluate({"mode": mode, "note": note})
            assert result["receiptSummary"] == {
                "count": int(mode == "approved"),
                "notes": [note] if mode == "approved" else [],
            }
    elif task == "pending-details":
        for mode in ("fresh", "resume", "approved", "denied"):
            result = await app.evaluate({"mode": mode, "note": note})
            expected = [
                {"id": "call-1", "tool": "record_action", "arguments": {"note": note}}
            ]
            assert result["pendingRequests"] == (
                expected if mode in ("fresh", "resume") else []
            )
    else:
        raise ValueError("Unknown acceptance task")


if __name__ == "__main__":
    asyncio.run(check(sys.argv[1], sys.argv[2]))
    print(json.dumps({"passed": True}))
