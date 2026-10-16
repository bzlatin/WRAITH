# Roadmap

Priorities follow [product validation](product-direction.md), without a fixed release calendar.

## Available in v0.5

- Python/TypeScript function adapters, guided setup, and `doctor` diagnostics.
- Fixed baselines, checks, local HTML reports, immutable history, and reviewed case import.
- Text, structured JSON, tool, retrieval, resource, and optional exact-trace checks.
- Repeated samples and statistical gates with explicit inconclusive decisions.
- Opt-in live experiments with a shared budget for instrumented provider attempts.
- Native installation and generated offline GitHub PR checks.

See [verification](verification.md) for native release and controlled-fixture results.

## Current source improvements

The source build adds reviewed batch import and initialization, explicit input-only
functions, typed case-authoring flags, per-case expectation diagnostics, and report
context with comparison failures first. These are not in the published v0.5.0
binary. See [faster setup](first-use.md) and [coverage results](coverage-challenge.md).

The source also adds [native CI comparison and bounded offline jobs](workflow-value.md).
These reduce measured run time and custom workflow scripting; v0.5.0 does not
include them.

## Current decision

The [ingestion-verification decision](index-product-decision.md) authorizes one
focused improvement after comparing existing tools. The experimental
`wraith index check` command checks exact chunks/revisions and explicit tombstones
from sorted exports, with bounded reports and pending/unknown outcomes. An optional
Qdrant exporter and local demonstration are included. A runnable
[LlamaIndex document-search workflow](verified-ingestion.md) creates its manifest
before writes and verifies an isolated collection before promotion. This is not in v0.5.0.

The original [product assessment](product-assessment.md) and
[public issue audit](public-issue-audit.md) still do not establish demand for broad
agent-testing expansion. Previous automated research queues remain complete.

## Completed comparison and next decisions

The [existing-pipeline compatibility check](upstream-ingestion.md) is complete.
The public transformation hook works, but both checkers need the same setup and
neither demonstrated a maintenance advantage. Routine Linux CI now uses this
focused check instead of rerunning the full 28-attempt study on every push.

The [repeated-update comparison](repeated-ingestion.md) ran three pinned CPython
snapshots, duplicate/rename/removal changes and four deliberate controls. Both
verifiers made matching decisions across 14 steps each. The shared operational
wrapper handled recovery and retention, but no incremental Rust-checker benefit or
human-effort reduction was demonstrated on this workload.

1. Keep the existing integration and finite CI checks working. Preserve any actual
   counterexamples; no additional feature queue is justified by these results.
2. Pause ingestion-feature and commercial-platform expansion until a specific
   repeated workflow requirement exceeds the integration or equivalent recipe.
3. Native GitHub builds and tests now [pass on all three operating systems](verification.md#experimental-ingestion-source).
   Keep that validation before a future release; no new release is requested here.
4. Require authorized repeat-use evidence and a paid commitment before a hosted
   service. No customer outreach or release publication is part of this comparison.

Keep the core local and framework neutral. [REA](rea-investigation.md) is a potential
optional investigation tool; it is neither required nor integrated. Accounts, billing,
automatic repair and a multi-tenant control plane remain deferred.
