# Product decision: verify ingestion before promotion

Research and local implementation reviewed October 15, 2026.

**Build a small ingestion-verification capability inside Wraith. Treat it as an
experimental product direction, with enterprise and SaaS expansion conditional on
repeat use.** The first user is an engineer who owns a self-managed RAG pipeline
and needs to know whether a completed job actually wrote the intended searchable
chunks. The initial integration is an ingestion-job gate over a frozen generation.

## Why change direction

Earlier Wraith studies demonstrated execution and configured regression detection.
The [weather comparison](weather-comparison.md) found the same controlled faults
with ordinary tests, with higher Wraith runtime. The [upstream study](upstream-study.md)
had four usable PR merges out of ten and limited changed-behavior coverage. The
[historical](historical-pilot.md), [maintained-agent](maintained-agent.md), and
[public issue](public-issue-audit.md) work did not establish repeat adoption or paid
demand. Those results remain intact; this direction does not retroactively validate
the original business.

Ingestion verification has an explicit requirement that comes from the application:
which chunks of which revision should exist. It needs no model judge or manually
written question suite. A manifest is still integration work. Teams without that
metadata may find an existing managed ingestion service more useful.

Cribl's lesson is to solve an expensive operational problem with a clear owner.
Its own account describes starting with telemetry routing and shaping to address
cost and control. It also already offers LLM telemetry routing; a generic
“Cribl for AI” pitch does not identify an unserved market.
[Company background](https://cribl.io/about-us/),
[LLM routing](https://docs.cribl.io/llm-observability/llm-use-case-route-destinations/).
Cribl's valuation and company-reported revenue are not evidence for Wraith demand.

## Evidence and alternatives

Public reports describe concrete consistency failures:

- [Dify #40457](https://github.com/langgenius/dify/issues/40457) reports vector deletion
  using the wrong identifier space while cleanup appears successful. Remaining
  vectors do not necessarily reach users: the report describes additional filtering.
- [LlamaIndex #23002](https://github.com/run-llama/llama_index/issues/23002) reports
  document identity loss when two documents share a content hash. Exact identities
  matter even when text matches.
- [LlamaIndex #22733](https://github.com/run-llama/llama_index/issues/22733) discusses
  the failure window in delete-before-insert replacement. Monitoring detects an
  incomplete result; it does not make replacement atomic.

These reports guided requirements. We did not reproduce these upstream bugs in this
implementation, and they are not independent customer interviews.

The market already includes [RAGproof](https://ragproof.io/),
[raghealth](https://pypi.org/project/raghealth/0.5.5/),
[ragfresh](https://pypi.org/project/ragfresh/), and managed sync from
[LlamaCloud](https://developers.llamaindex.ai/llamaparse/connectors/) and
[Paragon](https://www.useparagon.com/product/managed-sync). raghealth also advertises
scheduling, dashboards and alerts. Scheduling alone is not an uncovered opportunity.
Broader agent evaluation is served by [MLflow](https://mlflow.org/docs/latest/genai/datasets/)
and [LangSmith](https://docs.langchain.com/langsmith/evaluation-types);
[MCPJam](https://www.mcpjam.com/features) overlaps MCP compatibility checks.

## Executed comparison

We downloaded and hash-verified PyPI wheels for raghealth 0.5.5 and ragfresh 0.1.0,
reviewed their implementations, and executed their unchanged library functions with
controlled source/store objects. Both were the latest PyPI versions at inspection.
No vendor server, production deployment, or end-to-end CLI was benchmarked.

| Same document at the same revision | raghealth coverage check | ragfresh check | Exact chunk-set comparison |
| --- | --- | --- | --- |
| All 3 expected chunks | Covered | Unchanged | Equal |
| Only 2 of 3 expected chunks | Covered; no findings | Unchanged | Missing ID |
| 3 chunks, but one wrong ID | Covered; no findings | Unchanged | Missing and unexpected IDs |
| No chunks | Coverage finding | Not yet indexed | Missing IDs |

raghealth was called with embedding comparison disabled; the question here is exact
coverage, not semantic duplication. Its source metadata included the expected chunk
IDs, which its coverage check does not consume. ragfresh's API has no chunk-manifest
parameter. Its documented semantics count a document as indexed when any chunk is
present. Both checks behave as designed. No claim is made that their other features
or all competing tools share this limitation.

Reproduce the comparison in a separate environment with those pinned packages:
`python examples/index-audit/compare_tools.py`.
[Recorded outputs](../examples/index-audit/comparison-results.json).
Wheel SHA-256 values:

- raghealth: `612431437dcaee1f9d25f65e48dc5054f85961df472976f471239b4b6e99ddbb`
- ragfresh: `26b1f0810d26f13734a434ce810f43e71f8389662ceb81dc1d99007d86446ca9`

**The simple set comparison catches the same defect.** SQL joins can do so too.
There is no algorithmic moat. The engineering hypothesis is that strict export
contracts, bounded scans, uncertainty handling and useful job-level evidence reduce
repeated operational work. This has not been measured with users. Extending an
existing tool remains a reasonable alternative if this packaging adds no benefit.

## What is implemented

`wraith index check` streams versioned manifests and inventories, compares exact
chunk IDs and revisions within each tenant/document, handles explicit tombstones,
and emits JSON/HTML with the responsible job and suggested next action. Incomplete
exports, concurrent updates, normal ingestion lag and missing metadata cannot pass.
The Qdrant exporter reads payload metadata, bounds pagination, spools sorting to
local disk, and never modifies the collection. [Usage and contracts](index-audit.md).

A local Qdrant client demonstration deliberately leaves one chunk unwritten and
one deletion unapplied. Wraith reports both, and both clear after repair. The
before and after index each contain three points: a total-count check would miss
the difference. This is controlled engineering validation, not a natural discovery.
No model requests, private application access, or customer outreach were used.

## Workflow integration follow-up

The [LlamaIndex/Qdrant search example](verified-ingestion.md) now creates its own
pre-write manifest, builds a separate candidate collection, and promotes only a
verified generation. Two imports of this repository's then-current 35 documentation
files / 235 chunks passed, as did nine integration tests covering normal changes
and deliberate failures. Both Wraith and the plain script caught the controlled
partial write. No naturally occurring ingestion defect was discovered.

This removes manual manifest authoring for this one integration and avoids changing
the selected collection during a build. It does not remove the need for a stable
source snapshot. Local Qdrant allows only one process; distributed publishers,
concurrent readers and server crash recovery were initially untested. The subsequent
[owned-server checks](ingestion-server-checks.md) exercised HTTP readers, publisher
interruptions and a standalone restart over 200 public documents / 4,725 chunks.
They preserve that scope: distributed publication is still untested. Each import
still rebuilds and retains a complete collection. The example is useful for local document
search, but has not demonstrated lower operator effort or independent adoption.
[Measured results and limitations](verified-ingestion.md#comparison-and-automated-checks).

## Local verification

On macOS Apple Silicon, Rust 1.87 builds and all 66 Rust tests passed; current
stable Clippy passed with warnings denied. All 72 Python tooling tests passed.
The existing deterministic RAG pilot still detects its 13 configured fault cases
across seven comparisons, with no unexpected failures in its 71 negative cases.
These counts describe controlled checks, not a production false-positive estimate.
The HTML report was inspected in a browser and report escaping/immutability are
covered by integration tests. The modified-source secret scan found no leaks.
Subsequent [native GitHub validation](verification.md#experimental-ingestion-source)
passed on Linux, macOS and Windows. Optional SDK and owned-server controls passed
on Linux using the small bundled corpus; they were not run on Windows by CI.

A generated, complete export with 100,000 documents / 300,000 chunks (29.8 MB)
was checked in 0.184 seconds with about 4.2 MiB peak child RSS in one local release
run. A 10,000-document run took 0.239 seconds. Startup/cache effects were not
controlled; do not use these timings as a comparative speed claim. Measurements
exclude Qdrant, export generation/sorting, network and concurrent writers. They
support a bounded-memory implementation check, not enterprise-scale readiness.
[Recorded measurements](../examples/index-audit/scale-results.json).

## Business and scale decision

Potential buyer: a platform or search team running its own ingestion stack. The
recurring trigger is an ingestion completion, deletion, source revision, or index
migration. The proposed paid value is keeping that verification working across
jobs and helping operators resolve discrepancies. A hosted control plane with
customer-run collectors is one possible later delivery model. Pricing, acquisition,
support costs, gross margin and willingness to pay are all untested.

A streaming engine and disk-spooled export provide a practical foundation for large
inventories. They do not solve cross-store snapshots, multi-region consistency,
access control, continuous-change watermarks, or enterprise operations. In particular,
the current exporter requires a freeze/immutable generation to return reliable
results. Avoid selling it as a continuous production monitor yet.

Next decisions:

The subsequent [upstream recipe integration](upstream-ingestion.md) is complete:
four ordinary transitions passed both checkers through the public transformation
hook. Shared setup costs remain. Retain the local utility and the expansion pause.

1. Keep the implemented workflow available. The [completed repeated-update comparison](repeated-ingestion.md)
   found matching decisions over 14 steps per lane with the same operational wrapper.
   Pause expansion; no incremental checker benefit or lower operator effort was
   demonstrated on that workload.
2. If full rebuilds or source snapshots are too burdensome, stop or improve that
   one integration. Do not add unrelated connectors, another validation framework,
   or automated repair to compensate for missing adoption.
3. Before investing in accounts, billing or an enterprise service, obtain authorized
   repeat-use trials and a paid commitment. Automated tests cannot substitute for
   this commercial evidence. No outreach is authorized by this document.

[REA](rea-investigation.md) may help investigate packaged connectors and runtime
failures. It is optional diagnostic tooling, not part of the ingestion gate.
