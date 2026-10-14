# Prospective application pilot

This finite pilot connects Wraith to the independently maintained
[LLM application](https://github.com/simonw/llm), then evaluates three legitimate
changes in isolated source copies. It runs the actual CLI, function-tool loader,
approval callbacks, and tool orchestration. Its model is the existing offline Echo
plugin; tools perform harmless local operations.

The source revision and Apache-2.0 provenance are pinned in
[source.json](../examples/application-pilot/source.json). Contracts and feature
acceptance checks are frozen before candidate edits. The tasks were selected for
this experiment; they are not changes requested or accepted by LLM's maintainers.

## Run from a source checkout

Use Python 3.13, Git, and an installed Wraith v0.5.0 binary:

```sh
python3 scripts/application-pilot.py prepare --install
python3 scripts/application-pilot.py task partial-tools
# Codex edits only the approved modules in the returned candidate directory.
python3 scripts/application-pilot.py evaluate partial-tools
```

Repeat `task`/`evaluate` for `tool-prefix` and `approval-json`, then:

```sh
python3 scripts/application-pilot.py finish
python3 scripts/application-pilot.py status
```

`--install` permits Git/package downloads into ignored directories. Requirements
are pinned; LLM is installed separately from the declared source revision.
Evaluation runs with the Echo plugin and a cooperative guard that rejects socket
connections. Credentials are replaced with non-secret fixture values in child
processes. This executes trusted local code, not an adversarial security sandbox.

Preparation uses native `init`, `doctor`, and `baseline`. Each evaluation runs the
unchanged upstream test subset, separate feature acceptance, and native `check`.
The subset is `test_tools.py` plus `test_pause_resume.py`, excluding three recorded
provider tests with `not vcr`. It is not the full application test suite.

`finish` requires the latest source of all three candidates to pass every check
against the same baseline. It seals native history and closes the queue. Each task
starts from the original source; changes are independent, not cumulative releases.
No scheduled run is needed after queue completion.

## Evidence and boundaries

Open `.wraith/app-pilot-validated/report.md` for results and HTML report links.
Native runs, comparisons, and reports live in `project/.wraith/history/` beneath
that directory. Source snapshots and failed attempts remain preserved.

The runner rejects changed contracts, tests, adapters, policies, dependency
versions, baseline pointers, or completed evidence. Candidate edits are restricted
to the task's declared application modules. Source fingerprints identify the exact
application; native Git metadata identifies the surrounding harness checkout.
Environment values and fixture-model token estimates are not recorded.

The fixture simulates terminal stdin so approval answers reach the confirmation
prompt. It normalizes generated tool-call IDs and records tools at their actual
execution points. Neither rejected tool requests nor tool discovery are recorded
as successful executions. Async CLI paths run in a worker thread to avoid nesting
event loops inside the function adapter.

An interrupted preparation needs an explicit new `--root`; preserve its logs for
diagnosis. Evaluation can be retried as a new immutable attempt. Investigate
failures before repairing a candidate; never weaken checks to complete a task.
Exits 0/1/2/3 retain pass, failed check, execution error, and inconclusive meanings.

## Observed result

On macOS arm64, all nine baseline scenarios and 60 selected upstream tests passed.
Three independent application changes passed feature acceptance, the upstream
subset, and Wraith checks. Approval-format differences remained informational.
No additional regression surfaced, so incremental detection value and diagnosis
time remain unproven. No provider model requests ran.

Preparation timing excludes discovery and earlier dependency bootstrap. The
recorded contract draft-to-freeze span overlaps harness development; it is not
human authoring time. This pilot does not measure model quality, statistical noise,
maintainer adoption, unattended scheduling, or native Linux/Windows execution.
