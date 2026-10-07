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

## Validation
Offline demos, controlled RAG mutations, and pinned upstream agent orchestration
validate engineering behavior. Natural regression discovery and repeat use remain
the product validation goals. See [verification](docs/verification.md).

## Product Principles
- Minimize setup and explain problems with concrete fixes.
- Show failures first, with expected and observed evidence.
- Preserve versioned contracts and honest uncertainty.
- Keep provider logic outside the framework-neutral core.

## Report Brief
Compact, self-contained HTML generated from saved evaluation results, with failures
first and expandable output details.
