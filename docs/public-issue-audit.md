# Public issue audit

**Decision: keep Wraith available as a local utility and keep product expansion
paused.** Fifteen issue reviews show concrete evaluation and debugging problems,
but do not establish a repeated, unmet need for Wraith's before/after workflow.
The strongest remaining lead is access to per-case traces after an evaluation.
That is worth preserving as a lead; it does not yet justify another integration.

Reviewed on **2026-10-15**. This is public-source research, not user interviews,
adoption evidence or a measure of willingness to pay.

## Scope and method

Reviewed five issues each from PydanticAI, LangGraph and CrewAI, including their
available comments. All three repositories were public, unarchived and had recent
default-branch activity when checked. Searches used evaluation, testing, tracing,
reporting and comparison terms. Titles and search results were screened before the
fifteen detailed reviews; the list was not randomly sampled or preregistered.
Closed requests and supplied workarounds were retained.

For each issue, distinguish the reported problem, current response or alternative,
and what Wraith could actually do. Check linked fixes and official documentation
where relevant. An open issue does not prove that a defect remains reproducible;
a closed proposal does not prove that a feature shipped. No upstream applications
or third-party fixes were executed in this audit.

Three interchange proposals have the same reporting account. Two CrewAI report
bugs also share one reporting account. They are not five independent demand
signals. Public accounts cannot establish independent people or organizations.
Bot replies, offers to implement a fix and promotional comments are not adoption.

The tables below are the complete fifteen-issue review set. Statuses are snapshots
on the review date. Summaries omit personal identities, local paths and raw logs.

## PydanticAI

| Issue | Problem and response | Implication for Wraith |
| --- | --- | --- |
| [#4758: retain per-case traces](https://github.com/pydantic/pydantic-ai/issues/4758), open | Wants `SpanTree` available after evaluation. Uses an evaluator to retain trees outside the report. A second account describes the same gap for a multi-tool RAG agent. | Strongest lead: concrete use and corroboration within one project. Current report source has trace IDs but no retained span-tree field. Wraith preserves its own observed activity, not arbitrary Pydantic span trees. |
| [#2053: repeated evaluations](https://github.com/pydantic/pydantic-ai/issues/2053), closed | Manually grouping repeated runs was cumbersome. Basic multi-run support shipped in [#4253](https://github.com/pydantic/pydantic-ai/pull/4253). Current docs support repetition and grouped aggregates. | Genuine evaluation need with native support. This does not establish an unmet need for Wraith. Early stopping and per-case repeat counts are separate requests. |
| [#2904: long-running cases](https://github.com/pydantic/pydantic-ai/issues/2904), closed | Slow tasks/evaluators stalled evaluation. Reporter confirms that adding AnyIO timeout scopes solved it; cleanup errors came from their application's parallelism. | Wraith offers process deadlines, but the reported workflow already has a confirmed solution. This is not evidence that migration helps. |
| [#2209: rendering without Logfire installed](https://github.com/pydantic/pydantic-ai/issues/2209), open | Multiple accounts reported rendering/context errors. Installing the Logfire package was a confirmed workaround; a later comment disputed full resolution. Current package metadata still makes full Logfire optional. | Local reporting matters, but current reproduction is unverified. A Python library dependency does not imply a hosted account or upload requirement. Wraith would bypass, not fix, the SDK defect. |
| [#7710: EvalPort interchange](https://github.com/pydantic/pydantic-ai/issues/7710), open | The format's author proposes conversion from an external dataset vocabulary. Pydantic already serializes its own datasets as YAML/JSON. The reply is automated triage, not maintainer adoption. | Same origin as the LangGraph and CrewAI proposals below. A conversion request does not establish demand for Wraith's format or evaluation semantics. |

## LangGraph

| Issue | Problem and response | Implication for Wraith |
| --- | --- | --- |
| [#6214: granular tracing](https://github.com/langchain-ai/langgraph/issues/6214), open | Maintainer describes a customer who wants a PDF traced once at the root, then masked in child runs. A collaborator marks it high priority. | Concrete customer problem, but field-level capture control differs from local change comparison. Existing masking is relevant; whether it meets the proposed state-annotation ergonomics was not established. Wraith has no such policy. |
| [#5764: missing error events](https://github.com/langchain-ai/langgraph/issues/5764), open | Reporter observes missing error-bearing debug events in single-mode streaming. Multiple stream modes are a reported workaround. Linked fix [#8401](https://github.com/langchain-ai/langgraph/pull/8401) closed without merging. | Instrumentation correctness belongs upstream. Wraith can retain adapter/process failures, but cannot recover an event the framework omitted. Current reproduction was not tested. |
| [#8225: missing usage metadata](https://github.com/langchain-ai/langgraph/issues/8225), open | Streaming reportedly loses token counts. Disabling streaming is the reporter's workaround. A later contributor could not reproduce the loss with the reported versions and requested more details. | Report remains unconfirmed. Wraith's usage checks require observed usage; they cannot reconstruct missing counts. |
| [#7327: cross-checkpoint drift](https://github.com/langchain-ai/langgraph/issues/7327), closed | Author proposes hooks for their own drift monitor, then supplies a wrapper and post-run state-history approach. No maintainer commitment or demonstrated deployment appears in the thread. | Continuous state/memory monitoring is a different workflow from fixed before/after scenarios. The proposal alone does not warrant new Wraith metrics or replay features. |
| [#8472: OpenEval interchange](https://github.com/langchain-ai/langgraph/issues/8472), closed | Same author as the other interchange proposals explicitly retracts this request as overly broad outreach and identifies LangSmith as the relevant evaluation layer. | Counterevidence to treating cross-posted proposals as repeated independent demand. Do not build a LangGraph interchange integration from this request. |

## CrewAI

| Issue | Problem and response | Implication for Wraith |
| --- | --- | --- |
| [#6711: OpenEval interchange](https://github.com/crewAIInc/crewAI/issues/6711), open | Same interchange author later reports shipping an external adapter. Another account offers to contribute; no maintainer adoption is established. The adapter's operation was not verified here. | Community conversion is already claimed available. This is one proposal origin across three repositories, not three customers requesting Wraith. |
| [#7728: headless evaluation](https://github.com/crewAIInc/crewAI/issues/7728), open | Requests an explicit `--no-open` flag for SSH/CI. Current source still opens report URLs except in daemon mode; it also supplies unattended verdict/brief output. | Small upstream CLI gap. Wraith does not open a browser automatically, but it does not replace CrewAI AMP's evaluation service or criteria. |
| [#7352: memory observability](https://github.com/crewAIInc/crewAI/issues/7352), open | Requests memory read/write visibility, events and snapshots. No corroborating comments. Current official docs and source already expose memory query, save and retrieval events. | Existing hooks address part of the request; snapshots and full coverage were not verified. Wraith needs instrumentation too and does not inspect framework memory automatically. |
| [#7997: skipped-task score attribution](https://github.com/crewAIInc/crewAI/issues/7997), open | Skipped conditional tasks reportedly crash or shift scores. Reporter supplies mocked-model tests and a fix; replacement [#7998](https://github.com/crewAIInc/crewAI/pull/7998) remains open. | Important report-correctness bug with a targeted upstream fix. Wraith cannot repair CrewAI's score attribution. No new Wraith catch occurred. |
| [#8024: evaluation table alignment](https://github.com/crewAIInc/crewAI/issues/8024), closed | Non-default iteration counts misalign report rows. [#8031](https://github.com/crewAIInc/crewAI/pull/8031) merged on October 12. Same reporter as #7997. | Resolved upstream report bug with an ordinary regression test. Two bugs from one account are not independent product demand. |

## Existing capabilities checked

- **Pydantic Evals:** [multi-run evaluation](https://pydantic.dev/docs/ai/evals/how-to/multi-run/)
  groups repeated observations; [serialization](https://pydantic.dev/docs/ai/evals/how-to/dataset-serialization/)
  saves datasets as YAML/JSON. [Trace integration](https://pydantic.dev/docs/ai/evals/how-to/logfire-integration/)
  exposes span trees during evaluation and supports OpenTelemetry backends. That
  does not resolve the requested post-run in-memory report access in #4758.
- **LangSmith:** [masking and per-function processors](https://docs.langchain.com/langsmith/mask-inputs-outputs)
  control logged data. [pytest integration](https://docs.langchain.com/langsmith/pytest)
  supports assertions and a mode that disables result syncing. These capabilities
  do not establish that the specific state-field annotation request is solved.
- **CrewAI:** [event listeners](https://docs.crewai.com/v1.15.28/en/concepts/event-listener)
  include memory events. Its [testing command](https://docs.crewai.com/v1.15.28/en/concepts/testing)
  already performs repeated crew evaluation. Their existence does not guarantee
  coverage of every memory path or correctness of every report.
- **Promptfoo:** [CI documentation](https://www.promptfoo.dev/docs/integrations/ci-cd/)
  describes gates and JSON, HTML and JUnit reports. Portable reports and CI gates
  alone are not unique to Wraith. This was a documentation check, not a benchmark.

Pinned source checks used PydanticAI
[`be2ed8f`](https://github.com/pydantic/pydantic-ai/tree/be2ed8fbafaf66242cc87d752121396f5fa0fe22)
and CrewAI
[`3da2d4e`](https://github.com/crewAIInc/crewAI/tree/3da2d4e9932b5f2fa9aa73ea9245e0f8b5c154f8):
Pydantic report fields, dataset execution and package dependencies; CrewAI CLI
evaluation entrypoints and memory event types. Official docs can change after this
review. Upstream installation, fixes, provider calls and production behavior were
not tested.

## What this changes

Debugging agent activity is a recurring topic. The specific requests differ:
retain existing spans, suppress selected fields, emit missing events, preserve
usage, and observe memory. Treating all of them as demand for a new regression
runner would erase the problem boundaries. None of these threads demonstrates
repeat use of Wraith or a preference for its setup and reports over current tools.

The most relevant unresolved lead is #4758. Two accounts describe the same
post-evaluation trace-access gap within one framework. A small upstream report
change or local OpenTelemetry handling may serve it better than adding a second
runner. No repeated cross-project request for the same Wraith-shaped workflow was
established in this review. This is a judgment about this selected set, not an
estimate of market demand or proof that no such workflow exists.

**No prototype or new automated campaign follows from this audit.** Keep the
existing implementation and evidence. Resume expansion only when a concrete
workflow needs portable change evidence repeatedly and a small integration can
show a benefit over its existing tests or trace tools. Measure added setup,
maintenance and review effort as well as runtime; record human effort only when
it is actually observed. Until then, maintain the CLI and leave commercial-service
work paused. Public issue research cannot establish paid demand.

No outreach, telemetry, provider calls or new recurring automation was used.
This audit completes the bounded research step; it does not create another queue
that must run before a product decision can be made.
