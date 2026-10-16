# Verify an ingestion job

**Experimental, source build only. Not included in v0.5.0.**

An ingestion job can finish while a document is only partly indexed. Wraith checks
its intended chunk IDs and revisions against an export of the serving index. It
reports missing chunks, unexpected chunks, outdated revisions, and chunks remaining
for explicit deletion tombstones. Run it after ingestion or before promoting a new
index generation.

This check needs no prompts, test questions, model calls, or agent adapter. It does
need an authoritative ingestion manifest. Export the intended chunks **before the
writes**; deriving expectations from the resulting index would hide failed writes.

## Try it without a database

From this source checkout, with Rust 1.87+:

```sh
cargo build --locked
# Expected exit 1: chunk "1" is missing.
target/debug/wraith index check \
  --manifest examples/index-audit/manifest.jsonl \
  --inventory examples/index-audit/partial.jsonl \
  --html .wraith/index-demo/partial.html

# Expected exit 0: all three intended chunks are present at revision 8.
target/debug/wraith index check \
  --manifest examples/index-audit/manifest.jsonl \
  --inventory examples/index-audit/complete.jsonl
```

Use `target/debug/wraith.exe` on Windows. HTML and JSON paths must be new files;
Wraith never overwrites prior evidence. Add `--json result.json` to save a report or
`--output json` for machine-readable stdout. No `wraith.yaml` is required.

## Use a Qdrant collection

For a working ingestion job that creates its own manifest, start with the
[LlamaIndex document-search example](verified-ingestion.md). It verifies a separate
candidate collection before switching the serving alias.

The optional exporter uses Qdrant's read APIs. It asks for identity/revision payloads,
not vectors or chunk text. Install it in a dedicated environment:

```sh
python3 -m venv .wraith/index-venv
.wraith/index-venv/bin/python -m pip install -r examples/index-audit/requirements.txt
```

On Windows, the virtual environment's interpreter is `Scripts/python.exe`.
Each point must have string payload fields `tenant`, `document_id`, `chunk_id`, and
`revision`. The chunk ID is the logical ID in your ingestion plan, scoped to the
tenant and document; it need not equal Qdrant's physical point ID. Distinct documents
with identical content keep distinct identities.

1. Freeze source changes and collection writes, or select a genuinely immutable
   generation. Wait for completed writes to become visible to the reader.
2. Export your authoritative manifest for that generation, including explicit
   tombstones and a settled state for each ingestion operation.
3. Export the same collection and run the check. Keep writes frozen through both
   exports. A shared label alone does not establish a common snapshot.

```sh
# QDRANT_API_KEY, if required, is read from the environment and never saved.
.wraith/index-venv/bin/python adapters/index/qdrant_export.py \
  --url http://localhost:6333 --collection support \
  --manifest manifest.jsonl --output inventory.jsonl --quiesced

target/debug/wraith index check \
  --manifest manifest.jsonl --inventory inventory.jsonl \
  --json .wraith/ingestion/job-42.json --html .wraith/ingestion/job-42.html
```

`--quiesced` is your attestation that the freeze is in effect. Without it, the
export has `stable: false` and the check is inconclusive. Two equal counts cannot
establish snapshot consistency. The exporter checks counts around pagination,
rejects missing identity fields and duplicate points, and publishes a complete
file only after a successful scan. A missing revision is retained as unknown.
Credentials are accepted only through a named environment variable; remote URLs
require HTTPS. Use database credentials with read-only collection access.

The exporter reads the entire collection, so the manifest scope must describe the
same whole collection. It does not infer filters, tenant ACLs, or an ingestion
watermark. For continuous-write systems without immutable generations, this
prototype is not yet an unattended production monitor.

## Manifest contract

Both files are UTF-8 JSONL: one header, then one row per `(tenant, document_id)`, in
strict UTF-8 byte order. Rows must be unique. Header `record_count` counts document
rows, not chunks; it detects a truncated export even at a complete line boundary.
Schemas for these exports and reports are version 1, independent of agent artifacts.
Unknown versions, unknown fields, duplicate IDs, malformed rows, and unsorted rows
are setup errors.

Manifest example:

```jsonl
{"schema_version":1,"kind":"manifest","scope":"support","generation":"job-42","complete":true,"stable":true,"record_count":2}
{"tenant":"team-a","document_id":"policy","state":"present","settled":true,"revision":"8","expected_chunks":["0","1","2"],"job_id":"ingest-42"}
{"tenant":"team-a","document_id":"retired","state":"deleted","settled":true,"job_id":"delete-41"}
```

Inventory example:

```jsonl
{"schema_version":1,"kind":"inventory","scope":"support","generation":"job-42","complete":true,"stable":true,"record_count":1}
{"tenant":"team-a","document_id":"policy","chunks":[{"id":"0","revision":"8"},{"id":"2","revision":"8"}]}
```

This finds missing chunk `1` for `policy`; the `retired` tombstone passes because no
chunks remain. Comparing only document presence or total chunk counts is insufficient.

- `scope`: same complete collection or explicit partition in both exports.
- `generation`: a common immutable revision/freeze identifier supplied by the exporter.
- `complete`: every row in the declared scope was enumerated. A filtered/failed scan
  cannot claim completeness. The engine cannot verify this assertion independently.
- `stable`: the export represents that frozen generation without concurrent changes.
- `settled`: the application's ingestion and visibility/grace period have finished.
  Keep it false during normal lag. Wraith does not infer this from timestamps.
- `revision`: a source version or content hash, preserved in each indexed chunk.
- `expected_chunks`: exact intended IDs. Missing/null means unknown; an explicit empty
  array means the document intentionally produces no chunks.
- `state: deleted`: authoritative deletion intent. A missing source-list entry alone
  never proves a deletion; unmatched inventory documents remain unknown.
- `job_id`: optional operational identifier included in findings for diagnosis.

For a Postgres ledger, export from a repeatable-read, read-only transaction with
bytewise ordering (`COLLATE "C"`) and explicit tombstones. The transaction does not
freeze Qdrant: the ingestion system must supply the common barrier. No Postgres
connector is included. Other databases can emit the same portable contract.

## Workflow outcomes

| Exit | Meaning | Suggested job behavior |
| --- | --- | --- |
| 0 | All declared document contracts verified | Continue promotion |
| 1 | At least one confirmed discrepancy | Inspect the listed ingestion job and chunk IDs |
| 2 | Invalid input or read/write failure | Fix export/setup; no successful report is implied |
| 3 | Pending ingestion or insufficient evidence | Wait or resolve coverage, then export again |
| 130 | Interrupted | Keep existing evidence; retry with new output paths |

A confirmed discrepancy keeps exit 1 even if another document is unknown. Every
uncertain document remains counted. Incomplete or unstable exports cannot produce
confirmed discrepancies or a passing result. An empty pair is inconclusive.

Use your existing job scheduler's retry and artifact retention. Feed trusted
completed exports to Wraith after the ingestion barrier. Keep credentials out of
untrusted PR jobs; `wraith ci init` still generates the released **agent** workflow,
not an index-monitoring workflow. Use separate output paths per job. The index
reports do not currently appear in `wraith history`.

The CLI never repairs an index. Perform remediation through the owning application,
then export again. A stored chunk is not proof that retrieval exposed it, and absence
from this export is not proof of physical erasure or regulatory compliance.

## Bounds and validation

The Rust engine merges sorted document rows with memory bounded by record size and
report caps, rather than retaining the corpus. Each line is at most 1 MiB; identifiers
are at most 1,024 UTF-8 bytes. Reports retain at most 1,000 document findings and 20
chunk examples per category. Full counts and the number of omitted findings remain
visible. The algorithm reads every row even after a failure, so later corruption
cannot silently produce a valid report.

The optional exporter pages 512 points at a time and uses a temporary on-disk SQLite
sort. Its default cap is one million points (`--max-points` changes it explicitly).
Export disk use grows with the collection; this is not an incremental scan. The
engine's bound does not establish distributed-database or enterprise-scale readiness.

To exercise an actual **local Qdrant client backend** with deliberate partial writes
and deletion leftovers, followed by repair:

```sh
.wraith/index-venv/bin/python examples/index-audit/demo.py \
  --wraith target/debug/wraith --output .wraith/qdrant-demo-1
```

The demo owns an in-memory collection and needs no credentials or models. Its two
before findings clear after repair. These are controlled failures, not discoveries
in a production service. [Research, comparison and product decision](index-product-decision.md).
