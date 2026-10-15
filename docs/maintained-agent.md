# Testing fixes in a maintained agent

Wraith runs nine frozen contracts against Hugging Face's
[smolagents](https://github.com/huggingface/smolagents) `ToolCallingAgent`, then
compares three isolated fixes and their combined version. The agent's real tool
loop, validation, retries, and stream handling execute locally. A scripted model
supplies responses; no provider requests or API keys are needed.

This study targets defects found through source inspection at revision
`96f33faaf028479119ec8d34507b47694cf14e34` (Apache-2.0). It measures reproducible
behavior and test overlap, not blind discovery, production model quality, or adoption.
The upstream repository and its tests are unchanged; patches are local examples.

## Results

| Version | Wraith contracts passed | Comparison | Existing tests passed / skipped |
| --- | --- | --- | --- |
| Unmodified | 2/9 | Baseline fails expectations | 25 / 1 |
| Execute checks under Python `-O` | 4/9 | Blocks two new error assertions | 25 / 1 |
| Handle callable diagnostic names | 4/9 | Passes with existing debt | 25 / 1 |
| Close streams cleanly | 3/9 | Passes with existing debt | 25 / 1 |
| Combined fixes | 9/9 | Passes | 25 / 1 |

The seven original failing scenarios share three root causes:

- An `assert` removes final-answer validation under Python optimization.
- Rejected callable objects and partial functions crash diagnostic formatting,
  which assumes every callable has `__name__`.
- Closing a stream before tool execution yields during `GeneratorExit`.

Executing checks under `-O` exposes the callable crash in two scenarios. Wraith
shows a new `AttributeError` where none occurred before, while normal upstream
tests and the existing function-check tests under `-O` pass. Both scenarios already
failed their answer/check-count expectations. This is a useful failure interaction,
not two newly broken tasks or evidence of improved answer accuracy.

Existing tests also help: running two unchanged validation tests under `-O`
detects the skipped checks; promoting an existing generator warning to an error
detects the stream issue. A new targeted unit test detects the callable crash.
Wraith supplies repeatable application contracts and before/after reports; these
results do not establish that unit tests could not catch the same defects.

The selected subset is listed in [source.json](../examples/maintained-agent/source.json).
One test is already skipped upstream (GH-1255/GH-1409). The full upstream suite was
not run. See [machine-readable results](evidence/maintained-agent.json).

## Reproduce automatically

Use Python 3.12+ and a current source build of Wraith. From the repository root:

```sh
cargo build --workspace --locked
python3 scripts/maintained-pilot.py reproduce --install
```

Installation downloads the pinned source and locked Python dependencies. Evaluation
then runs offline. A cooperative socket guard blocks ordinary Python connections;
it is not an adversarial sandbox. Linux CI repeats this command when the fixture
or runner changes, with read-only permissions and no provider secrets.

The command freezes source, contracts, tests, dependencies, and project policy;
applies the reviewed patches to separate candidates; runs upstream tests and
controls; saves Wraith comparisons; and verifies the combined fix. An expected
partial-fix rejection is recorded as exit 1 in its evidence. The reproduction
command succeeds only after validating the expected decisions and combined checks.
It does not publish a release or send anything upstream.

Read `.wraith/maintained-agent-study/report.md` for the comparison table and links to
native HTML reports. `assessment.json` contains a summary without local paths,
hostnames, or environment values. Raw artifacts stay in the ignored experiment
root. Native history may contain local paths and application data; review it before
sharing. No human setup/review time, maintainer adoption, or revenue was measured.

The baseline deliberately contains failed requirements for diagnosis. **It is not
an approved green CI baseline.** Passing relative comparisons can retain existing
failures. Only the combined fix passes all nine requirements.

## Operate a new local change

To reuse an existing checkout and virtual environment without installation:

```sh
python3 scripts/maintained-pilot.py --root .wraith/another-study prepare \
  --upstream /path/to/smolagents --python /path/to/venv/bin/python
python3 scripts/maintained-pilot.py --root .wraith/another-study candidate combined
# Edit only src/smolagents/agents.py inside the returned candidate directory.
python3 scripts/maintained-pilot.py --root .wraith/another-study evaluate combined
```

The finite reproduction expects all four reviewed candidates before `finish`.
Use `apply-reviewed ID` instead of `candidate ID` to apply a frozen example patch.
Use `verify` to check evidence seals or `report` to regenerate the summary without
rerunning the agent. Completed experiments cannot acquire more attempts. Changed
policies, binaries, dependencies, or contracts require an explicit new root.
Incomplete setup and evaluation logs are preserved; never overwrite them.

Next useful study: freeze a task suite before inspecting another change, then
compare an actual feature implementation with the project's unchanged tests.
That would provide stronger evidence about regression prevention than these
targeted existing-defect reproductions.
