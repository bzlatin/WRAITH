# Automated coverage challenge

This finite offline campaign asks which application defects Wraith's scenarios
miss, then reruns the same defects after adding reviewed checks. It uses the pinned
LLM application and environment from the [application pilot](application-pilot.md).
No maintainer outreach, live model requests, or scheduled waiting is required.

## Run the calibration

Build the current source; batch import is not in the published v0.5.0 binary:

```sh
cargo build --workspace --locked
python3 scripts/application-pilot.py prepare --install
python3 scripts/coverage-challenge.py --root .wraith/coverage-original \
  --resources .wraith/app-pilot-validated --binary target/debug/wraith
python3 scripts/coverage-challenge.py --root .wraith/coverage-expanded \
  --resources .wraith/app-pilot-validated --binary target/debug/wraith --expanded
```

If that application pilot root already exists, omit its preparation command.
`--install` allows source/package downloads; challenge evaluation makes no provider
requests. On Windows, use `python` and `target/debug/wraith.exe`. The campaign
reuses the prepared environment through local directory symlinks (Windows may
require Developer Mode). Keep the chosen binary unchanged until both runs finish.

The original suite has nine CLI scenarios. The expanded suite imports eight
reviewed SDK cases through `wraith cases import`: sync/async callbacks,
cancellation, errors, correlation, pause siblings, partially completed history,
and stale-history handling. The real application executes these paths; the Echo
model supplies deterministic requests. This does not test reasoning, tool choice,
retrieval quality, or provider behavior.

Each of twelve source mutations changes one application function in an isolated
copy. Four benign controls exercise equivalent code changes. Exact anchors and
Python syntax are checked before evaluation; test files stay unchanged. A separate
witness runner must fail the named reviewed requirement before a mutation counts
as a valid fault. Witnesses and Wraith share the reviewed expectations; they are
separate execution paths, not independent ground truth or independent authors.

Every change runs the witness checks, the unchanged 60-test upstream offline
subset, and native Wraith `check`. Setup errors and unwitnessed mutations are
excluded from detections. Controls must pass all three checks. A campaign can
complete with invalid changes, but records `validCalibration: false` and exits 2;
completion alone is not acceptance. Reusing a completed root verifies saved evidence without
rerunning comparisons. Preserve partial roots and use a new explicit root after
setup failures. Completed changes can resume; incomplete change directories are
retained for diagnosis.

Reports, source snapshots, oracle failures, JUnit results, native HTML, and runner
copies remain under the chosen ignored root. Baselines and frozen inputs never
refresh automatically. These are trusted local records, not signed attestations.

## Development after calibration

Prepare a separate queue using the expanded, fixed suite:

```sh
python3 scripts/coverage-challenge.py --root .wraith/coverage-development \
  --resources .wraith/app-pilot-validated --binary target/debug/wraith \
  --expanded --development
python3 scripts/application-pilot.py --root .wraith/coverage-development task resume-opt-out
# Codex edits only the returned candidate's approved application module.
python3 scripts/application-pilot.py --root .wraith/coverage-development evaluate resume-opt-out
```

Repeat `task`/`evaluate` for `argument-isolation`, then run `finish` with the same
root. Execute evaluations serially: native checks share a project lock. Tasks are
independent local changes, not upstream contributions or a combined release.
Feature acceptance is separate from the fixed regression gate. The optional
fixture arguments to the preparation helper reuse the existing pilot's baseline,
provenance, and evidence checks; there is no second execution engine.

## Observed result and decision

On macOS arm64, the original suite caught **3/12 seeded faults**; the expanded suite
caught **12/12**. All four controls passed both suites. The selected upstream tests
caught all twelve faults. The nine misses were scenario gaps expressible using
existing JSON checks; no new evaluator was needed. These are finite calibration
counts, not population detection rates or prospective discoveries.

Two Wraith improvements address observed setup friction: importing a reviewed
batch atomically and warning about weak expectations per scenario, including
within mixed suites. Neither infers missing source coverage nor treats observed
output as a correct answer. Source-built commands are documented in the
[integration guide](getting-started.md); published v0.5.0 remains unchanged.

This phase establishes stronger workflow-contract coverage. It does not establish
an advantage over the existing upstream test subset, time saved by reviewers,
customer demand, or live-model quality. Further work should address observed
integration/report friction or evaluate a separately budgeted model-quality suite,
not increase the mutation count to claim product validation.
