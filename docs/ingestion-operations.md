# Recover ingestion state and review old indexes

**Experimental source integration.** This command belongs to the optional Python
LlamaIndex/Qdrant example; it is not in the published v0.5.0 binary.

Wraith's index check compares the document pieces an ingestion job intended to write
with the pieces actually stored. The example publishes a new index only after that
check passes. Its new `inspect` command answers a different question: what is selected
now, and how does that selection relate to saved build evidence?

## Use it

After following the [document-search setup](verified-ingestion.md), run:

```sh
.wraith/ingestion-venv/bin/python examples/verified-ingestion/search.py \
  --db .wraith/document-search inspect --history .wraith/ingestion \
  --json .wraith/ingestion-inspection.json
```

`--history` is the parent directory containing job directories such as `first`,
`second` and `third`. The JSON output path must be new and its parent must exist.
Use `--output json` for structured stdout. The command reads the local database;
it does not delete collections, create receipts or rerun ingestion.

The first line explains whether the selected index has matching build evidence and
a receipt. A missing receipt can occur when ingestion switches the serving alias
and then crashes. If the actual selection matches intact passing evidence, inspection
reports that state so an operator can investigate without blindly rebuilding it.

The collection list shows point counts, evidence status and reasons to keep copies.
`--keep-previous 2` retains the two newest recorded prior publications for rollback;
the default is one. Zero is rejected. Older copies can be marked **review older copy**.
That is a review list, never permission to delete.

Every alias protects its referenced collection, including aliases outside the inspected
workflow. Unfinished jobs protect their recorded previous collection. Unpublished,
failed, unknown and legacy collections are kept. Invalid evidence or a change in
collection/alias observations prevents any retirement recommendations. Timestamp ties
are retained together. Point counts do not establish byte savings or billable costs.

Exit 0 means the inspection completed with matching evidence for the selected index.
Exit 3 means that state could not be established; exit 2 is a command/setup error.
**Inspection does not audit current live contents.** Run `wraith index check` with
consistent exports when you need to check whether data still matches the manifest.

## Evidence and compatibility

New imports save an immutable `job.json` before writes and SHA-256 digests of that
record, the manifest, inventory and JSON report inside `verification.json`. Inspection
checks these files, their separate schema-1 contracts and their identities together.
Hashes detect accidental changes; they are not signatures or protection against an
actor rewriting the files and hashes together.

Older imports lack this binding. They remain readable as unbound history and are kept,
but cannot establish a verified recovery state. Original evidence is never rewritten
or retroactively certified. These optional integration records are separate from the
native engine's agent-run and index-report schemas.

The local backend holds its ordinary exclusive process lock during inspection.
The server runner inspects only its owned localhost database. Repeated alias/list
reads detect some concurrent changes, but do not establish an atomic snapshot or
coordinate multiple publishers. A retention plan becomes stale as the workflow changes.

## What the automated evidence shows

The [server runner](ingestion-server-checks.md) now exercises recovery and retention
alongside actual ingestion, concurrent queries and process interruption. It checks:

- The selected generation is correctly identified after a publisher dies before saving its receipt.
- The oldest recorded publication is listed for review while the selected index,
  rollback copy, failed candidate and unfinished jobs are kept.
- Adding another alias protects that older collection too.
- Inspecting leaves actual point metadata and aliases unchanged.
- Changing a report in a copied history makes the inspection inconclusive and keeps every collection.

The larger run uses 200 pinned public CPython documents / 4,725 chunks. These are
deliberate controls, not naturally discovered incidents. [Recorded results](../examples/verified-ingestion/operations-results.json)
include timings and exact outcomes. The original server and local results remain intact.

A [small independent recipe](../examples/verified-ingestion/reconcile_operations.py)
answers the same normal recovery and retention questions using trusted job files.
It does not detect the altered report because it trusts recorded exit codes. Adding
the same validation to that script is possible. The comparison demonstrates the
packaged checks, not an exclusive algorithm or a measured reduction in human effort.

This is evidence of technical utility: one command reconstructs actionable state
from a real database and its job artifacts without modifying either. It does not
establish independent adoption, production reliability, customer ROI or paid demand.

## Next decision

The [repeated-update comparison](repeated-ingestion.md) now exercises these cases
with the same wrapper in both lanes. Decisions matched across 14 steps per lane;
no incremental checker benefit or human-effort saving was established. Keep this
integration available and pause expansion until an observed requirement justifies it.
Automatic deletion, repair, more connectors and a hosted service remain deferred.
