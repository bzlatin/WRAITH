#!/usr/bin/env python3
"""Small comparison baseline for trusted exports from this example.

This intentionally does not implement Wraith's full untrusted-input validation,
streaming limits, bounded findings or HTML report. It can detect the same missing,
extra and stale chunks. No database or model dependency.
"""

import argparse
import json
from pathlib import Path


def reconcile(manifest, inventory):
    def read(path):
        with Path(path).open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream]

    expected_header, *documents = read(manifest)
    observed_header, *indexed = read(inventory)
    if (
        not documents
        or any(
            not h["complete"] or not h["stable"]
            for h in (expected_header, observed_header)
        )
        or any(
            expected_header[k] != observed_header[k] for k in ("scope", "generation")
        )
        or any(not d["settled"] for d in documents)
        or any(c["revision"] is None for d in indexed for c in d["chunks"])
    ):
        return {"exit_code": 3, "reason": "incomplete, unsettled or empty input"}
    expected = {
        (d["tenant"], d["document_id"], chunk, d["revision"])
        for d in documents
        if d["state"] == "present"
        for chunk in d["expected_chunks"]
    }
    observed = {
        (d["tenant"], d["document_id"], c["id"], c["revision"])
        for d in indexed
        for c in d["chunks"]
    }
    return {
        "exit_code": 0 if expected == observed else 1,
        "missing_or_stale": sorted(expected - observed),
        "unexpected_or_stale": sorted(observed - expected),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("inventory", type=Path)
    args = parser.parse_args()
    result = reconcile(args.manifest, args.inventory)
    print(json.dumps(result, indent=2))
    raise SystemExit(result["exit_code"])
