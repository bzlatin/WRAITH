# A repeatable agent check with measured overhead

This study tests a real smolagents feature from a passing baseline, then measures
Wraith's cost as a PR step. It uses actual `ToolCallingAgent` execution with a
scripted offline model. No provider requests or private application data are used.

## What changed

The baseline pins smolagents to `96f33faaf028479119ec8d34507b47694cf14e34` and applies
the three reviewed [validation/stream fixes](maintained-agent.md). Sixteen regression
scenarios were frozen before the feature implementation. They cover final-answer
validation, callable checks, optimized Python, streaming, memory reset, and callback
counts. The 25 passing upstream tests and one upstream skip remain unchanged.

The feature implements [upstream request #1374](https://github.com/huggingface/smolagents/issues/1374):
a final-answer critic can inspect the current action in memory. Acceptance fails
before implementation and passes after it. The feature, existing tests, and all
16 Wraith scenarios pass. **No additional useful feature regression was caught.**
These are local proposed changes, not an upstream merge or maintainer adoption.

The first manual comparison used a `.stdout` filename where the CLI requires an
explicit `.json` path. Its incomplete logs remain preserved as a harness error;
it is excluded from application findings. The new native CI command owns artifact
filenames and comparison orchestration, removing that custom glue.

## Measured result

On macOS arm64, three interleaved repetitions per setting produced:

| Check | Wall time |
| --- | --- |
| Wraith, baseline + candidate, one job | 14.03 s median |
| Wraith, baseline + candidate, four jobs | 4.96 s median |
| Selected upstream tests, candidate only | 1.37 s |

All six comparisons passed without editing the suite. This demonstrates mechanical
repeatability for one deterministic change; it is not a general false-positive
rate. Dependencies were warm. Installation, build, queue, human authoring, and
review time are excluded. Parallel speedup depends on the agent and machine;
latency per observation can increase with resource contention.

A separate calibration restores the already-known upstream defects. Wraith exits
1 while the selected ordinary upstream tests pass. That checks the failure path;
it is not a new prospective discovery. [Sanitized evidence](evidence/workflow-value.json).

## Use the improved workflow

A **current source build** adds one native command for existing offline checkouts:

```sh
wraith --config candidate/wraith.yaml ci check \
  --base-config base/wraith.yaml --jobs 4 \
  --artifacts .wraith/pr-check --summary "$GITHUB_STEP_SUMMARY"
```

Prepare both checkouts and install application dependencies with your normal CI
steps. Use the exact PR base SHA and candidate SHA. Wraith uses the base's scenarios,
expectations, adapter command, and policy in both directories; it ignores the
candidate configuration's contents. Relative application/runtime paths resolve in
each directory. A shared environment must support both versions; a relative venv
path in the command can select each checkout's own environment.

The command requires a passing base, stops before the candidate if it fails, and
preserves exits 0/1/2/3/130. It writes fresh JSON/HTML evidence and a concise escaped
Markdown summary with failed expectations and before/after values. Existing
artifact directories cannot be overwritten. `--summary` appends to an external
file and is optional outside GitHub Actions. It needs no GitHub API token.

The source-built PR workflow exercises this command against Wraith's offline RAG
suite at the exact base/head commits, with read-only permissions and no provider
secrets. A separate job reproduces this feature study and its calibration. The
published v0.5.0 installer and generated release-based CI remain unchanged; these
new commands require a source build until a later release is authorized.

`run`, `baseline`, `check`, and `ci check` accept `--jobs 1..32`; the default is one.
Only use parallel jobs for independent observations. Keep shared-state or live
agents sequential. `baseline` saves its concurrency, and `check` inherits it;
changing it needs `baseline --replace --jobs N`. Schema-1 workflow records migrate to schema 2
with one job; schema 2 records the jobs value. Older binaries reject the newer
records instead of silently changing concurrency. Keep concurrency fixed when judging latency/resource gates.

## Reproduce or continue locally

```sh
cargo build --workspace --locked
python3 scripts/workflow-pilot.py reproduce --install
```

This replays the reviewed feature patch; it is labeled separately from the original
development run. Read `.wraith/workflow-value/report.md` and its native reports.
Raw evidence stays local. The socket guard is cooperative, not a security sandbox.
A new experiment needs a new `--root`; incomplete and completed evidence cannot be
overwritten. `prepare` returns the sole editable application module; `evaluate`
keeps acceptance, upstream tests, and Wraith decisions separate. `benchmark`,
`report`, `verify`, and `finish` operate on that frozen study.

Wraith is useful here as a repeatable contract gate with reviewable history and a
measured additional step. It complements the application's tests. Whether the
extra cases and reports save a team's time still requires observing that team's
changes and review work. No human time savings, customer demand, or ROI is claimed.
