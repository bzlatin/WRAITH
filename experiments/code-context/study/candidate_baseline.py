"""Frozen repository lookups against the local candidate; no model calls."""
import json
import shutil
import time
from pathlib import Path
from mcp_client import Client, clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    root = (REPO / ".wraith/code-context-study").resolve()
    output = root / "candidate-lookups"
    output.mkdir(exist_ok=False)
    node = shutil.which("node")
    for item in json.loads((HERE / "protocol.json").read_text())["repositories"]:
        client = None
        record = dict(schema_version=1, lane="candidate", repository=item["name"], calls=[], status="incomplete")
        start = time.monotonic()
        try:
            client = Client([node, str(HERE.parent / "cli.cjs"), "mcp", "--root", str(root / item["name"]),
                             "--cache", str(root / "candidate-cache")], root / item["name"], clean_env())
            record["initialization"] = client.initialize()
            record["startup_seconds"] = time.monotonic() - start
            for tool, args in [("code_symbols", dict(query=item["symbol"], limit=8, max_bytes=16000)),
                               ("code_context", dict(query=item["question"], limit=8, max_bytes=16000)),
                               ("code_symbols", dict(query=item["symbol"], limit=8, max_bytes=16000))]:
                called = time.monotonic()
                result = client.call("tools/call", dict(name=tool, arguments=args))
                record["calls"].append(dict(name=tool, arguments=args, seconds=time.monotonic()-called, result=result))
            record["status"] = "tool_error" if any(c["result"].get("isError") for c in record["calls"]) else "complete"
        except Exception as exc:
            record["error"] = str(exc)
        finally:
            if client:
                record["sampled_peak_process_tree_rss_bytes"] = client.peak_rss
                client.close()
                record["stderr"] = client.stderr.decode(errors="replace")
            record["total_seconds"] = time.monotonic()-start
            (output / (item["name"] + ".json")).write_text(json.dumps(record, indent=2)+'\n')
        print(item["name"], record["status"], round(record["total_seconds"], 3), flush=True)


if __name__ == "__main__":
    main()
