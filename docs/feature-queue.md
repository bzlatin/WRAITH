# Support-agent feature queue

This finite experiment applies three independent feature changes to the synthetic
support agent: policy-search aliases, normalized pasted order IDs, and structured
human-handoff details. Each candidate starts from the same baseline. No defect is
deliberately injected. This is developer-selected work on an authored application,
not independent adoption or proof of commercial demand.

The ten `multi-step-v2` Wraith cases stay fixed. Ten existing application tests
are frozen from `LiveAgentTests`; the runner changes only which application module
they import. Separate acceptance tests verify each new feature. Report acceptance,
component-test failures, Wraith regressions, and execution errors separately.
A feature that passes its tests can still break old behavior; a passing queue with
no useful new catch does not establish incremental detection value.

## Run from source

```sh
cargo build --workspace --locked
python3 scripts/change-pilot.py prepare
python3 scripts/change-pilot.py apply-reviewed
python3 scripts/change-pilot.py offline
```

Preparation creates isolated baseline copies and freezes source, cases, tests,
native binary, and recorded model decisions. It first confirms that the new
feature acceptance tests fail on the unchanged application. `apply-reviewed`
applies the three recorded implementations; Codex can instead edit only the
returned candidates’ `agent.py` files before evaluating. Git must
be available to apply the patches; they touch only each candidate's `agent.py`.
Do not edit frozen files, policy, results, or the existing live experiments.
Existing roots and attempted runs cannot be overwritten or automatically retried.

Offline mode replays the earlier baseline's recorded tool selections and final
model drafts through the changed application. Tools execute locally and Wraith
records their actual results. The model does not reconsider changed tool results;
this tests application compatibility for those fixed decisions, not model quality.
If a tool result changes, replay stops with an execution error instead of treating
an old model answer as a new response to different evidence.
Reports label the replay and count zero provider requests. Component and feature
acceptance tests run without provider access.

## Optional live comparison

```sh
python3 scripts/change-pilot.py live --allow-live
```

Obtain separate spending authorization first. One shared **120-request cap** covers
a fresh baseline and all three candidates, failures included. Each version uses
the same ten cases and at most three attempts per case. Check reuses the baseline's
budget; there are no retries, automatic budget resets, or extra comparisons.
A failed baseline stops candidate spending. Failed acceptance or component tests
skip that candidate's live evaluation. A provider/execution failure stops the queue.
Unused requests are not spent after the queue completes.

Open the experiment's `offline/report.md` or `live/report.md`. Each row links tests
and native JSON/HTML evidence, records duration as machine runtime, and compares
Wraith findings with the frozen application tests. This cannot measure human
triage time, causal prompt effects, production accuracy, or willingness to pay.
Review each finding before calling it a useful catch or false alarm. Each mode's
completed files are sealed; new work requires an explicit new experiment.

## Recorded offline result

The baseline and all three independent implementations passed the ten frozen
application tests and ten Wraith cases; all three new-feature acceptance tests
passed. The acceptance tests failed on the unchanged application before changes.
The successful replay used **zero provider requests**. Both systems passed all
three changes, so this run produced **zero additional useful catches**.
[Sanitized results](evidence/feature-queue.json) retain source hashes, individual
decisions, and overlap counts. Full local evidence is under
`.wraith/feature-queue-validated/offline/`.

An initial replay rehearsal failed because recorded search activity used a list
while the actual function returned a JSON envelope. That harness error remains
preserved under `.wraith/feature-queue-v1/`; it is not counted as an application
regression. The corrected harness checks reconstructed tool return envelopes
against the frozen implementation and observed trace. Automated fault tests
exercise evidence tampering and budget/baseline stops without provider requests.

The live queue is implemented but has not run. It requires separate authorization;
the previous completed experiment's remaining requests are not automatically reused.
