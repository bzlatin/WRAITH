# Product direction

Wraith's current focus is verifying document ingestion for AI search: show whether
a job stored the intended chunks, gate a candidate index, and make the resulting
state inspectable. Existing agent regression workflows remain supported.

## Current decision

The [repeated ingestion comparison](repeated-ingestion.md) is complete: both checkers
handled the 14-step workload with matching decisions under the same operational
wrapper. Keep the integration available; pause additional ingestion features and
commercial expansion until an observed workflow requirement justifies them. The
shared guardrails are useful, but this study did not establish an incremental
Rust-engine benefit, lower operator effort or paid demand.

The [upstream recipe integration](upstream-ingestion.md) used LlamaIndex's public
transformation hook without replacing its pipeline. Both checkers passed four
normal transitions and needed the same capture/export configuration. The hook
requires an uncached full rebuild without a document store. Keep this capability
as an optional open-source utility; no further feature or SaaS queue is justified.

The [earlier product assessment](product-assessment.md) paused broad agent-testing
expansion after studies failed to show enough benefit over ordinary tests. That
assessment remains valid for the original workflow.

The current bounded improvement is [ingestion verification](index-product-decision.md):
check whether a completed job wrote the exact intended chunk IDs and revisions.
An executed comparison identified a partial-chunk coverage limitation in two existing
tools. A simple reconciliation script also solves it, so the product hypothesis is
reliable integration and actionable evidence, not a unique algorithm.

The [experimental source command](index-audit.md) implements that check. Maintain
existing agent workflows; defer broad expansion and a commercial platform until
repeat use demonstrates enough value over scripts and existing products.

## Validation goals

For ingestion, integrate an authoritative manifest and consistent export into a real
job, then measure actionable discrepancies and repeated operation against a plain
reconciliation script. Keep intentional failures separate from natural discoveries.

For the original agent workflow, catch a useful, naturally occurring regression in an independently useful agent,
then see developers run Wraith again during changes and on pull requests. Offline
fixtures and injected faults validate the engine; they do not establish this goal.

Start with a small suite of real tasks. Record useful catches, missed failures,
false alarms, setup time, and whether the report helped diagnose the problem.
Collect voluntary feedback rather than uploading agent data or adding telemetry.

## Priorities

- Reduce install, configuration, baseline, and comparison friction.
- Show the scenario, expectation, baseline, candidate, and regression classification.
- Keep baselines fixed and preserve the decision and evidence from every completed check.
- Distinguish output differences, failed contracts, missing instrumentation, and uncertainty.
- Ship through GitHub source, native binaries, readable documentation, and PR checks.

Choose additional evaluators, adapter hooks, replay, and statistical methods from
observed gaps. Hosted accounts, billing, dashboards, and shared storage should follow
repeated team needs. Feature counts, downloads, and stars do not demonstrate that
Wraith improves an agent workflow.

See [roadmap](roadmap.md) for current capabilities and the next work.
