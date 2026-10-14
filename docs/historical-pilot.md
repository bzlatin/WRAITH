# Reproduce a real upstream regression

This source-checkout pilot tests one historical PydanticAI approval bug using its
unmodified source. It then supports a finite queue of changes to a small offline
approval workflow. No private application or model credentials are needed.

The [original report](https://github.com/pydantic/pydantic-ai/issues/3350) describes
an action executing without approval when an agent resumes from saved messages.
The pilot pins the revision before the introducing change, the introducing
revision, and the later fix in
[source.json](../examples/historical-approval/source.json). Every export retains
the upstream MIT license. The tool only records an in-memory receipt.

## Run the retrospective pilot

Use Python 3.13, Git, and an installed Wraith v0.5.0 binary. From the Wraith source
checkout:

```sh
python3 scripts/historical-pilot.py prepare --install
python3 scripts/historical-pilot.py historical
python3 scripts/historical-pilot.py status
```

`--install` permits Git/package downloads into ignored `.wraith/` directories.
Subsequent evaluations run offline with `FunctionModel`. Dependencies, source
exports, binary, application, contracts, and acceptance checks are fingerprinted;
the environment is never serialized. Package names/versions are recorded.
`--binary` selects another installed binary; `--python` selects an existing
isolated environment containing the exact pinned dependencies.

The historical command succeeds only when the baseline passes, the introducing
revision fails the two resumed-history scenarios, the fix passes, and the later
upstream regression-test control fails/passes on buggy/fixed code. It also records
the existing approval/deferred test subset from each revision unchanged, using
the same selection. Their tests and snapshots can differ; this is not the full
upstream test suite or a claim that ordinary tests cannot detect the bug.

Open `.wraith/historical-approval-validated/report.md` for results and links to
real Wraith HTML reports. A known bug reproduced after reading its report is
retrospective evidence, not a new or blind discovery.

## Operate the development queue

```sh
python3 scripts/historical-pilot.py task history-roundtrip
# Codex edits only approval_agent.py in the returned candidate directory.
python3 scripts/historical-pilot.py evaluate history-roundtrip
```

Repeat for `receipt-summary` and `pending-details`. Each task starts from the same
fixed baseline. These are separate experiments, not cumulative application changes.
The task instructions and feature checks are frozen during prepare. Evaluation
records the exact application snapshot, existing upstream test subset, feature
acceptance, Wraith run, trusted-policy comparison, timings, and HTML report.

Evaluation exits 0 only when all checks pass; 1 means a failed check, 2 an execution
or setup error, and 3 an inconclusive comparison. Investigate failures before
repairing the candidate. Every evaluation gets a new immutable attempt; neither
repeating commands nor repairing code replaces a baseline or old result.

Completed evidence is checked for accidental changes. Do not edit frozen inputs
or old results. An interrupted initial setup/historical run requires an explicit
new `--root`; preserve the incomplete root for diagnosis. A timed-out/interrupted
evaluation without a completed comparison is not a passing result. The local
runner executes trusted upstream code; it is not a filesystem or network sandbox.

## What this establishes

Verified on macOS arm64 with Python 3.13 and Wraith v0.5.0: the historical bug
failed two scenarios while the selected 13 upstream tests passed. The maintainers'
later targeted test also caught it. The fixed revision passed all six Wraith
scenarios, and three independent development changes passed feature acceptance
and comparison. No live provider requests ran.

This supports workflow contracts for approval and resumed state. It does not
establish prospective bug discovery, customer adoption, model quality, statistical
false-alarm rates, or Linux/Windows execution. The next product test is repeat use
during legitimate changes in an independently maintained agent application.
