# Product direction

Wraith should make an agent change easier to review: show what broke, show the
before/after evidence, and give the developer a check they can repeat.

## Validation goal

Catch a useful, naturally occurring regression in an independently useful agent,
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
