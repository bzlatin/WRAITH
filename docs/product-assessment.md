# Product assessment: narrow the scope

**Recommendation: keep Wraith as a small local change-evidence tool, and pause
feature expansion and commercial-service work.** The engine works. The studies
have not shown that its extra setup and runtime deliver enough value over existing
tests, or that teams repeatedly want it.

The earlier validation strategy should change. More synthetic defects, replay runs
and custom research runners can validate implementation indefinitely without
answering whether Wraith improves someone's workflow.

## What the evidence says

The [weather comparison](weather-comparison.md) exercises a second framework and
user-facing requirements. Two real application feature implementations pass ten
frozen cases in both Wraith and equivalent Python integration tests. Both detect
the same two seeded faults. Wraith takes about seven seconds per base/candidate
comparison; the ordinary tests take about two seconds on the tested Mac. No useful
natural regression was caught. The shared requirements make equal detection an
expected result, not proof that all testing tools are interchangeable.

The [upstream PR study](upstream-study.md) selected ten actual PRs. Four usable merges
passed; six were stale. Several changes were outside the narrow suite. It provides
little evidence about preventing regressions in those changed features.

Earlier [historical](historical-pilot.md) and [maintained-agent](maintained-agent.md)
studies show that configured checks can expose important behavior, including a
partial fix revealing a latent crash. They remain source-guided or historical,
and ordinary tests can detect the same behavior when they express the requirement.
No study establishes human review savings, repeat adoption or willingness to pay.

The [public issue audit](public-issue-audit.md) reviewed fifteen requests and bugs
across PydanticAI, LangGraph and CrewAI. It found concrete debugging needs, including
post-evaluation trace access, but no repeated unmet workflow that justifies another
Wraith integration. Some needs already have native support; others require upstream
instrumentation fixes. Three interchange proposals share one origin, and one was
explicitly retracted. The audit supports keeping expansion paused. It is a selected
source review, not a measure of market demand.

## The competitive question

Agent testing is already served by ordinary test frameworks. PydanticAI recommends
standard Python testing with replacement models; its Evals package supplies cases,
datasets and evaluators. [Testing guidance](https://pydantic.dev/docs/ai/guides/testing/),
[Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/).

Promptfoo documents evaluation gates and reports in CI. LangSmith integrates
assertions and evaluation reporting with pytest, including a mode that disables
result syncing. [Promptfoo CI](https://www.promptfoo.dev/docs/integrations/ci-cd/),
[LangSmith pytest](https://docs.langchain.com/langsmith/pytest).

These capabilities make “tests for AI agents” a broad, weak differentiator. This is
an inference from their documented features, not a comparative benchmark or a claim
that their defaults match Wraith. We did not install or benchmark these products.

Wraith's more specific hypothesis is: **developers need a local, framework-neutral
way to preserve and review what changed, using existing application test helpers.**
Fixed baselines, observed activity, explicit inconclusive outcomes and portable HTML
are concrete capabilities. Their net workflow benefit remains a hypothesis.

## Decision and limits

- **Keep:** execution reliability, compatibility, documentation and the local CLI.
- **Narrow:** describe Wraith as a portable before/after evidence tool. Recommend
  existing tests when they already answer the review question.
- **Pause:** new evaluators, framework wrappers, speculative features, hosted
  dashboards, accounts, billing and additional automated “prove value” campaigns.
- **Resume product expansion:** only for a concrete workflow that repeatedly needs
  something its existing tests do not provide, with a recorded benefit and acceptable
  added setup, runtime and maintenance. A reviewed useful catch would strengthen
  that case; a feature count or another passing fixture would not.

Codex can automate execution, setup checks, artifact verification and bounded
experiments. An automation-only program cannot establish voluntary adoption or
whether someone will pay. While independent feedback is deferred, commercial
validation remains unavailable. There is no need to contact anyone or add telemetry.

This does not establish that Wraith is useless. It is enough evidence to reject
continued broad expansion on the assumption that more engineering will prove the
business. Keep the useful implementation, preserve the experiments, and hold the
next feature to a specific unmet workflow need.
