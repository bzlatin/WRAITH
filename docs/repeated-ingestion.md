# Repeated document updates: Wraith and reconciliation

The finite comparison is complete. Both verifiers made the expected decisions in
all 14 steps per lane. The integration's guardrails worked, but this workload did
not demonstrate an additional operational benefit from the Rust checker over plain
reconciliation using the same wrapper.

## What ran

Two aliases on an owned localhost Qdrant 1.19.0 server received the same document
snapshots. Both lanes used the same LlamaIndex splitter, lexical embeddings,
Qdrant exporter, publication logic, evidence hashes, recovery inspector and retention
rules. Only the verifier changed:

- Wraith: native Rust subprocess, JSON and HTML reports.
- Reference: independent set/revision reconciliation of trusted exports, JSON only.

The reference is explicitly recorded as `plain-reference-v1` in job evidence and
inspection output. It calls no Wraith evaluator. The inspector validates both lanes'
evidence identically; its benefits cannot be attributed uniquely to the Rust checker.
There is no alternate-verifier option in the normal example CLI.

The runner saves its protocol before reading inputs or executing either lane.
It alternates which lane runs first, preserves new directories for each attempt,
and stops on a wrong answer or execution error. Incomplete attempts retain their
protocol and available observations rather than being replaced.

| Sequence | Classification | Required result |
| --- | --- | --- |
| CPython 3.13.0 → 3.13.1 → repeat → 3.13.2 → rollback | Normal source changes | Approve correct snapshots |
| Duplicate content, rename one document, remove five, restore | Normal source changes | Preserve exact identities and revisions |
| Acknowledge a missing chunk | Deliberate control | Block publication |
| Remove one indexed revision field | Deliberate control | Inconclusive; keep selected index |
| Fail receipt writing after publication | Deliberate control | Recover actual selected generation |
| Empty source feed | Deliberate control | Inconclusive; keep selected index |
| Resume the latest release | Normal source change | Approve and inspect normally |

Each release contributes its first 200 sorted regular `Doc/library/**/*.rst` files,
imported as plain text. Moving the selection boundary changes membership; removed
entries are not a claim that those files were deleted upstream. Snapshot 3.13.0 to
3.13.1 changed 31 retained documents and added/removed 17 selected paths. The next
release changed 31 retained documents and added/removed one selected path.

An independent source witness hashes raw file bytes and scrolls actual selected
points to check document identities/revisions after every attempt. A separate event
ledger supplies expected recovery and retention answers. This is a scripted workflow
using public documents, not independent adoption or a natural defect discovery.

## Results

| Observed on one macOS arm64 host | Wraith | Reference |
| --- | --- | --- |
| Attempts | 14 | 14 |
| Normal transitions | 10 | 10 |
| Wrong answers in this sequence | 0 | 0 |
| Deliberate partial write blocked | 1 | 1 |
| Expected inconclusive outcomes | 2 | 2 |
| Lost-receipt state correctly inspected | 1 | 1 |
| Total verifier time | 0.480 s | 0.165 s |
| Total ingestion-job time | 24.57 s | 24.39 s |
| Median inspection time | 23.8 ms | 23.4 ms |

[Recorded outputs, source checksums and limits](../examples/verified-ingestion/repeated-results.json).
Wraith also produced HTML, and the reference ran in process. These timings involve
different work; they do not establish causal overhead, statistical significance or
human time saved. No production false-positive rate is estimated from these cases.

Mechanical source loading took 0.089 seconds and server/history setup took 0.137
seconds. Dependency installation, network preparation and human authoring were not
measured. Both lanes still required a trusted pre-write manifest, payload identities,
a quiescent candidate generation, evidence storage and an owner of publication.
The Rust binary was used only by Wraith. This experiment does not measure first-time
installation or standalone reference deployment.

All 28 candidate collections and their evidence were retained: about 798 MiB of
allocated filesystem blocks after shutdown. Logical file lengths were 9.37 GB,
including sparse/preallocated files. No deletion or byte-saving claim was made.
The full-rebuild example still cannot deliberately publish an empty corpus through
this manifest contract; the empty-feed control shows that conservative limitation.

## Reproduce

Use the setup in [verified ingestion](verified-ingestion.md), then prepare pinned
fixtures in new directories. Network access is needed only for preparation:

```sh
.wraith/ingestion-venv/bin/python examples/verified-ingestion/fetch_fixtures.py --output .wraith/repeat-fixtures/qdrant
.wraith/ingestion-venv/bin/python examples/verified-ingestion/fetch_fixtures.py --corpus --release 3.13.0 --output .wraith/repeat-fixtures/3.13.0
.wraith/ingestion-venv/bin/python examples/verified-ingestion/fetch_fixtures.py --corpus --release 3.13.1 --output .wraith/repeat-fixtures/3.13.1
.wraith/ingestion-venv/bin/python examples/verified-ingestion/fetch_fixtures.py --corpus --release 3.13.2 --output .wraith/repeat-fixtures/3.13.2
cargo build --release --locked

.wraith/ingestion-venv/bin/python examples/verified-ingestion/repeat_workflow.py \
  --qdrant-binary .wraith/repeat-fixtures/qdrant/qdrant --wraith target/release/wraith \
  --release0 .wraith/repeat-fixtures/3.13.0/documents \
  --release1 .wraith/repeat-fixtures/3.13.1/documents \
  --release2 .wraith/repeat-fixtures/3.13.2/documents \
  --output .wraith/repeated-ingestion/first
```

The runner supports the owned-server POSIX environment and performs no model calls.
It stops its server and retains data. Local qualification also ran the sequence with
small bundled fixtures; that fixture does not represent CPython release changes.
Routine CI uses the shorter [upstream compatibility check](upstream-ingestion.md)
and existing server controls. Reproduce this longer study separately when needed.

## Product decision

Keep the current ingestion safeguard and diagnostic integration available. Pause
further ingestion-feature and SaaS expansion: this comparison supports functional
utility, but does not establish lower operator effort or an advantage over a recipe
with the same guardrails. Large/untrusted exports and report usability were not
compared, so this result is not a verdict on every Wraith capability.

There is no new feature queue justified by these results. Maintain the existing
checks, preserve counterexamples when they occur, and choose future work from a
specific workflow requirement that this integration or the recipe fails to meet.
