# Test ingestion against a Qdrant server

The optional server runner starts its own standalone Qdrant process on loopback,
runs concurrent readers and deliberately interrupts publishers. It never connects
to an existing database. This extends the [local document-search example](verified-ingestion.md)
with actual HTTP writes, reads and server recovery checks.

## Run it

Use Python 3.10+, a source-built Wraith and the optional dependencies from
`examples/verified-ingestion/requirements.txt`. macOS and Linux need permission to
start a localhost listener and send POSIX signals to owned test processes.

From the repository root:

```sh
# Network preparation: checksummed official Qdrant 1.19.0 binary.
.wraith/ingestion-venv/bin/python examples/verified-ingestion/fetch_fixtures.py \
  --output .wraith/qdrant-server-bin

# Runtime uses only localhost and public example files. Choose a new output directory.
.wraith/ingestion-venv/bin/python examples/verified-ingestion/server_check.py \
  --qdrant-binary .wraith/qdrant-server-bin/qdrant \
  --source examples/verified-ingestion/documents \
  --output .wraith/server-check/first --wraith target/debug/wraith
```

The downloader supports macOS arm64/x86_64 and Linux x86_64. The runner requires
POSIX; Windows server interruption checks are not implemented. It disables Qdrant
telemetry and gRPC, binds HTTP to `127.0.0.1`, and starts with a minimal environment
so inherited Qdrant settings cannot redirect storage or listeners. The downloader
uses internet access; the runner needs no external service, API key or model call.

For the larger public corpus:

```sh
.wraith/ingestion-venv/bin/python examples/verified-ingestion/fetch_fixtures.py \
  --corpus --output .wraith/cpython-corpus

.wraith/ingestion-venv/bin/python examples/verified-ingestion/server_check.py \
  --qdrant-binary .wraith/qdrant-server-bin/qdrant \
  --source .wraith/cpython-corpus/documents \
  --output .wraith/server-check/cpython --wraith target/release/wraith
```

Build the release binary with `cargo build --release --locked` first. The corpus
is the first 200 sorted regular `Doc/library/**/*.rst` files from CPython 3.13.0,
commit `60403a5409ff2c3f3b07dd2ca91a7a3e096839c7`, imported as plain text. Preparation
preserves CPython's license and records the archive checksum. This is public technical
documentation, not a customer's corpus or a semantic retrieval benchmark.

## What is checked

| Phase | Required outcome |
| --- | --- |
| Initial import and repeat import | Both checks pass; the selected collection changes |
| Writer acknowledges a missing chunk | Both checks fail; the selected collection stays unchanged |
| Publisher killed after a partial write | Previous collection stays selected |
| Publisher killed after verification, before alias update | Previous collection stays selected |
| Publisher killed after alias update, before receipt | Verified candidate is selected despite the missing receipt |
| Server killed and restarted | Alias survives; full inventory matches the selected manifest |

Two independent reader clients search during every phase after initialization.
They check that each response belongs to one generation with a saved passing gate,
and that its observed identities/revisions belong to that generation's manifest.
The runner adds a persisted generation label to test points for this observation.
It does not change the source text, replace the real SDK or fabricate write results.
The partial-write and pause points are deliberate controls at the library boundary.

A killed publisher retaining the old alias is an orchestration property. It would
also hold with the plain script. The acknowledged partial write exercises Wraith's
actual failure decision; the plain script catches it too.

The runner also validates [read-only recovery and retention](ingestion-operations.md):
missing receipts, in-flight jobs, another alias referencing an old collection, unchanged
point metadata and altered evidence. This extension saves `operations.json`, a readable
`operations.txt`, the trusted-input reference result and the control reports.

## Measured results

One complete macOS arm64 run used Qdrant 1.19.0, Python 3.13 and a release Wraith:

- 200 documents, 3,954,237 source bytes, 4,725 chunks per complete generation.
- Preparation and ingestion: 1.63–1.80 seconds per completed write stage.
- Export: 0.127–0.219 seconds, with 12 explicit client read calls per scan.
- Wraith subprocess plus JSON/HTML: 24–27 ms. Plain in-process reconciliation: 7.6–9.2 ms.
- 1,215 successful sampled concurrent queries; zero errors or mixed/unapproved generations.
- Forced server restart preserved the alias; recovery plus full export/audit took 0.89 seconds.
- Six retained collections: 186,200,064 allocated bytes (about 178 MiB) after shutdown.
  Logical file lengths totaled about 2.0 GB, including sparse/preallocated files.

[Recorded results](../examples/verified-ingestion/server-results.json) include phase
counts, timings, storage observations and binary/source fingerprints. Earlier local
measurements remain in [the original results](../examples/verified-ingestion/results.json).
Timings include different output work for Wraith and the script, and exclude Python
imports from the individual stage times. Export cost applies to both approaches.
Allocated blocks change with background optimization and are not a billing estimate.
The server outage is excluded from concurrent-query samples and measured separately.
These observations do not estimate a production error rate or demonstrate human time savings.

The run directory preserves phase reports, manifests, inventories, server logs,
partial collections and copied source files. Only supported `.md`/`.txt` documents
are copied, under the example's size limits; symlinks are rejected. `summary.json` appears only after all
controls pass. A failed run saves `incomplete.json` when possible; choose a new
output directory for a later attempt. The runner stops and reaps its own processes.
It retains data rather than deleting evidence automatically.

## Decision and limits

The check works over HTTP at this corpus size, including one observed server restart.
No naturally occurring defect, customer adoption or paid demand was established.
Standalone alias updates follow Qdrant's [documented atomic operations](https://qdrant.tech/documentation/manage-data/collections/#collection-aliases).
Multiple publishers, clusters, network partitions, crash timing inside the alias
operation, storage exhaustion and sustained production load remain untested.

The observed recovery gap is a missing receipt after successful promotion. The
actual alias and its matching passing verification must be inspected together.
Retained generations also accumulate storage. A [recovery summary and retention plan](ingestion-operations.md)
now addresses these inspection questions and is compared with a small reference recipe.
The [extension results](../examples/verified-ingestion/operations-results.json) preserve
the original measurements separately. Automatic deletion, repair and a hosted service
remain outside this evidence.
