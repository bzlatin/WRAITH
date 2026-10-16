"""Independent set reconciliation inside the study's shared operational wrapper.

Only the frozen workload's trusted application-generated exports are supported.
This is not a replacement for Wraith's bounded/untrusted-input contract. It emits
JSON, not HTML; the benchmark reports that output difference explicitly.
"""

import json

from reconcile import reconcile


def verify(_unused_binary, manifest, inventory, output):
    # No Wraith subprocess, evaluator, or inspector is called by this checker.
    decision = reconcile(manifest, inventory)
    with manifest.open(encoding="utf-8") as stream:
        expected_header, *expected = [json.loads(line) for line in stream]
    with inventory.open(encoding="utf-8") as stream:
        observed_header, *observed = [json.loads(line) for line in stream]
    indexed = {(d["tenant"], d["document_id"]): d["chunks"] for d in observed}
    findings = []
    totals = {
        "documents": len(expected),
        "expected_chunks": sum(len(d.get("expected_chunks", [])) for d in expected),
        "observed_chunks": sum(len(d["chunks"]) for d in observed),
        "passed": 0,
        "failed": 0,
        "pending": 0,
        "unknown": 0,
    }
    for document in expected:
        chunks = indexed.get((document["tenant"], document["document_id"]), [])
        planned = set(document.get("expected_chunks", []))
        actual = {c["id"] for c in chunks}
        unknown = document.get("revision") is None or any(
            c["revision"] is None for c in chunks
        )
        stale = [c["id"] for c in chunks if c["revision"] != document.get("revision")]
        status = (
            "unknown"
            if unknown
            else "failed"
            if planned != actual or stale
            else "passed"
        )
        totals[status] += 1
        if status != "passed":
            findings.append(
                {
                    "tenant": document["tenant"],
                    "document_id": document["document_id"],
                    "status": status,
                    "missing_count": len(planned - actual),
                    "unexpected_count": len(actual - planned),
                    "stale_count": len(stale),
                    "reason": "Reference chunk-set/revision comparison",
                    "next_action": "Inspect the job's intended and observed chunks",
                }
            )
    report = {
        "schema_version": 1,
        "manifest": expected_header,
        "inventory": observed_header,
        "status": {0: "passed", 1: "failed", 3: "unknown"}[decision["exit_code"]],
        "summary": totals,
        "findings": findings,
        "coverage_issues": [decision["reason"]] if decision["exit_code"] == 3 else [],
        "omitted_findings": 0,
    }
    with (output / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    (output / "check.log").write_text(
        "plain-reference-v1: trusted export reconciliation; no HTML\n"
    )
    return decision["exit_code"]
