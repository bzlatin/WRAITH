---
name: wraith-trial
description: Operate Wraith's finite offline support-agent trial, implement isolated development tasks, investigate regressions, and report evidence beyond component tests. Use for this trial and its scheduled continuation, not general app development or live model evaluation.
---

# Wraith trial operator

Work in the Wraith checkout containing `scripts/trial.py`. Read its `AGENTS.md` and
`docs/automated-trial.md`. The user authorizes implementing the mock development
queue and investigating results. Keep all application changes in the returned
candidate directory; the runner, frozen inputs, data, tests, and old evidence stay
unchanged during a task. Use runner commands to update state; do not edit state.json
or attempt journals manually. No external skills or network are needed for a normal run.

Run `python3 scripts/trial.py status` (use `python` on Windows). If not initialized,
run `start` once with an installed binary. Resume the existing experiment; a changed
binary or frozen baseline is a blocker, not permission to reset it.

Run `next` to obtain the current task or the next pending one. Read its task file
and application requirements. Implement the feature correctly in the isolated
candidate. Do not add intentional defects, dispatch on scenario IDs, alter tests,
or tailor output to expected examples. Record tool activity where real operations
occur; cache hits must not be presented as fresh search execution.

Run `evaluate`. It checks component behavior, new-feature acceptance, and the frozen
regression gate separately. Passing the regression gate without implementing the
new feature is not enough. Fix concrete failures and evaluate again; prior attempts
remain immutable. An unchanged source reuses its existing result.

For a failing Wraith comparison, inspect `comparison.stdout`, `unit.stderr`, both
outputs in `report.html`, and the evaluated source. Reproduce the exact failing
request. Write a short JSON judgment with classification, reason, and evidence;
record it using `triage path/to/judgment.json` before repairing the candidate.
Judgments are provisional. Do not call a finding useful merely because Wraith
reported it. Record whether component tests also caught it. Unresolved semantic
claims stay unresolved; inconclusive or execution errors never become passing gates.

Call `finish` only after every check passes. Process one development task per
scheduled run, allowing at most three new evaluations of that task per run. After repeated failure to
make progress, preserve the evidence and report the blocker instead of weakening
checks or resetting the experiment. The original requirements and suite are visible;
this is not a blind or independent benchmark.

When all tasks are complete, inspect `report.md` and produce a short engineering
and product assessment: repeat-run reliability, observed useful catches beyond
component tests, noise/unknowns, and one next recommendation. Do not claim customer
adoption, natural production regressions, or live-model accuracy from a mock trial.
Pause the associated heartbeat using its saved identifier and existing settings
once the finite queue is complete. Preserve this chat and evidence.

Live requests, publishing, pushing branches, application merges, and external
messages are outside this trial. Local scheduling depends on the host and app being
available. Keep findings and app artifacts private under ignored `.wraith/`.
