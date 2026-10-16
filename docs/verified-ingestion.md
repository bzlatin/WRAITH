# Verify an index before publishing it

**Experimental source example. Requires Python 3.10+ and a source-built Wraith.**

Import a folder of Markdown or text files, search it locally, and rebuild it as files
change. The example uses LlamaIndex's ingestion pipeline and Qdrant's persistent
local backend. Wraith checks the candidate collection before the serving alias moves.
A failed or inconclusive check leaves the previous collection selected.

## Try it

From the repository root, with Rust 1.87+:

```sh
cargo build --locked
python3 -m venv .wraith/ingestion-venv
.wraith/ingestion-venv/bin/python -m pip install -r examples/verified-ingestion/requirements.txt

.wraith/ingestion-venv/bin/python examples/verified-ingestion/search.py \
  --db .wraith/document-search ingest \
  --source examples/verified-ingestion/documents \
  --output .wraith/ingestion/first --wraith target/debug/wraith --compare-plain

.wraith/ingestion-venv/bin/python examples/verified-ingestion/search.py \
  --db .wraith/document-search query 'refund payment'
```

On Windows use `Scripts/python.exe` inside the virtual environment and
`target/debug/wraith.exe`. Installing dependencies needs network access; ingestion
and search use no network, model API, credentials or downloaded model weights.
The 256-dimensional token-hash embeddings support basic lexical search. They are
not a semantic embedding model or evidence of retrieval quality.

Open `.wraith/ingestion/first/report.html`. To index your own files, replace
`--source` with a dedicated directory, such as this repository's `docs`. After
changes, repeat `ingest` with a **new** output directory. Use the same `--db` and
`--alias` (default `documents`) to replace the selected generation. Do not edit the
source directory during ingestion's initial read; an immutable checkout is preferable.

## What happens

1. Read UTF-8 `.md` and `.txt` files once. Relative filenames identify documents;
   SHA-256 hashes identify their captured revisions. Reject symlinks and invalid text.
2. Run LlamaIndex's `SentenceSplitter`, retaining separate identities for files with
   identical content. Save expected node IDs before any vector-store write.
3. Create a new collection and run the embedding/write stage against those same
   prepared nodes. Caching and document deduplication are disabled for this full rebuild.
4. Export the completed, exclusively owned candidate collection. Run Wraith, saving
   JSON, HTML and the decision. Only exit 0 permits promotion.
5. Switch the alias and save a promotion receipt. Retain previous and failed collections.

The integration splits [LlamaIndex's ingestion pipeline](https://developers.llamaindex.ai/python/framework-api-reference/ingestion/)
at the write boundary. It follows Qdrant's documented
[collection alias pattern](https://qdrant.tech/documentation/manage-data/collections/#collection-aliases).
This is established database practice; Wraith adds the verification gate.
The manifest validates storage against the parser's intended output. It cannot detect
content the parser itself silently omitted or determine whether the source was up to date.

## Failure and recovery

Use [read-only inspection](ingestion-operations.md) to join actual selection with
saved build evidence and review older copies. New imports bind their job metadata
and export/report hashes; older evidence remains unbound and is kept.

`verification.json` contains the check's exit code, collection names, scan counts
and measured stage times. `promotion.json` exists only after the new alias is
confirmed. `error.json` describes an interrupted execution stage when Python can
record it; `check.log` contains Wraith diagnostics.

Inspect the actual alias after any interruption:

```sh
.wraith/ingestion-venv/bin/python examples/verified-ingestion/search.py \
  --db .wraith/document-search status
```

A process crash can occur after alias publication but before receipt creation;
absence of a receipt does not prove the alias stayed unchanged. Fix the cause and
start a new attempt. Existing evidence is never overwritten or automatically resumed.
The example does not automatically remove collections. Source removals stop appearing
in the newly selected collection, but retained generations still contain their text.
This is not physical erasure or a compliance deletion workflow.

## Comparison and automated checks

`--compare-plain` also runs [a small reconciliation script](../examples/verified-ingestion/reconcile.py)
against the identical exports. Both detect missing, extra and stale chunk tuples.
The script is for trusted example exports; it lacks Wraith's complete validation,
streaming bounds and diagnostic HTML. It can also be run alone:

```sh
python3 examples/verified-ingestion/reconcile.py \
  .wraith/ingestion/first/manifest.jsonl .wraith/ingestion/first/inventory.jsonl

.wraith/ingestion-venv/bin/python examples/verified-ingestion/tests/test_workflow.py \
  --wraith target/debug/wraith -v
```

Fourteen workflow tests use the actual libraries and local database. They cover
repeat builds, revisions, removals, duplicate-content identities, an acknowledged
partial write, failed writes, missing metadata, empty inputs, verification timeout,
alias-name conflicts, exclusive database ownership, and the upstream manifest hook's
cache, identity and evidence-preservation boundaries. Controlled faults are injected
at the library boundary; they are not newly discovered LlamaIndex or Qdrant defects.
The tests prohibit socket connections during in-process ingestion and search.
On Python 3.13, Qdrant 1.19.1 emits a resource warning for its temporary SQLite
thread-safety probe; tracing localized it to the installed dependency. Tests still
pass, and the application closes its persistent client. This warning is not counted
as an ingestion defect caught by Wraith.

Two local imports of Wraith's then-current 35 documentation files wrote 235 chunks
per generation and passed both checks. Search included the statistical-gating guide among its three results
for a query about minimum samples and inconclusive comparisons. Wraith's subprocess
check plus JSON/HTML took 28–53 ms; the in-process reconciliation took 0.8–0.9 ms.
Export took 11–13 ms and three client reads per generation. These are single-machine
observations with different output work, excluding Python import time; not a fair
algorithm benchmark or proof of human time saved. [Recorded results](../examples/verified-ingestion/results.json).

## Scope and remaining work

The local database allows one process at a time. Tests query the previous collection
through that same process during a failed build; this is **not** a demonstrated
concurrent-reader or zero-downtime service. A separate
[owned-server runner](ingestion-server-checks.md) now tests concurrent HTTP readers,
interrupted publishers and a standalone server restart. Distributed publisher
coordination remains untested. The example's alias recheck is not compare-and-swap protection.

Each import rebuilds the whole corpus and retains another collection. Limits are
1,000 files, 8 MiB per file and 32 MiB total; memory holds the parsed corpus. Wraith's
streaming comparator does not make the ingestion pipeline itself streaming.
A continuously changing source needs snapshot/watermark support beyond this example.
Stored database text, manifests and reports may contain application data; keep them private.

The [server check](ingestion-server-checks.md) records a 200-document / 4,725-chunk
run, including storage growth and recovery limits. The [recovery inspector](ingestion-operations.md)
now provides that view and a conservative retention plan. Compare it with the plain
recipe. The [completed repeated-update comparison](repeated-ingestion.md) found
functional parity and supports pausing further expansion.
Do not expand into hosted billing or monitoring until repeated use justifies the overhead.
