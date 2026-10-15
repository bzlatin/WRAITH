# Automated support-agent trial

This finite trial asks whether Wraith adds useful workflow evidence beyond ordinary
tests. Codex operates a standalone mock application and reports findings. It does
not modify a personal app, call a model provider, or upload evidence.

## Start

Install [Wraith](install.md) and Python 3.10+. From the source checkout:

```sh
python3 scripts/trial.py start
python3 scripts/trial.py next
```

The runner prefers Wraith on PATH, then `~/.local/bin/wraith`, then the local debug
build. Override with `--binary /path/to/wraith` before `start`. Windows uses `python`
and can select `wraith.exe`. `--root path` starts a separate experiment.

Setup freezes the application, requirements, data, regression contracts, component
tests, task acceptance checks, and Python adapter. It validates a baseline and three
calibration controls. The application runs independently; see
[its guide](../examples/support-agent/README.md).

## Codex's work loop

`next` returns a task and an isolated candidate directory. Codex implements the
requested feature there, then runs:

```sh
python3 scripts/trial.py evaluate
python3 scripts/trial.py finish
python3 scripts/trial.py next
```

`evaluate` runs the fixed component tests, task-specific acceptance checks, and
Wraith comparisons using the trusted baseline policy. It records the exact source
snapshot, hashes, version, outputs, failed checks, and HTML report. Repeating an
unchanged completed evaluation reuses its result. Repairs produce a new attempt;
prior failures and the baseline remain fixed. `finish` requires all three checks
to pass against the latest candidate. Tasks each start from the original baseline;
they are independent experiments, not cumulative releases.

For a failing comparison, Codex writes a JSON judgment with `classification`,
`reason`, and concrete `evidence`, then runs `triage judgment.json`. Classifications
include `actionable_regression`, `false_alarm`, `known_debt`, `execution_error`, and
`unresolved`. Judgments are immutable and explicitly provisional. They do not
turn a failed or inconclusive gate into a pass.

## Evidence and automation

`status` regenerates `.wraith/trial/report.md`. Per-attempt `report.html` files are
real Wraith reports. Calibration controls are separated from Codex development
comparisons. Counts distinguish overlapping component-test catches, unresolved
findings, and reviewed regressions beyond component tests. Passing tasks alone
produce an insufficient-evidence verdict about incremental value.

The included `wraith-trial` skill defines the bounded Codex procedure. A heartbeat
can process one task per run, investigate failures, and stop at queue completion.
The desktop app and computer must remain running for local scheduled work; see
[official scheduling guidance](https://learn.chatgpt.com/codex/automations).
Scheduling does not bypass permissions. Codex uses account usage even though this
mock application has no paid model calls.

Trials remain under ignored `.wraith/`. Resume interrupted evaluation with the same
candidate: partial attempts stay incomplete and a new attempt is allocated. A hard
kill can leave `trial.lock`; verify its process stopped before removing that file.
Interrupted initial setup before state creation requires an explicit new `--root`.
Changed frozen inputs, baseline evidence, or binary hashes reject reuse.

This executes trusted local code; it is not a network or filesystem sandbox.
Offline fixtures do not measure prompt quality, live-model accuracy, or demand.
A later live phase needs its own explicit shared budget. A useful mock result
justifies an independent project pilot, not a claim of production validation.
