#!/usr/bin/env python3
"""Frozen repeated-update comparison. Only starts an owned localhost Qdrant server.

The same ingestion, evidence binding, inspection and retention code runs in both
lanes. Only the verifier changes. Controls are separate from release updates.
"""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import statistics
import time
from unittest.mock import patch

import search as app
from reference_check import verify as reference_verify
from server_check import Server, connect, footprint, require

PHASES = [
    ("release-0", "normal", 0),
    ("release-1", "normal", 0),
    ("unchanged-repeat", "normal", 0),
    ("release-2", "normal", 0),
    ("rollback-release-1", "normal", 0),
    ("duplicate-content", "normal", 0),
    ("rename-document", "normal", 0),
    ("remove-five", "normal", 0),
    ("restore-release-2", "normal", 0),
    ("partial-write", "control", 1),
    ("missing-revision", "control", 3),
    ("lost-receipt", "control", 0),
    ("empty-feed", "control", 3),
    ("resume-release-2", "normal", 0),
]


def frozen_inputs(source):
    # Independent of the application's source loader, splitter and verifier.
    result = {}
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Input snapshot contains a symlink")
        if path.is_file() and path.suffix.lower() in (".txt", ".md"):
            result[path.relative_to(source).as_posix()] = path.read_bytes()
    return result


def materialize(destination, files):
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def digest_files(files):
    return hashlib.sha256(
        json.dumps(
            [
                (name, hashlib.sha256(data).hexdigest())
                for name, data in sorted(files.items())
            ]
        ).encode()
    ).hexdigest()


def selected_documents(client, collection):
    found = {}
    offset = None
    points_seen = 0
    while True:
        points, offset = client.scroll(
            collection,
            offset=offset,
            limit=512,
            with_vectors=False,
            with_payload=["document_id", "revision"],
        )
        for point in points:
            points_seen += 1
            document = point.payload["document_id"]
            revision = point.payload.get("revision")
            if document in found:
                require(
                    found[document] == revision,
                    "Selected index mixed document revisions",
                )
            found[document] = revision
        if offset is None:
            return found, points_seen


def expected_review(ledger, aliases, selected):
    protected = {target for _, target in aliases}
    protected.update(
        row["previous"] for row in ledger if row["code"] == 0 and not row["receipt"]
    )
    publications = [
        row for row in ledger if row["receipt"] and row["collection"] != selected
    ]
    if publications:
        protected.add(publications[-1]["collection"])
    return sorted(
        row["collection"] for row in publications if row["collection"] not in protected
    )


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    # Write requirements before looking at snapshot contents or executing either lane.
    protocol = {
        "schema_version": 1,
        "phases": [{"name": n, "kind": k, "expected_gate": e} for n, k, e in PHASES],
        "common_requirements": [
            "exact stored document/chunk identities and revisions",
            "inconclusive empty/missing-revision evidence blocks promotion",
            "selected data equals last approved source",
            "lost receipts do not change actual alias truth",
            "all aliases, rollback and unfinished references protected",
            "immutable evidence with identical hash checks in both lanes",
        ],
        "shared": [
            "source snapshots",
            "LlamaIndex splitter and local lexical embeddings",
            "Qdrant exporter",
            "publication wrapper",
            "evidence schemas and hash binding",
            "operations inspector and retention policy",
        ],
        "difference": "native Rust checker plus JSON/HTML versus independent trusted-export reconciliation plus JSON",
        "limitations": [
            "shared operational safety is not incremental Rust-engine value",
            "reference supports only this trusted-export workload",
            "single host; alternating lane order is not a statistical latency study",
            "mechanical setup time excludes dependency installation/network and human effort",
        ],
    }
    app.save_json(root / "protocol.json", protocol)
    input_began = time.perf_counter()
    snapshots = {
        name: frozen_inputs(getattr(args, name))
        for name in ("release0", "release1", "release2")
    }
    input_load_seconds = time.perf_counter() - input_began
    if not all(snapshots.values()):
        raise ValueError("Each source snapshot must contain documents")
    setup_began = time.perf_counter()
    server = Server(args.qdrant_binary, root / "server")
    lanes = {
        name: {
            "history": root / name,
            "alias": "repeat-" + name,
            "ledger": [],
            "selected_sources": {},
            "rows": [],
        }
        for name in ("wraith", "reference")
    }
    for lane in lanes.values():
        lane["history"].mkdir()
    summary = {
        "schema_version": 1,
        "status": "incomplete",
        "kind": "frozen repeated-ingestion verifier comparison",
        "protocol_sha256": app.operations.digest(root / "protocol.json"),
        "inputs": {
            name: {
                "documents": len(files),
                "bytes": sum(map(len, files.values())),
                "sha256": digest_files(files),
            }
            for name, files in snapshots.items()
        },
        "provider_calls": 0,
        "phases": [],
        "mechanical_setup": {},
        "comparison": "same operational wrapper; only checker differs",
    }
    try:
        server.start()
        require(server.version == "1.19.0", "Study requires Qdrant 1.19.0")
        summary["mechanical_setup"] = {
            "server_and_empty_histories_seconds": time.perf_counter() - setup_began,
            "source_snapshot_load_seconds": input_load_seconds,
            "dependency_install_seconds": None,
            "human_authoring_seconds": None,
            "shared_integration_requirements": [
                "trusted pre-write chunk manifest",
                "identity/revision payload fields",
                "quiescent candidate generation",
                "job evidence directory",
                "alias promotion ownership",
            ],
            "native_binary_used_only_by": "wraith lane",
        }
        current = dict(snapshots["release0"])
        previous_files = {}
        with closing(connect(server.port)) as client:
            for step, (name, kind, expected_code) in enumerate(PHASES):
                if name == "release-0":
                    current = dict(snapshots["release0"])
                elif name in ("release-1", "rollback-release-1"):
                    current = dict(snapshots["release1"])
                elif name in ("release-2", "restore-release-2", "resume-release-2"):
                    current = dict(snapshots["release2"])
                elif name == "duplicate-content":
                    current["__duplicate_document.txt"] = current[sorted(current)[0]]
                elif name == "rename-document":
                    first = sorted(current)[0]
                    current["__renamed/" + first] = current.pop(first)
                elif name == "remove-five":
                    for document in sorted(current)[: min(5, len(current) - 1)]:
                        del current[document]
                elif name == "empty-feed":
                    current = {}
                source = root / "sources" / f"{step:02}-{name}"
                preparation_began = time.perf_counter()
                materialize(source, current)
                source_preparation_seconds = time.perf_counter() - preparation_began
                source_revisions = {
                    doc: hashlib.sha256(content).hexdigest()
                    for doc, content in current.items()
                    if content.strip()
                }
                delta = {
                    "added": len(current.keys() - previous_files.keys()),
                    "removed": len(previous_files.keys() - current.keys()),
                    "changed": sum(
                        previous_files.get(doc) != data
                        for doc, data in current.items()
                        if doc in previous_files
                    ),
                }
                previous_files = dict(current)
                paired = []
                for lane_name in (
                    ("wraith", "reference")
                    if step % 2 == 0
                    else ("reference", "wraith")
                ):
                    lane = lanes[lane_name]
                    alias = lane["alias"]
                    output = lane["history"] / f"{step:02}-{name}"
                    summary["active_attempt"] = {
                        "phase": name,
                        "lane": lane_name,
                        "kind": kind,
                        "expected_gate": expected_code,
                    }
                    before = app.selected_collection(client, alias)
                    original_add = app.QdrantVectorStore.add
                    original_save = app.save_json

                    def controlled_add(store, nodes, **kwargs):
                        if name == "partial-write":
                            return original_add(store, nodes[:-1], **kwargs)
                        result = original_add(store, nodes, **kwargs)
                        if name == "missing-revision":
                            client.delete_payload(
                                store.collection_name,
                                keys=["revision"],
                                points=[nodes[0].id_],
                                wait=True,
                            )
                        return result

                    def controlled_save(path, value):
                        if name == "lost-receipt" and path.name == "promotion.json":
                            raise OSError("deliberate receipt-write control")
                        original_save(path, value)

                    began = time.perf_counter()
                    error_type = None
                    with (
                        patch.object(app.QdrantVectorStore, "add", controlled_add),
                        patch.object(app, "save_json", controlled_save),
                    ):
                        try:
                            receipt = app.publish(
                                client,
                                source,
                                alias,
                                output,
                                args.wraith if lane_name == "wraith" else None,
                                _verifier=None
                                if lane_name == "wraith"
                                else ("plain-reference-v1", reference_verify),
                            )
                        except OSError as error:
                            if name != "lost-receipt":
                                raise
                            error_type = type(error).__name__
                            receipt = json.loads(
                                (output / "verification.json").read_text()
                            )
                    job_seconds = time.perf_counter() - began
                    summary["active_attempt"]["observed_gate"] = receipt["exit_code"]
                    summary["active_attempt"]["gate_mismatch"] = (
                        receipt["exit_code"] != expected_code
                    )
                    require(
                        receipt["exit_code"] == expected_code,
                        f"{lane_name}/{name}: wrong gate decision",
                    )
                    after = app.selected_collection(client, alias)
                    published = (output / "promotion.json").exists()
                    generation = receipt["generation"]
                    if expected_code == 0:
                        require(
                            after == generation, "Approved generation was not selected"
                        )
                        lane["selected_sources"] = source_revisions
                        require(
                            published == (name != "lost-receipt"), "Wrong receipt state"
                        )
                    else:
                        require(
                            after == before,
                            "Blocked generation replaced selected index",
                        )
                    observed, points_seen = selected_documents(client, after)
                    require(
                        observed == lane["selected_sources"],
                        f"{lane_name}/{name}: selected document identities/revisions disagree with independent source witness",
                    )
                    lane["ledger"].append(
                        {
                            "collection": generation,
                            "previous": before,
                            "code": expected_code,
                            "receipt": published,
                        }
                    )
                    aliases = sorted(
                        (a.alias_name, a.collection_name)
                        for a in client.get_aliases().aliases
                    )
                    expected_candidates = expected_review(
                        lane["ledger"], aliases, after
                    )
                    began = time.perf_counter()
                    inspection = app.operations.inspect(client, lane["history"], alias)
                    inspection_seconds = time.perf_counter() - began
                    actual_candidates = sorted(
                        r["collection"]
                        for r in inspection["collections"]
                        if r["retention_action"] == "review_retirement"
                    )
                    expected_recovery = (
                        "selected_with_receipt"
                        if any(
                            r["collection"] == after and r["receipt"]
                            for r in lane["ledger"]
                        )
                        else "selected_verified_receipt_missing"
                    )
                    require(
                        inspection["inspection_complete"]
                        and inspection["recovery"] == expected_recovery,
                        "Wrong recovery answer",
                    )
                    require(
                        actual_candidates == expected_candidates,
                        "Wrong retention answer",
                    )
                    require(
                        aliases
                        == sorted(
                            (a.alias_name, a.collection_name)
                            for a in client.get_aliases().aliases
                        ),
                        "Inspection changed aliases",
                    )
                    app.save_json(output / "inspection.json", inspection)
                    verify_key = (
                        "wraith_check_with_reports"
                        if lane_name == "wraith"
                        else "plain_check_json_only"
                    )
                    row = {
                        "lane": lane_name,
                        "phase": name,
                        "kind": kind,
                        "expected_gate": expected_code,
                        "observed_gate": receipt["exit_code"],
                        "misdiagnoses": 0,
                        "recovery": inspection["recovery"],
                        "source_documents": len(current),
                        "selected_documents": len(observed),
                        "selected_points": points_seen,
                        "planned_chunks": receipt["chunks"],
                        "delta": delta,
                        "shared_source_preparation_seconds": source_preparation_seconds,
                        "retirement_review_count": len(actual_candidates),
                        "execution_control": error_type,
                        "seconds": {
                            "job_total": job_seconds,
                            "prepare_and_ingest": receipt["seconds"][
                                "prepare_and_ingest"
                            ],
                            "export": receipt["seconds"]["export"],
                            "verification": receipt["seconds"][verify_key],
                            "inspection": inspection_seconds,
                        },
                        "export_reads": receipt["export"]["read_calls"],
                        "html_report": (output / "report.html").exists(),
                    }
                    lane["rows"].append(row)
                    paired.append(row)
                    app.save_json(output / "observation.json", row)
                comparable = (
                    "observed_gate",
                    "recovery",
                    "source_documents",
                    "selected_documents",
                    "selected_points",
                    "planned_chunks",
                    "retirement_review_count",
                )
                require(
                    all(paired[0][key] == paired[1][key] for key in comparable),
                    f"{name}: lane decision disagreement",
                )
                summary["phases"].extend(paired)
                print(
                    json.dumps(
                        {
                            "phase": name,
                            "kind": kind,
                            "gate": expected_code,
                            "decisions_equal": True,
                        }
                    ),
                    flush=True,
                )
        server.stop()
        summary["storage_observation"] = footprint(root / "server/storage")
        summary["totals"] = {
            name: {
                "attempts": len(lane["rows"]),
                "normal_steps": sum(r["kind"] == "normal" for r in lane["rows"]),
                "misdiagnoses": 0,
                "verification_seconds": sum(
                    r["seconds"]["verification"] for r in lane["rows"]
                ),
                "job_seconds": sum(r["seconds"]["job_total"] for r in lane["rows"]),
                "median_inspection_seconds": statistics.median(
                    r["seconds"]["inspection"] for r in lane["rows"]
                ),
            }
            for name, lane in lanes.items()
        }
        summary.pop("active_attempt", None)
        summary["decision"] = (
            "functional parity on the frozen workload; no incremental operational benefit demonstrated for the Rust checker over reconciliation in the shared wrapper"
        )
        summary["status"] = "passed"
        app.save_json(root / "summary.json", summary)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "totals": summary["totals"],
                    "decision": summary["decision"],
                },
                indent=2,
            )
        )
    except BaseException as error:
        summary["error_type"] = type(error).__name__
        summary["failure_detail"] = (
            str(error)
            if isinstance(error, AssertionError)
            else "Execution/setup failure; inspect local evidence"
        )
        app.save_json(root / "incomplete.json", summary)
        raise
    finally:
        server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-binary", type=Path, required=True)
    parser.add_argument("--wraith", type=Path, required=True)
    for name in ("release0", "release1", "release2"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
