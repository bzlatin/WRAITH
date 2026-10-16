#!/usr/bin/env python3
"""Owned localhost Qdrant test: concurrent readers, killed publishers, restart and costs.

Deliberate controls only. Never connects to a user-supplied server or deletes data.
"""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch

import search as app
from reconcile_operations import inspect_plain

ALIAS = "wraith-study"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def connect(port):
    return app.QdrantClient(url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False)


def wait_until(condition, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(0.02)
    raise TimeoutError("Control did not reach its required state")


def footprint(path):
    files = [p for p in path.rglob("*") if p.is_file()]
    sizes = []
    for file in files:
        try:
            sizes.append(file.stat())
        except (
            FileNotFoundError
        ):  # Background optimizer can replace files during sampling.
            pass
    return {
        "logical_bytes": sum(s.st_size for s in sizes),
        "allocated_bytes": sum(getattr(s, "st_blocks", 0) * 512 for s in sizes),
        "files": len(sizes),
    }


class Server:
    def __init__(self, binary, output):
        self.binary = binary.resolve(strict=True)
        self.output = output
        output.mkdir()
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.port = reservation.getsockname()[1]
        config = {
            "log_level": "WARN",
            "telemetry_disabled": True,
            "storage": {"storage_path": "./storage", "snapshots_path": "./snapshots"},
            "service": {"host": "127.0.0.1", "http_port": self.port, "grpc_port": None},
            "cluster": {"enabled": False},
        }
        # JSON is valid YAML; no additional parser or inherited QDRANT__ settings.
        (output / "config.yaml").write_text(json.dumps(config))
        self.process = None
        self.log = None
        self.starts = 0

    def start(self):
        self.starts += 1
        self.log = (self.output / f"server-{self.starts}.log").open("x")
        self.process = subprocess.Popen(
            [str(self.binary), "--config-path", "config.yaml", "--disable-telemetry"],
            cwd=self.output,
            env={"PATH": os.defpath},
            stdout=self.log,
            stderr=self.log,
            start_new_session=True,
        )

        def ready():
            if self.process.poll() is not None:
                raise RuntimeError("Owned Qdrant server exited; inspect its log")
            try:
                with closing(connect(self.port)) as client:
                    info = client.info()
                    return info.version
            except Exception:
                return None

        self.version = wait_until(ready)

    def stop(self, crash=False):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.send_signal(signal.SIGKILL if crash else signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None


class Readers:
    def __init__(self, port, root):
        self.port, self.root = port, root
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.times = []
        self.errors = []
        self.generations = {}
        self.approved = {}
        self.threads = []

    def approve(self, generation):
        if generation in self.approved:
            return self.approved[generation]
        for path in self.root.glob("*/verification.json"):
            try:
                result = json.loads(path.read_text())
                if result["generation"] != generation or result["exit_code"] != 0:
                    continue
                rows = [
                    json.loads(line)
                    for line in (path.parent / "manifest.jsonl")
                    .read_text()
                    .splitlines()[1:]
                ]
                self.approved[generation] = {
                    (d["document_id"], c, d["revision"])
                    for d in rows
                    for c in d["expected_chunks"]
                }
                return self.approved[generation]
            except (json.JSONDecodeError, FileNotFoundError):
                continue
        raise ValueError("Reader saw a generation without a completed passing check")

    def read(self):
        with closing(connect(self.port)) as client:
            vector = app.LexicalEmbedding().get_query_embedding(
                "Python exception refund payment"
            )
            while not self.stop_event.is_set():
                began = time.perf_counter()
                try:
                    points = client.query_points(
                        ALIAS,
                        query=vector,
                        using=app.VECTOR_NAME,
                        limit=3,
                        with_payload=[
                            "document_id",
                            "chunk_id",
                            "revision",
                            "study_generation",
                        ],
                    ).points
                    generations = {p.payload["study_generation"] for p in points}
                    if len(generations) != 1:
                        raise ValueError("Empty or mixed-generation query result")
                    generation = generations.pop()
                    with self.lock:
                        expected = self.approve(generation)
                        if any(
                            (
                                p.payload["document_id"],
                                p.payload["chunk_id"],
                                p.payload["revision"],
                            )
                            not in expected
                            for p in points
                        ):
                            raise ValueError(
                                "Reader saw chunks outside the approved manifest"
                            )
                        self.generations[generation] = (
                            self.generations.get(generation, 0) + 1
                        )
                        self.times.append(time.perf_counter() - began)
                except Exception as error:
                    with self.lock:
                        self.errors.append(type(error).__name__)
                self.stop_event.wait(0.02)

    def start(self):
        self.threads = [
            threading.Thread(target=self.read, daemon=True) for _ in range(2)
        ]
        for thread in self.threads:
            thread.start()

    def count(self):
        with self.lock:
            return len(self.times)

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=15)
        if any(t.is_alive() for t in self.threads):
            raise RuntimeError("Reader did not stop")
        ordered = sorted(self.times)
        return {
            "successful_queries": len(ordered),
            "errors": len(self.errors),
            "error_types": sorted(set(self.errors)),
            "generations_observed": len(self.generations),
            "latency_ms": {
                "median": ordered[len(ordered) // 2] * 1000 if ordered else None,
                "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000
                if ordered
                else None,
            },
        }


def worker(args):
    """Only called by this runner against its freshly created localhost server."""
    output = args.output
    original_add = app.QdrantVectorStore.add

    def pause(collection):
        app.save_json(
            output / "paused.json", {"stage": args.stage, "collection": collection}
        )
        threading.Event().wait(120)
        raise TimeoutError("Parent did not interrupt the paused control")

    def add(store, nodes, **kwargs):
        # Observable test labels are actually persisted; they do not replace real payload IDs.
        for node in nodes:
            node.metadata["study_generation"] = store.collection_name
            node.excluded_embed_metadata_keys.append("study_generation")
        if args.stage == "during-write":
            original_add(store, nodes[: max(1, min(64, len(nodes) // 2))], **kwargs)
            pause(store.collection_name)
        if args.stage == "partial-ack":
            return original_add(store, nodes[1:], **kwargs)
        return original_add(store, nodes, **kwargs)

    with closing(connect(args.port)) as client:
        original_promote = client.update_collection_aliases

        def promote(*positional, **kwargs):
            generation = json.loads((output / "verification.json").read_text())[
                "generation"
            ]
            if args.stage == "before-promotion":
                pause(generation)
            result = original_promote(*positional, **kwargs)
            if args.stage == "after-promotion":
                pause(generation)
            return result

        with (
            patch.object(app.QdrantVectorStore, "add", add),
            patch.object(client, "update_collection_aliases", promote),
        ):
            result = app.publish(
                client, args.source, ALIAS, output, args.wraith, compare_plain=True
            )
        expected = 1 if args.stage == "partial-ack" else 0
        if result["exit_code"] != expected:
            raise RuntimeError("Import did not produce the expected gate decision")


def logical_state(client):
    """Control-only readback, outside the inspection timing. Does not fetch text/vectors."""
    collections = sorted(c.name for c in client.get_collections().collections)
    aliases = sorted(
        (a.alias_name, a.collection_name) for a in client.get_aliases().aliases
    )
    state = {}
    for collection in collections:
        value = hashlib.sha256()
        offset = None
        while True:
            points, offset = client.scroll(
                collection,
                offset=offset,
                limit=512,
                with_payload=[
                    "tenant",
                    "document_id",
                    "chunk_id",
                    "revision",
                    "study_generation",
                ],
                with_vectors=False,
            )
            for point in points:
                value.update(
                    json.dumps([str(point.id), point.payload], sort_keys=True).encode()
                )
            if offset is None:
                break
        state[collection] = value.hexdigest()
    return {"aliases": aliases, "collection_metadata_sha256": state}


def operation_controls(client, root):
    selected = app.selected_collection(client, ALIAS)
    expected_active = json.loads(
        (root / "after-promotion/verification.json").read_text()
    )["generation"]
    first = json.loads((root / "initial/verification.json").read_text())["generation"]
    require(selected == expected_active, "Independent alias witness disagrees")
    before = logical_state(client)
    began = time.perf_counter()
    inspection = app.operations.inspect(client, root, ALIAS)
    inspection_seconds = time.perf_counter() - began
    began = time.perf_counter()
    reference = inspect_plain(client, root, ALIAS)
    reference_seconds = time.perf_counter() - began
    require(
        inspection["recovery"] == "selected_verified_receipt_missing",
        "Failed to recover the missing-receipt window",
    )
    require(
        inspection["selected_collection"] == selected
        and inspection["inspection_complete"],
        "Recovery selected an unverified collection",
    )
    candidates = [
        r["collection"]
        for r in inspection["collections"]
        if r["retention_action"] == "review_retirement"
    ]
    require(
        candidates == [first],
        "Retention did not protect aliases, rollback and unfinished jobs",
    )
    require(
        reference["selected_collection"] == selected
        and reference["recovery"] == inspection["recovery"]
        and reference["review_candidates"] == candidates,
        "Trusted-input reference disagreed",
    )
    require(
        logical_state(client) == before, "Inspection changed stored metadata or aliases"
    )
    app.save_json(root / "operations.json", inspection)
    (root / "operations.txt").write_text(app.operations.human(inspection) + "\n")
    app.save_json(root / "operations-plain.json", reference)
    # A second alias is a real database reference, even when it is not the selected workflow.
    client.update_collection_aliases(
        change_aliases_operations=[
            app.models.CreateAliasOperation(
                create_alias=app.models.CreateAlias(
                    collection_name=first, alias_name="operator-hold"
                )
            )
        ]
    )
    held = app.operations.inspect(client, root, ALIAS)
    require(held["retention"]["review_candidates"] == 0, "Other alias was ignored")
    app.save_json(root / "operations-held.json", held)
    # Preserve originals. Change only a copy to test evidence-integrity handling.
    copied = root / "altered-history-copy"
    copied.mkdir()
    for stage in (
        "initial",
        "repeat",
        "partial-ack",
        "during-write",
        "before-promotion",
        "after-promotion",
    ):
        destination = copied / stage
        destination.mkdir()
        for name in (
            "job.json",
            "manifest.jsonl",
            "inventory.jsonl",
            "report.json",
            "verification.json",
            "promotion.json",
        ):
            path = root / stage / name
            if path.exists():
                shutil.copyfile(path, destination / name)
    report_path = copied / "after-promotion/report.json"
    altered = json.loads(report_path.read_text())
    altered["status"] = "failed"
    report_path.write_text(json.dumps(altered))
    rejected = app.operations.inspect(client, copied, ALIAS)
    trusted_reference = inspect_plain(client, copied, ALIAS)
    require(
        not rejected["inspection_complete"]
        and rejected["retention"]["review_candidates"] == 0,
        "Changed evidence was accepted",
    )
    require(
        trusted_reference["recovery"] == "selected_verified_receipt_missing",
        "Reference no longer demonstrates its trusted-input limit",
    )
    app.save_json(root / "operations-altered.json", rejected)
    return {
        "recovery_answer_correct": True,
        "retirement_candidates_correct": True,
        "logical_metadata_and_aliases_unchanged_by_inspection": True,
        "other_alias_protected": True,
        "altered_evidence_rejected": True,
        "trusted_reference_also_answers_normal_case": True,
        "trusted_reference_does_not_detect_altered_report": True,
        "review_candidate_points": inspection["retention"]["candidate_points"],
        "no_deletion_performed": True,
        "seconds": {
            "inspection": inspection_seconds,
            "trusted_reference": reference_seconds,
        },
        "scope": "deliberate server interruption and copied-evidence controls; no human-effort or adoption inference",
    }


def run(args):
    if os.name != "posix":
        raise ValueError("Server interruption checks currently require POSIX signals")
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source"
    source.mkdir()
    for relative, content in app.read_source(args.source.resolve()):
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    source_files = sorted(p for p in source.rglob("*") if p.is_file())
    digest = hashlib.sha256()
    for path in source_files:
        digest.update(
            path.relative_to(source).as_posix().encode()
            + b"\0"
            + hashlib.sha256(path.read_bytes()).digest()
        )
    server = Server(args.qdrant_binary, root / "server")
    summary = {
        "schema_version": 1,
        "kind": "owned localhost server controls; no natural defect claims",
        "source": {
            "files": len(source_files),
            "bytes": sum(p.stat().st_size for p in source_files),
            "sha256": digest.hexdigest(),
        },
        "phases": [],
        "provider_calls": 0,
        "environment": {
            "os": sys.platform,
            "python": sys.version.split()[0],
            "qdrant_binary_sha256": hashlib.sha256(
                args.qdrant_binary.read_bytes()
            ).hexdigest(),
            "wraith_binary_sha256": hashlib.sha256(
                args.wraith.read_bytes()
            ).hexdigest(),
        },
    }
    readers = None
    child = None
    child_log = None
    started = time.perf_counter()
    try:
        server.start()
        summary["qdrant_version"] = server.version
        if server.version != "1.19.0":
            raise ValueError("This study is pinned to Qdrant 1.19.0")
        for stage in [
            "initial",
            "repeat",
            "partial-ack",
            "during-write",
            "before-promotion",
            "after-promotion",
        ]:
            output = root / stage
            with closing(connect(server.port)) as client:
                before = app.selected_collection(client, ALIAS)
            readers = Readers(server.port, root) if before else None
            if readers:
                readers.start()
                wait_until(lambda: readers.count() >= 10)
            phase_start = time.perf_counter()
            child_log = (root / f"{stage}.log").open("x")
            child = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    "--port",
                    str(server.port),
                    "--stage",
                    stage,
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                    "--wraith",
                    str(args.wraith.resolve()),
                ],
                stdout=child_log,
                stderr=child_log,
                start_new_session=True,
            )
            if stage in ("initial", "repeat", "partial-ack"):
                child.wait(timeout=600)
                if child.returncode != 0:
                    raise RuntimeError(f"{stage} import failed; inspect phase log")
            else:

                def paused():
                    if child.poll() is not None:
                        raise RuntimeError("Control exited before its pause marker")
                    try:
                        return json.loads((output / "paused.json").read_text())
                    except (FileNotFoundError, json.JSONDecodeError):
                        return None

                marker = wait_until(paused, timeout=600)
                count = readers.count()
                wait_until(lambda: readers.count() >= count + 10)
                if stage == "during-write":
                    with closing(connect(server.port)) as client:
                        pending = app.operations.inspect(client, root, ALIAS)
                        row = next(
                            r
                            for r in pending["collections"]
                            if r["collection"] == marker["collection"]
                        )
                        require(
                            row["retention_action"] == "keep"
                            and row["evidence_state"] == "unfinished",
                            "In-flight candidate was not protected",
                        )
                        app.save_json(root / "operations-inflight.json", pending)
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=15)
            exit_code = child.returncode
            child = None
            child_log.close()
            child_log = None
            with closing(connect(server.port)) as client:
                after = app.selected_collection(client, ALIAS)
                if stage in ("partial-ack", "during-write", "before-promotion"):
                    require(
                        after == before, "Unapproved candidate replaced serving index"
                    )
                elif stage == "after-promotion":
                    require(
                        after == marker["collection"] and after != before,
                        "Server control invariant failed",
                    )
                    require(
                        not (output / "promotion.json").exists(),
                        "Control did not exercise missing-receipt window",
                    )
                else:
                    require(
                        after
                        == json.loads((output / "promotion.json").read_text())[
                            "collection"
                        ],
                        "Server control invariant failed",
                    )
                if readers:
                    count = readers.count()
                    wait_until(lambda: readers.count() >= count + 10)
                observations = readers.stop() if readers else None
                readers = None
                if observations:
                    require(
                        observations["errors"] == 0
                        and observations["successful_queries"] >= 20,
                        "Server control invariant failed",
                    )
                phase = {
                    "stage": stage,
                    "publisher_exit": exit_code,
                    "wall_seconds_including_worker_startup": time.perf_counter()
                    - phase_start,
                    "alias_changed": before != after,
                    "readers": observations,
                    "retained_collections": len(client.get_collections().collections),
                    "storage_observation": footprint(root / "server/storage"),
                }
                if (output / "verification.json").exists():
                    receipt = json.loads((output / "verification.json").read_text())
                    phase["verification"] = {
                        k: receipt[k]
                        for k in (
                            "exit_code",
                            "plain_exit_code",
                            "documents",
                            "chunks",
                            "export",
                            "seconds",
                        )
                    }
                if stage == "during-write":
                    phase["partial_points"] = client.count(
                        marker["collection"], exact=True
                    ).count
            summary["phases"].append(phase)
            app.save_json(root / f"{stage}-observation.json", phase)
            print(json.dumps({"completed": stage, "readers": observations}), flush=True)
        # A server outage is a separate recovery control, excluded from serving-read samples.
        with closing(connect(server.port)) as client:
            selected = app.selected_collection(client, ALIAS)
        began = time.perf_counter()
        server.stop(crash=True)
        server.start()
        with closing(connect(server.port)) as client:
            require(
                app.selected_collection(client, ALIAS) == selected,
                "Server control invariant failed",
            )
            restart = root / "restart"
            restart.mkdir()
            manifest = root / "after-promotion/manifest.jsonl"
            header = app.exporter.read_header(manifest)
            app.exporter.export_inventory(
                client, selected, header, restart / "inventory.jsonl", quiesced=True
            )
            result = subprocess.run(
                [
                    str(args.wraith.resolve()),
                    "index",
                    "check",
                    "--manifest",
                    str(manifest),
                    "--inventory",
                    str(restart / "inventory.jsonl"),
                    "--json",
                    str(restart / "report.json"),
                    "--html",
                    str(restart / "report.html"),
                ],
                stdout=subprocess.DEVNULL,
                timeout=60,
            )
            require(
                result.returncode == 0,
                "Post-crash inventory did not match the approved manifest",
            )
            require(
                app.search(client, ALIAS, "Python exception refund payment"),
                "Server control invariant failed",
            )
        summary["server_restart"] = {
            "forced_kill": True,
            "alias_preserved": True,
            "full_inventory_exit": result.returncode,
            "recovery_and_full_audit_seconds": time.perf_counter() - began,
        }
        with closing(connect(server.port)) as client:
            summary["operations"] = operation_controls(client, root)
        server.stop()
        summary["final_storage"] = footprint(root / "server/storage")
        summary["elapsed_seconds"] = time.perf_counter() - started
        summary["status"] = "passed"
        app.save_json(root / "summary.json", summary)
        print(json.dumps(summary, indent=2))
    except BaseException as error:
        summary["status"] = "incomplete"
        summary["error_type"] = type(error).__name__
        app.save_json(root / "incomplete.json", summary)
        raise
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=15)
        if child_log:
            child_log.close()
        if readers:
            readers.stop()
        server.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-binary", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wraith", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--stage", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
    else:
        if args.qdrant_binary is None:
            parser.error("--qdrant-binary is required")
        run(args)
