# Product direction

The owner's October 2026 feedback establishes the priority: make Wraith useful in
actual agent development before expanding the product. The implementation already
provides a local CLI, saved comparisons, packaging, and CI workflows. Those are
engineering capabilities; real-agent usefulness and repeat adoption remain unproven.

## First product milestone

Use Wraith against a real AI agent and catch a regression that would be annoying
to discover manually. Start with an independently useful agent, such as a small
RAG agent, and a manageable suite of representative scenarios. The suggested five
tools and twenty scenarios are examples, not quotas.

Save a baseline, change the agent, save a candidate, and compare. Exercise realistic
prompt, tool, or retrieval changes. Record what Wraith caught, what it missed, and
whether finding and diagnosing the regression became easier. Deterministic test
doubles remain important for offline tests; synthetic intentional failures alone
do not establish this milestone.

## Core experience

The install → configure → run → save → change → compare path should be easy to
repeat. Reports should surface actionable regressions with the scenario, baseline
behavior, candidate behavior, expectation, and classification. Prioritize failures
over incidental differences, explain configured gates, and preserve honest limits
around missing instrumentation and stochastic evidence.

GitHub source, issues, releases, a clear README, binaries, and Actions are the initial
distribution path. Native platform execution is checked by CI and native archive smoke tests;
real project PR adoption still needs validation. Apache-2.0 is selected; public
releases require the owner's request.
Cloud, auth, billing, databases, dashboards, and a substantial website are deferred.

## Learn from real use

After dogfooding and distribution validation, aim for roughly 5–10 developers to
install Wraith on their own agents. Observe actual integration rather than asking
whether they hypothetically like the idea. A lightweight pilot record should capture:

- Agent and change tested; setup time and the point of friction.
- Useful findings, missed regressions, and misleading or noisy gates.
- Whether the developer could understand and act on the comparison.
- Whether they ran it again, added it to CI, or stopped using it, and why.

The adoption signal is projects using Wraith repeatedly each week or on PRs. Stars,
downloads, and social attention provide context but do not establish product value.
Collect this evidence through voluntary feedback or shared CI examples; do not add
telemetry or upload agent data by default.

Let repeated needs choose the next work: checks, scenario authoring, SDKs, trace
import/replay, PR reporting, or stronger sample decisions. Shared history and paid
team features follow demonstrated team use. Suggested schedules, evaluator counts,
prices, and revenue examples are hypotheses, not commitments or validated forecasts.
