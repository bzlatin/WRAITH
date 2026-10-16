# Integrate an existing ingestion recipe

The official LlamaIndex Qdrant recipe works with a pre-write manifest added through
its public transformation hook. Wraith and plain reconciliation both passed four
normal transitions. **No integration or maintenance advantage was demonstrated.**
Keep Wraith as an optional local utility; pause ingestion features and SaaS work.

## What ran

The runner pins the upstream [Connecting to Vector Databases example](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/docs/src/content/docs/framework/module_guides/loading/ingestion_pipeline/index.md).
Preparation verifies source and MIT license checksums. Execution uses only the
recipe's pipeline constructor, with deterministic replacements for title extraction,
embeddings and tokenization. It runs the real LlamaIndex pipeline and Qdrant local
backend with sockets blocked. It does not execute the cloud example end to end.

Initial import, unchanged repeat, source revision and rename each stored two
documents / nine chunks and passed both checkers. A witness at the SDK write method
confirmed that source identities were present in the saved manifest before writes.
The same exported files went to Wraith and the trusted-input script. There were no
injected storage faults or natural defect discoveries in this check.
[Recorded results](../examples/verified-ingestion/upstream-results.json).

Two incomplete qualification attempts are retained locally. They exposed mistakes
in the new runner's client cleanup and write-method witness, not upstream ingestion
defects or Wraith catches. The third attempt completed.

## Integration cost

Both checkers require the same source identities/revisions, candidate isolation,
pre-write capture, consistent export, evidence paths and owner of publication.
Wraith additionally needs its native executable; the script needs Python. The
manifest hook and Qdrant export still need Python and the application SDKs in both
cases. Wraith supplies bounded validation and HTML; the reference supports trusted
exports and emits JSON. Those differences were not measured as a usability benefit.

For a synchronous, single-worker full rebuild using the existing dependencies:

```python
# Make adapters/index importable from this source checkout.
from llamaindex_manifest import ManifestCapture, attach_capture

pipeline.disable_cache = True
attach_capture(pipeline, ManifestCapture(
    destination="new-job/manifest.jsonl", scope="support", generation="job-42",
    tenant="team-a", revisions=source_revisions,
))
pipeline.run(documents=documents)
# After successful writes and the visibility barrier, export the isolated
# collection and run either checker. Continue publication only on exit 0.
```

`source_revisions` maps each authoritative `Document.id_` to its source version,
captured from the intended source snapshot. Never build it from indexed output.
Append the capture after all node-changing transformations. The hook adds identity
payloads and closes its new manifest before the vector store receives nodes.
Existing evidence, unknown documents and duplicate chunk IDs stop before writes.
It does not manage publication or recovery; use the [complete example](verified-ingestion.md)
when those are needed.

The helper rejects caching and attached document stores, which can skip nodes or
the side-effecting capture. Keep this example synchronous and single-worker; it is
not an incremental, asynchronous or parallel-ingestion adapter. Disabling caching
may be unacceptable in a live model-backed pipeline. Neither checker removes that
cost. Intended parser output also cannot prove that parsing captured all source text.

## Reproduce

Use the [optional dependency setup](verified-ingestion.md). Network access is needed
only to prepare the pinned public recipe and license:

```sh
python3 examples/verified-ingestion/upstream_check.py --prepare .wraith/upstream-source
.wraith/ingestion-venv/bin/python examples/verified-ingestion/upstream_check.py \
  --upstream .wraith/upstream-source --wraith target/debug/wraith \
  --output .wraith/upstream-run
```

Use new paths for another attempt. The runner freezes its protocol before execution
and preserves incomplete results. It makes no model calls. Routine Linux CI runs
this focused compatibility check; the longer [repeated-update comparison](repeated-ingestion.md)
remains a separate, manually invoked reproduction.

## Decision

The integration is feasible, but neither this recipe nor the repeated-update study
shows a reason to build a commercial service. No human setup time, maintenance
effort, preference or willingness to pay was measured. Avoid another synthetic
feature queue. Reopen product expansion only for a concrete workflow requirement
that the current utility or a simple recipe cannot handle economically.
