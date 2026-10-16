"""Run the frozen lookup workload against pinned Serena. No LLM calls."""
import argparse
import json
import time
from pathlib import Path
from mcp_client import Client, clean_env

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO / ".wraith/code-context-study")
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    protocol = json.loads((HERE / "protocol.json").read_text())
    output = root / args.attempt
    output.mkdir(exist_ok=False)
    for item in protocol["repositories"]:
        started = time.monotonic()
        record = dict(schema_version=1, lane="serena", repository=item["name"],
                      commit=item["commit"], calls=[], status="incomplete")
        client = None
        try:
            command = [str(root / "serena-venv/bin/serena"), "start-mcp-server",
                       "--project", str(root / item["name"]), "--context", "ide",
                       "--mode", "planning", "--mode", "no-onboarding", "--agent-interface", "tools",
                       "--enable-web-dashboard", "false", "--open-web-dashboard", "false",
                       "--enable-gui-log-window", "false"]
            record["command"] = command
            client = Client(command, root / item["name"], clean_env({
                "SERENA_HOME": str(root / "serena-home-ready"), "SERENA_USAGE_REPORTING": "false",
                "npm_config_cache": str(root / "npm-cache"), "npm_config_ignore_scripts": "true"}))
            record["initialization"] = client.initialize()
            record["startup_seconds"] = time.monotonic() - started
            tools = client.call("tools/list")["tools"]
            record["tools"] = tools
            for name, arguments in [("find_symbol", dict(name_path_pattern=item["symbol"], include_body=True, max_answer_chars=16000)),
                                    ("search_for_pattern", dict(substring_pattern=item["symbol"], restrict_search_to_code_files=True, max_answer_chars=16000))]:
                if not any(t["name"] == name for t in tools):
                    raise RuntimeError("Expected documented tool not exposed: " + name)
                start = time.monotonic()
                result = client.call("tools/call", dict(name=name, arguments=arguments))
                record["calls"].append(dict(name=name, arguments=arguments, seconds=time.monotonic() - start,
                                             output_bytes=len(json.dumps(result).encode()), result=result))
            record["status"] = "tool_error" if any(c["result"].get("isError") for c in record["calls"]) else "complete"
        except Exception as exc:
            record["error"] = str(exc)
        finally:
            if client:
                record["sampled_peak_process_tree_rss_bytes"] = client.peak_rss
                client.close()
                record["stderr_first_64k"] = client.stderr.decode(errors="replace")
            record["total_seconds"] = time.monotonic() - started
            (output / (item["name"] + ".json")).write_text(json.dumps(record, indent=2) + "\n")
        print(item["name"], record["status"], round(record["total_seconds"], 3), record.get("error", ""), flush=True)


if __name__ == "__main__":
    main()
