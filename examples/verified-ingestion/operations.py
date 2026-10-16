"""Read-only recovery and conservative retention planning for the ingestion example.

Historical evidence integrity is not a new audit of live collection contents.
No SDK imports, mutation methods, process probes or deletion commands belong here.
"""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

GENERATION = re.compile(r"wraith-[0-9a-f]{32}\Z")
MAX_FILE = 64 * 1024 * 1024


class EvidenceError(ValueError):
    """An actionable, fixed diagnostic that contains no raw evidence values."""


def digest(path):
    if path.is_symlink() or not path.is_file():
        raise EvidenceError("Evidence must be a regular file")
    value = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(65536):
            size += len(block)
            if size > MAX_FILE:
                raise EvidenceError("Evidence exceeds 64 MiB per file")
            value.update(block)
    return value.hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("Duplicate JSON field")
        result[key] = value
    return result


def read_json(path, header=False):
    if path.is_symlink() or not path.is_file():
        raise EvidenceError("Evidence must be a regular file")
    with path.open("rb") as stream:
        data = stream.readline(1048577) if header else stream.read(1048577)
    if len(data) > 1048576:
        raise EvidenceError("Evidence metadata exceeds 1 MiB")
    value = json.loads(data, object_pairs_hook=_object)
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
    ):
        raise EvidenceError("Unsupported evidence metadata schema")
    return value


def _record(directory):
    names = ("job.json", "verification.json", "promotion.json", "manifest.jsonl")
    values = {
        name: read_json(directory / name, header=name.endswith("jsonl"))
        for name in names
        if (directory / name).exists() or (directory / name).is_symlink()
    }
    identities = {v.get("generation", v.get("collection")) for v in values.values()}
    if len(identities) != 1:
        raise EvidenceError("Conflicting evidence identities")
    generation = identities.pop()
    if not isinstance(generation, str) or not GENERATION.fullmatch(generation):
        raise EvidenceError("Invalid generation identity")
    job = values.get("job.json")
    record = {
        "collection": generation,
        "evidence_directory": directory.name,
        "evidence_state": "legacy_unbound",
        "verified_at_build": False,
        "published_receipt": False,
        "previous_collection": None,
        "created_at_utc": None,
        "workflow_alias": None,
    }
    if job is None:
        return record
    alias = job.get("alias")
    if (
        not isinstance(alias, str)
        or not alias.strip()
        or any(ord(c) < 32 for c in alias)
    ):
        raise EvidenceError("Invalid workflow alias")
    try:
        created = datetime.fromisoformat(job["created_at_utc"])
    except (ValueError, TypeError) as error:
        raise EvidenceError("Invalid job timestamp") from error
    if created.utcoffset() is None or created.utcoffset().total_seconds() != 0:
        raise EvidenceError("Job timestamp must be UTC")
    previous = job.get("previous_collection")
    if previous is not None and (
        not isinstance(previous, str) or not GENERATION.fullmatch(previous)
    ):
        # A workflow can inherit a foreign collection. Preserve its identity for protection.
        if not isinstance(previous, str) or not previous.strip():
            raise EvidenceError("Invalid previous collection")
    record.update(
        workflow_alias=alias,
        previous_collection=previous,
        created_at_utc=created.isoformat(),
        evidence_state="unfinished",
    )
    verification = values.get("verification.json")
    if verification is None:
        return record
    if (
        verification.get("alias") != alias
        or verification.get("previous_collection") != previous
    ):
        raise EvidenceError("Verification does not match the job")
    verifier = verification.get("verifier", "wraith")
    if verifier not in ("wraith", "plain-reference-v1") or verifier != job.get(
        "verifier", "wraith"
    ):
        raise EvidenceError("Unknown or conflicting verifier identity")
    record["verifier"] = verifier
    code = verification.get("exit_code")
    if type(code) is not int or code not in (0, 1, 2, 3, 130):
        raise EvidenceError("Invalid recorded exit code")
    hashes = verification.get("evidence_sha256")
    if hashes is None:
        record["evidence_state"] = "legacy_unbound"
        return record
    if not isinstance(hashes, dict) or any(
        name not in ("job.json", "manifest.jsonl", "inventory.jsonl", "report.json")
        for name in hashes
    ):
        raise EvidenceError("Invalid evidence digest fields")
    for name, expected in hashes.items():
        if not isinstance(expected, str) or digest(directory / name) != expected:
            raise EvidenceError(f"Saved evidence changed: {name}")
    if code not in (0, 1, 3):
        record["evidence_state"] = "execution_incomplete"
        return record
    if set(hashes) != {"job.json", "manifest.jsonl", "inventory.jsonl", "report.json"}:
        raise EvidenceError("Verification lacks bound evidence")
    report = read_json(directory / "report.json")
    manifest = values.get("manifest.jsonl")
    inventory = read_json(directory / "inventory.jsonl", header=True)
    for name, header in (("manifest", manifest), ("inventory", inventory)):
        if (
            header is None
            or header.get("kind") != name
            or header.get("generation") != generation
            or report.get(name) != header
        ):
            raise EvidenceError("Report does not bind the recorded exports")
    statuses = {0: "passed", 1: "failed", 3: ("pending", "unknown")}
    expected_status = statuses[code]
    if report.get("status") not in (
        expected_status if isinstance(expected_status, tuple) else (expected_status,)
    ):
        raise EvidenceError("Report and exit code disagree")
    record["evidence_state"] = "verified_unpublished" if code == 0 else "gate_blocked"
    record["verified_at_build"] = code == 0
    promotion = values.get("promotion.json")
    if promotion is not None:
        if (
            code != 0
            or promotion.get("alias") != alias
            or promotion.get("previous_collection") != previous
        ):
            raise EvidenceError("Promotion receipt conflicts with verification")
        record.update(published_receipt=True, evidence_state="published")
    return record


def inspect(client, history, alias, keep_previous=1):
    """Observe actual collections/aliases and their saved evidence. Never authorize deletion."""
    if type(keep_previous) is not int or keep_previous < 1:
        raise EvidenceError("keep_previous must be at least one")
    history = Path(history)
    if history.is_symlink() or not history.is_dir():
        raise EvidenceError("History must be a real directory")

    def snapshot():
        collections = sorted(c.name for c in client.get_collections().collections)
        aliases = sorted(
            (a.alias_name, a.collection_name) for a in client.get_aliases().aliases
        )
        if len(collections) > 1000:
            raise EvidenceError("Inspection is limited to 1,000 collections")
        return collections, aliases

    collections, aliases = snapshot()
    selected = next((collection for name, collection in aliases if name == alias), None)
    records = {}
    issues = []
    entries = sorted(history.iterdir())
    if len(entries) > 2000:
        raise EvidenceError("History is limited to 2,000 immediate entries")
    for directory in entries:
        if directory.is_symlink():
            issues.append({"directory": directory.name, "reason": "symlink_not_read"})
            continue
        if not directory.is_dir() or not any(
            (directory / name).exists() or (directory / name).is_symlink()
            for name in (
                "job.json",
                "verification.json",
                "promotion.json",
                "manifest.jsonl",
            )
        ):
            continue
        try:
            record = _record(directory)
            generation = record["collection"]
            if generation in records:
                raise EvidenceError("Duplicate generation records")
            records[generation] = record
            if record["evidence_state"] == "legacy_unbound":
                issues.append(
                    {
                        "directory": directory.name,
                        "reason": "legacy_evidence_has_no_binding",
                    }
                )
        except (ValueError, TypeError, KeyError, OSError) as error:
            issues.append(
                {
                    "directory": directory.name,
                    "reason": type(error).__name__,
                    "detail": str(error)
                    if isinstance(error, EvidenceError)
                    else "Evidence metadata is unreadable, invalid or missing required fields",
                }
            )
    protected_references = {
        r["previous_collection"]
        for r in records.values()
        if r["evidence_state"]
        in (
            "unfinished",
            "verified_unpublished",
            "execution_incomplete",
            "legacy_unbound",
        )
    }
    previous = [
        r
        for r in records.values()
        if r["published_receipt"]
        and r["workflow_alias"] == alias
        and r["collection"] != selected
    ]
    previous.sort(key=lambda r: r["created_at_utc"], reverse=True)
    cutoff = (
        previous[min(keep_previous, len(previous)) - 1]["created_at_utc"]
        if previous
        else None
    )
    rows = []
    for collection in collections:
        row = dict(
            records.get(
                collection,
                {
                    "collection": collection,
                    "evidence_state": "untracked",
                    "verified_at_build": False,
                    "published_receipt": False,
                },
            )
        )
        row["aliases"] = [name for name, target in aliases if target == collection]
        row["points"] = client.count(collection, exact=True).count
        reasons = []
        if row["aliases"]:
            reasons.append("referenced_by_alias")
        if collection in protected_references:
            reasons.append("referenced_by_unfinished_job")
        if not row["published_receipt"] or row.get("workflow_alias") != alias:
            reasons.append("no_bound_publication_for_this_workflow")
        if (
            cutoff is not None
            and row["published_receipt"]
            and row.get("workflow_alias") == alias
            and collection != selected
            and row.get("created_at_utc") is not None
            and row["created_at_utc"] >= cutoff
        ):
            reasons.append("retained_rollback_generation")
        row["protection_reasons"] = reasons
        row["retention_action"] = "keep" if reasons else "review_retirement"
        rows.append(row)
    changed = snapshot() != (collections, aliases)
    if changed:
        issues.append({"reason": "collections_or_aliases_changed_during_inspection"})
    active = next((row for row in rows if row["collection"] == selected), None)
    if active is None:
        recovery = "no_selected_collection"
    elif not active["verified_at_build"] or active.get("workflow_alias") != alias:
        recovery = "selected_evidence_unknown"
    elif active["published_receipt"]:
        recovery = "selected_with_receipt"
    else:
        recovery = "selected_verified_receipt_missing"
    complete = (
        not issues
        and active is not None
        and active["verified_at_build"]
        and active.get("workflow_alias") == alias
    )
    if not complete:
        for row in rows:
            row["retention_action"] = "keep"
            row["protection_reasons"].append("inspection_incomplete")
    candidates = [r for r in rows if r["retention_action"] == "review_retirement"]
    return {
        "schema_version": 1,
        "kind": "read_only_ingestion_inspection",
        "alias": alias,
        "selected_collection": selected,
        "recovery": recovery,
        "inspection_complete": complete,
        "observations_unchanged": not changed,
        "keep_previous": keep_previous,
        "retention": {
            "review_candidates": len(candidates),
            "candidate_points": sum(r["points"] for r in candidates),
            "candidate_bytes": None,
            "deletion_authorized": False,
        },
        "collections": rows,
        "issues": issues,
        "limits": [
            "Saved hashes detect accidental evidence changes, not malicious rewriting.",
            "Build verification is historical, not a fresh audit of live contents.",
            "Repeated metadata reads are not an atomic snapshot or a distributed lock.",
            "Point counts are observations, not byte or cost estimates. Re-inspect before any manual action.",
        ],
    }


def human(result):
    messages = {
        "selected_with_receipt": "The selected index has matching build evidence and a promotion receipt.",
        "selected_verified_receipt_missing": "The selected index has matching passing build evidence, but its promotion receipt is missing. Do not repeat the import just because the receipt is absent.",
        "selected_evidence_unknown": "The selected index cannot be linked to intact passing build evidence.",
        "no_selected_collection": "No collection is selected for this alias.",
    }
    lines = [
        messages[result["recovery"]],
        f"Selected: {json.dumps(result['selected_collection'])}",
        "This inspects saved evidence; it does not recheck current index contents.",
        "",
        "Collection | Points | Build evidence | Retention",
    ]
    evidence_labels = {
        "published": "passed; receipt saved",
        "verified_unpublished": "passed; no receipt",
        "gate_blocked": "blocked",
        "unfinished": "not completed",
        "legacy_unbound": "older unbound evidence",
        "untracked": "no saved job",
        "execution_incomplete": "execution incomplete",
    }
    reason_labels = {
        "referenced_by_alias": "used by an alias",
        "referenced_by_unfinished_job": "needed by an unfinished job",
        "no_bound_publication_for_this_workflow": "publication not proven",
        "retained_rollback_generation": "rollback copy",
        "inspection_incomplete": "inspection incomplete",
    }
    for row in result["collections"][:20]:
        retention = (
            "review older copy"
            if row["retention_action"] == "review_retirement"
            else "keep: "
            + ", ".join(reason_labels[r] for r in row["protection_reasons"])
        )
        label = evidence_labels[row["evidence_state"]]
        if row.get("verifier") == "plain-reference-v1":
            label += " (reference checker)"
        lines.append(
            f"{json.dumps(row['collection'])} | {row['points']} | {label} | {retention}"
        )
    if len(result["collections"]) > 20:
        lines.append(
            "More collections omitted; use --output json for the complete list."
        )
    plan = result["retention"]
    lines.extend(
        [
            "",
            f"Review {plan['review_candidates']} older collections ({plan['candidate_points']} points). Byte savings are unavailable.",
            "No deletion or repair was performed. Active aliases, rollback copies and unfinished jobs are protected.",
        ]
    )
    if result["issues"]:
        lines.append(
            "Inspection is incomplete; all collections are kept. Review the issues in JSON output."
        )
    return "\n".join(lines)
