"""Integration controls: real LlamaIndex and Qdrant local backend, no model calls."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import search as app

sys.path.insert(0, str(app.ROOT / "adapters/index"))
from llamaindex_manifest import ManifestCapture, attach_capture

WRAITH = None


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "refunds.md").write_text(
            "Refunds go to the original payment method."
        )
        (self.source / "security.md").write_text(
            "Enable two factor authentication for security."
        )
        self.client = app.QdrantClient(path=str(self.root / "db"))
        self.addCleanup(self.client.close)
        # Local ingestion/query must never attempt a network connection.
        self.network = patch.object(
            socket.socket, "connect", side_effect=AssertionError("network is forbidden")
        )
        self.network.start()
        self.addCleanup(self.network.stop)

    def publish(self, label):
        return app.publish(
            self.client,
            self.source,
            "serving",
            self.root / label,
            WRAITH,
            compare_plain=True,
        )

    def assert_retained(self, expected):
        self.assertEqual(app.selected_collection(self.client, "serving"), expected)
        self.assertEqual(
            app.search(self.client, "serving", "refunds payment")[0]["document"],
            "refunds.md",
        )

    def test_updates_deletions_duplicates_and_repeat_builds(self):
        initial = self.publish("initial")
        self.assertEqual(initial["exit_code"], 0)
        self.assertTrue((self.root / "initial/promotion.json").exists())
        self.assert_retained(initial["generation"])
        # Content equality must not collapse independent document identities.
        (self.source / "copy.md").write_text((self.source / "refunds.md").read_text())
        (self.source / "security.md").unlink()
        updated = self.publish("updated")
        self.assertEqual(updated["exit_code"], 0)
        points, _ = self.client.scroll(updated["generation"], limit=100)
        self.assertEqual(
            {p.payload["document_id"] for p in points}, {"copy.md", "refunds.md"}
        )
        self.assertTrue(self.client.collection_exists(initial["generation"]))
        (self.source / "refunds.md").write_text(
            "Refund requests now require a receipt."
        )
        changed = self.publish("changed")
        first = json.loads(
            (self.root / "initial/manifest.jsonl").read_text().splitlines()[1]
        )
        latest = [
            json.loads(line)
            for line in (self.root / "changed/manifest.jsonl")
            .read_text()
            .splitlines()[1:]
        ]
        self.assertNotEqual(
            first["revision"],
            next(r["revision"] for r in latest if r["document_id"] == "refunds.md"),
        )
        repeat = self.publish("repeat")
        self.assertEqual(repeat["exit_code"], 0)
        self.assertNotEqual(changed["generation"], repeat["generation"])
        self.assertEqual(repeat["chunks"], changed["chunks"])

    def test_partial_write_acknowledged_but_never_promoted(self):
        (self.source / "refunds.md").write_text(
            "Refunds go to the original payment method. " * 60
        )
        initial = self.publish("initial")
        original = app.QdrantVectorStore.add

        def partial(store, nodes, **kwargs):
            manifest = self.root / "partial/manifest.jsonl"
            self.assertTrue(manifest.is_file())  # Expectations exist before writes.
            self.assertGreater(sum(n.ref_doc_id == "refunds.md" for n in nodes), 1)
            result = original(store, nodes[1:], **kwargs)
            self.assert_retained(
                initial["generation"]
            )  # Old alias still queryable mid-build.
            return result

        with patch.object(app.QdrantVectorStore, "add", partial):
            result = self.publish("partial")
        self.assertEqual((result["exit_code"], result["plain_exit_code"]), (1, 1))
        report = json.loads((self.root / "partial/report.json").read_text())
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(
            self.client.count(result["generation"], exact=True).count,
            initial["chunks"] - 1,
        )
        self.assertFalse((self.root / "partial/promotion.json").exists())
        self.assert_retained(initial["generation"])

    def test_failed_writer_preserves_evidence_and_serving_index(self):
        initial = self.publish("initial")
        original = app.QdrantVectorStore.add

        def interrupted(store, nodes, **kwargs):
            original(store, nodes[:1], **kwargs)
            raise RuntimeError("simulated interrupted ingestion")

        with patch.object(app.QdrantVectorStore, "add", interrupted):
            with self.assertRaises(RuntimeError):
                self.publish("interrupted")
        self.assertTrue((self.root / "interrupted/manifest.jsonl").exists())
        self.assertFalse((self.root / "interrupted/promotion.json").exists())
        self.assertEqual(
            json.loads((self.root / "interrupted/error.json").read_text())["phase"],
            "ingest",
        )
        self.assert_retained(initial["generation"])
        with self.assertRaises(FileExistsError):
            self.publish("interrupted")

    def test_missing_revision_blocks_as_unknown(self):
        initial = self.publish("initial")
        original = app.QdrantVectorStore.add

        def missing_revision(store, nodes, **kwargs):
            result = original(store, nodes, **kwargs)
            self.client.delete_payload(
                store.collection_name,
                keys=["revision"],
                points=[nodes[0].id_],
                wait=True,
            )
            return result

        with patch.object(app.QdrantVectorStore, "add", missing_revision):
            result = self.publish("unknown")
        self.assertEqual(result["exit_code"], 3)
        self.assertFalse((self.root / "unknown/promotion.json").exists())
        self.assert_retained(initial["generation"])

    def test_empty_source_does_not_replace_a_working_index(self):
        initial = self.publish("initial")
        for path in self.source.iterdir():
            path.unlink()
        result = self.publish("empty")
        self.assertEqual(result["exit_code"], 3)
        self.assert_retained(initial["generation"])

    def test_alias_cannot_shadow_collection(self):
        self.client.create_collection(
            "serving",
            vectors_config=app.models.VectorParams(
                size=app.DIMENSIONS,
                distance=app.models.Distance.COSINE,
            ),
        )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.publish("conflict")
        self.assertIsNone(app.selected_collection(self.client, "serving"))

    def test_verifier_execution_failure_never_promotes(self):
        initial = self.publish("initial")
        with patch.object(
            app.subprocess, "run", side_effect=subprocess.TimeoutExpired("wraith", 60)
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.publish("timeout")
        self.assert_retained(initial["generation"])
        self.assertFalse((self.root / "timeout/promotion.json").exists())

    def test_snapshot_does_not_include_unrelated_files(self):
        (self.source / ".env").write_text("private test sentinel")
        self.assertEqual(
            {name for name, _ in app.read_source(self.source)},
            {"refunds.md", "security.md"},
        )
        if sys.platform == "win32":
            return
        (self.source / "link.md").symlink_to(self.root / "outside.md")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            list(app.read_source(self.source))

    def test_repeat_runner_stops_server_after_readiness_failure(self):
        import repeat_workflow
        from types import SimpleNamespace

        stopped = []

        class FailedServer:
            def __init__(self, binary, output):
                pass

            def start(self):
                raise RuntimeError("deliberate readiness failure")

            def stop(self):
                stopped.append(True)

        args = SimpleNamespace(
            output=self.root / "failed-repeat",
            release0=self.source,
            release1=self.source,
            release2=self.source,
            qdrant_binary=WRAITH,
            wraith=WRAITH,
        )
        with patch.object(repeat_workflow, "Server", FailedServer):
            with self.assertRaisesRegex(RuntimeError, "readiness"):
                repeat_workflow.run(args)
        self.assertEqual(stopped, [True])
        self.assertTrue((args.output / "protocol.json").is_file())
        self.assertTrue((args.output / "incomplete.json").is_file())
        self.assertFalse((args.output / "summary.json").exists())

    def test_directory_lock_prevents_second_local_owner(self):
        result = subprocess.run(
            [
                sys.executable,
                str(Path(app.__file__)),
                "--db",
                str(self.root / "db"),
                "query",
                "refund",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("RuntimeError", result.stderr)

    def test_malformed_source_creates_no_candidate_collection(self):
        (self.source / "invalid.md").write_bytes(b"\xff")
        with self.assertRaises(UnicodeDecodeError):
            self.publish("invalid")
        self.assertEqual(self.client.get_collections().collections, [])
        self.assertFalse((self.root / "invalid/promotion.json").exists())

    def test_manifest_hook_rejects_cache_and_document_skip_modes(self):
        from llama_index.core.storage.docstore import SimpleDocumentStore

        capture = ManifestCapture(
            destination=str(self.root / "manifest.jsonl"),
            scope="test",
            generation="first",
            tenant="docs",
            revisions={"d": "r"},
        )
        for pipeline in (
            app.IngestionPipeline(transformations=[]),
            app.IngestionPipeline(
                transformations=[], disable_cache=True, docstore=SimpleDocumentStore()
            ),
        ):
            with self.assertRaisesRegex(ValueError, "disable_cache"):
                attach_capture(pipeline, capture)
        self.assertFalse((self.root / "manifest.jsonl").exists())

    def test_manifest_hook_stops_before_write_on_reused_evidence(self):
        from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

        path = self.root / "manifest.jsonl"
        path.write_text("original evidence\n")
        capture = ManifestCapture(
            destination=str(path),
            scope="test",
            generation="first",
            tenant="docs",
            revisions={"d": "r"},
        )
        node = TextNode(
            text="refund",
            id_="chunk",
            relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id="d")},
        )
        store = app.QdrantVectorStore(client=self.client, collection_name="hook")
        pipeline = app.IngestionPipeline(
            transformations=[app.LexicalEmbedding()],
            vector_store=store,
            disable_cache=True,
        )
        attach_capture(pipeline, capture)
        with patch.object(app.QdrantVectorStore, "add") as write:
            with self.assertRaises(FileExistsError):
                pipeline.run(nodes=[node])
            write.assert_not_called()
        self.assertEqual(path.read_text(), "original evidence\n")

    def test_manifest_hook_rejects_unknown_source_and_duplicate_chunks(self):
        from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

        capture = ManifestCapture(
            destination=str(self.root / "manifest.jsonl"),
            scope="test",
            generation="first",
            tenant="docs",
            revisions={"d": "r"},
        )
        node = TextNode(
            text="refund",
            id_="chunk",
            relationships={NodeRelationship.SOURCE: RelatedNodeInfo(node_id="d")},
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            capture([node, node])
        node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id="unknown")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            capture([node])
        self.assertFalse((self.root / "manifest.jsonl").exists())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wraith", type=Path, required=True)
    args, rest = parser.parse_known_args()
    WRAITH = args.wraith.resolve(strict=True)
    unittest.main(argv=[sys.argv[0], *rest])
