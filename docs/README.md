# Wraith documentation

Start with the demo, connect a few representative tasks from your agent, and use
the same suite when reviewing changes.

## Start here

- [Install](install.md): native binaries, supported platforms, and source builds.
- [Try the workflow](dogfooding.md): see a passing check and a deliberate regression.
- [Connect your agent](getting-started.md): Python/TypeScript functions, recorded activity, live budgets, and history.
- [Add PR checks](ci-setup.md): generate and review an offline GitHub workflow.
- [Upstream examples](../examples/external-agents/README.md): pinned PydanticAI and LangGraph orchestration.

## Reference

- [Configuration](configuration.md): agent commands, scenarios, expectations, and thresholds.
- [Structured output](structured-output.md): typed checks on JSON fields and arrays.
- [Sampling and exact traces](sampling.md): repeated observations and trace comparisons.
- [Statistical gates](statistical-gating.md): allowances, minimum samples, uncertainty, and CI decisions.
- [Subprocess protocol](protocol.md): connect other languages or custom adapters.

## Development

- [Contributing](../CONTRIBUTING.md): build, test, and documentation conventions.
- [Architecture](architecture.md): execution, evaluation, storage, and versioned contracts.
- [Repository CI and packaging](ci.md): baseline artifacts, native builds, and release archives.
- [Verification](verification.md): release evidence and its limits.
- [Product direction](product-direction.md) and [roadmap](roadmap.md): current priorities.
- [Report design](report-design.md) and [design tokens](../DESIGN.md): HTML evidence presentation.

The [original MVP](mvp.md) and [v0.2 implementation plan](implementation-plan.md)
are historical context, not setup instructions or pending work.
