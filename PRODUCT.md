# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

This record describes the local HTML report; the primary product is a native CLI.

## Users
Developers changing AI agents and reviewing merge requests.

## Product Purpose
Catch configured behavioral regressions by running the same scenarios before and
after a change, then explain the evidence clearly enough to act on it.

## Operating Context
Local development and CI. Developers install Wraith, connect an agent, save a
baseline, edit code, and check the change. Reports are standalone local HTML.

## Capabilities and Constraints
Rust owns evaluation and comparison. Thin Python/TypeScript adapters run user code.
Artifacts stay local by default. Live model calls need explicit budgets and adapter
instrumentation. Statistical uncertainty is distinct from a passing gate.

## Evidence on Hand
Offline demos, RAG controlled mutations, and the Example application integration. Four
live baseline/candidate cases passed in initial experiments. Naturally occurring
regression catches and repeat adoption remain unproven.

## Product Principles
- Minimize setup and explain problems with concrete fixes.
- Show failures first, with expected and observed evidence.
- Preserve versioned contracts and honest uncertainty.
- Keep provider logic outside the framework-neutral core.

## Report Brief
The owner approved a compact, self-contained HTML report generated directly from
real evaluation results, with failures first and expandable output details.
