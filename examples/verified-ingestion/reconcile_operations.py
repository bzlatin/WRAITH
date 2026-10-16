"""Small read-only reference recipe for trusted example history.

Uses the same alias/collection reads. It intentionally trusts recorded gate exits;
it does not validate schemas, hashes, conflicting records or unsupported history.
It demonstrates that the basic recovery/retention question needs no novel algorithm.
"""

import json
from pathlib import Path


def inspect_plain(client, history, alias, keep_previous=1):
    aliases = [(a.alias_name, a.collection_name) for a in client.get_aliases().aliases]
    selected = next((c for a, c in aliases if a == alias), None)
    records = {}
    for path in sorted(Path(history).glob("*/job.json")):
        record = json.loads(path.read_text())
        verification = path.parent / "verification.json"
        record["passed"] = (
            verification.exists()
            and json.loads(verification.read_text())["exit_code"] == 0
        )
        record["published"] = (path.parent / "promotion.json").exists()
        records[record["generation"]] = record
    active = records.get(selected, {})
    recovery = "selected_evidence_unknown"
    if active.get("passed"):
        recovery = (
            "selected_with_receipt"
            if active["published"]
            else "selected_verified_receipt_missing"
        )
    protected = {c for _, c in aliases}
    protected.update(
        r.get("previous_collection") for r in records.values() if not r["published"]
    )
    previous = sorted(
        (
            r
            for c, r in records.items()
            if c != selected and r["published"] and r["passed"] and r["alias"] == alias
        ),
        key=lambda r: r["created_at_utc"],
        reverse=True,
    )
    protected.update(r["generation"] for r in previous[:keep_previous])
    collections = sorted(c.name for c in client.get_collections().collections)
    candidates = [
        c
        for c in collections
        if c not in protected
        and records.get(c, {}).get("published")
        and records[c]["passed"]
        and records[c]["alias"] == alias
    ]
    return {
        "selected_collection": selected,
        "recovery": recovery,
        "review_candidates": candidates,
        "candidate_points": sum(client.count(c, exact=True).count for c in candidates),
        "deletion_authorized": False,
    }
