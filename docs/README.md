# Wraith documentation

Choose ingestion verification for index contents or agent regression checks for
reviewing behavior changes.

## Start here

- [Existing pipeline integration](upstream-ingestion.md): official LlamaIndex recipe, pre-write hook, shared setup costs and the utility-only decision.
- [Repeated update comparison](repeated-ingestion.md): frozen public-document sequence, equivalent guardrails, functional parity and the expansion pause.
- [Recovery and retention](ingestion-operations.md): read-only inspection of actual selection, saved verification and older index copies.
- [Qdrant server checks](ingestion-server-checks.md): concurrent readers, interrupted publishers, recovery, and measured rebuild/storage costs.
- [Verified document search](verified-ingestion.md): runnable LlamaIndex/Qdrant ingestion, checks before promotion, and an offline comparison with a simple script.
- [Verify ingestion](index-audit.md): experimental exact chunk/revision checks and a read-only Qdrant exporter; source build required.

- [Install](install.md): native binaries, supported platforms, and source builds.
- [Try the workflow](dogfooding.md): see a passing check and a deliberate regression.
- [Connect your agent](getting-started.md): Python/TypeScript functions, recorded activity, live budgets, and history.
- [Faster setup and case authoring](first-use.md): reviewed initialization, input-only functions, and typed CLI expectations.
- [Add PR checks](ci-setup.md): generate and review an offline GitHub workflow.
- [Upstream examples](../examples/external-agents/README.md): pinned PydanticAI and LangGraph orchestration.

## Reference

- [Configuration](configuration.md): agent commands, scenarios, expectations, and thresholds.
- [Structured output](structured-output.md): typed checks on JSON fields and arrays.
- [Sampling and exact traces](sampling.md): repeated observations and trace comparisons.
- [Statistical gates](statistical-gating.md): allowances, minimum samples, uncertainty, and CI decisions.
- [Subprocess protocol](protocol.md): connect other languages or custom adapters.

## Development

- [Ingestion product decision](index-product-decision.md): executed competitor comparison, scope, business hypothesis and limits.
- [REA fit assessment](rea-investigation.md): optional investigation use cases; no required integration.

- [Automated mock-agent trial](automated-trial.md): Codex-operated changes, test overlap, and a bounded evidence report.
- [Historical upstream pilot](historical-pilot.md): reproduce an authentic approval bug and compare it with existing tests.
- [Prospective application pilot](application-pilot.md): evaluate real LLM CLI changes against fixed contracts and existing tests.
- [Product assessment](product-assessment.md): decision to narrow the scope and pause expansion pending a concrete workflow benefit.
- [Public issue audit](public-issue-audit.md): fifteen issues across three agent projects, existing solutions, and the remaining trace-access lead.
- [Weather workflow comparison](weather-comparison.md): equivalent requirements in Wraith and ordinary tests, feature changes, calibration and measured runtime.
- [Frozen upstream PR study](upstream-study.md): ten chronologically selected PRs, four executed comparisons, six blocked merges, and the limits of a narrow suite.
- [Workflow integration and overhead](workflow-value.md): green-baseline feature evaluation, native CI comparisons, and bounded offline parallelism.
- [Maintained-agent fix study](maintained-agent.md): reproduce smolagents defects, compare local fixes with existing tests, and inspect a partial-fix interaction.
- [Support-agent feature queue](feature-queue.md): three independent changes, frozen application tests, recorded replay, and optional live comparison.
- [Capped live-agent evaluation](live-pilot.md): real tool selection and answer generation under one request budget.
- [Automated coverage challenge](coverage-challenge.md): measure scenario misses and rerun reviewed application contracts.
- [Contributing](../CONTRIBUTING.md): build, test, and documentation conventions.
- [Architecture](architecture.md): execution, evaluation, storage, and versioned contracts.
- [Repository CI and packaging](ci.md): baseline artifacts, native builds, and release archives.
- [Verification](verification.md): release evidence and its limits.
- [Commercial assessment](commercial-assessment.md): current market offers, a service hypothesis, and missing buyer evidence.
- [Product direction](product-direction.md) and [roadmap](roadmap.md): current priorities.
- [Report design](report-design.md) and [design tokens](../DESIGN.md): HTML evidence presentation.

The [original MVP](mvp.md) and [v0.2 implementation plan](implementation-plan.md)
are historical context, not setup instructions or pending work.
