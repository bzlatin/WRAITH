"""Separate witness checks: use reviewed expected values, never candidate output."""

import asyncio
import json
from pathlib import Path
import sys
from entrypoint import evaluate


class Context:
    def tool(self, *args, **kwargs):
        pass  # The native adapter separately records these actual body calls.


async def main():
    cases = json.loads(Path(__file__).with_name("extra-contracts.json").read_text())
    failures = []
    for case in cases:
        output = await evaluate(case["input"], Context())
        for assertion in case["expect"]["json"]:
            value = output
            try:
                for part in assertion["path"].split("/")[1:]:
                    value = value[int(part)] if isinstance(value, list) else value[part]
            except (KeyError, IndexError, TypeError, ValueError):
                failures.append(
                    {"case": case["id"], "path": assertion["path"], "missing": True}
                )
                continue
            check = assertion["check"]
            passed = (
                value == check["value"]
                if check["op"] == "equals"
                else check["min"] <= len(value) <= check["max"]
            )
            if not passed:
                failures.append(
                    {
                        "case": case["id"],
                        "path": assertion["path"],
                        "observed": value,
                        "expected": check,
                    }
                )
    print(json.dumps({"failures": failures}, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
