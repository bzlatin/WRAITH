# Working on Wraith

Wraith is a local Rust agent regression-testing engine. Its purpose is to show what
an agent change broke, using the same scenarios before and after the change.

## Product and architecture

- Keep the core framework neutral. Provider SDKs and application logic belong in
  external adapters implementing the versioned JSON subprocess protocol.
- Two crates: `wraith-core` owns models, execution, evaluation, artifacts, and
  comparison; `wraith-cli` owns project setup, workflow history, reports, arguments, and exit codes.
- Favor small structs, enums, and functions. Avoid speculative traits, extra crates,
  databases, hosted features, or custom runtimes.
- Run locally, upload nothing by default, and never serialize the environment.
  Outputs and diagnostics may still contain application data.
- Treat behavior differences and measured regressions separately. Unchecked changes
  are informational; configured checks determine the gate.
- Repeated samples are independent observations, not paired seeds. Report sample
  counts and uncertainty honestly; do not claim significance from raw rate changes.

## Product validation priorities

Read `docs/product-direction.md` and `docs/roadmap.md` before choosing new work.
The next product milestone is catching a useful regression in a real agent, then
seeing developers run Wraith repeatedly during changes and in CI.

- Prioritize install/config/run/save/compare friction and actionable reports.
  Show the scenario, baseline, candidate, expectation, and regression classification.
- Synthetic fixtures validate engineering behavior; they do not prove product value.
- Choose additional evaluators, SDKs, replay, and statistical policies from observed
  gaps. Do not treat feature counts or speculative timelines as acceptance criteria.
- Keep GitHub, binaries, README, and CI as the initial distribution path. Defer
  cloud, accounts, billing, dashboards, and substantial branding work.
- Learn about repeat use through voluntary pilot feedback; keep telemetry off.

## Compatibility and execution

- Rust 2024; honor the workspace MSRV and checked-in `Cargo.lock`.
- Configuration, adapter protocol, run artifacts, comparison reports, and package
  versions are separate contracts. Increment schemas for incompatible changes,
  migrate supported old artifacts explicitly, and reject unsupported future versions.
- Comparison must reject changed inputs, expectations, metadata, or missing tests.
- `expect.json` evaluates final output using typed JSON-pointer rules. Read
  `docs/structured-output.md`; keep missing values and empty `each` arrays failing.
  Run/report schemas are 4; migrate supported schemas 1–3 in memory.
- Timeouts and cancellation must terminate descendants and reap the direct child.
  Use platform containment through safe APIs. Keep platform limits documented.
- Stdout is protocol data only. Drain bounded stdout/stderr concurrently; emit
  actionable diagnostics without backtraces or dumping environments.
- Preserve CLI exits: 0 passed, 1 behavioral/threshold failure, 2 execution/setup
  failure, 3 inconclusive statistical comparison (blocks CI). Interrupted execution uses 130 and must never save a partial run as complete.

## Setup and workflow boundaries

- Read `docs/getting-started.md`, `docs/ci-setup.md`, and `docs/install.md` before
  changing onboarding. CLI modules `project`, `workflow`, `report`, `cases`, and
  `ci` own these features; core evaluation stays independent of project setup.
- Python/TypeScript function adapters live under `adapters/` and are embedded in the
  binary. They record observed tools, retrieval, and usage; never fabricate traces.
- Baselines are explicit and fixed. Suite/sample/mode changes require `--replace`;
  ordinary checks must never silently refresh them. Save immutable run history and
  stored comparisons so regenerating a report does not change the original decision.
- Live mode requires opt-in and a shared request budget. Reserve before each actual
  provider attempt, consume failed attempts, and preserve budget identity through
  failures/interruption. A fresh budget requires an explicit new experiment.
  Helpers cannot cap hidden retries or code that bypasses instrumentation.
- Project settings use schema 1 and workflow records schema 2, separately from
  run/comparison schema 4. Migrate workflow schema 1 in memory with jobs=1; reject
  unsupported future versions before execution.
  Store declared model names and credential variable names, never credential values.
- Reports are self-contained escaped HTML, with failures first and native disclosures.
  Read `DESIGN.md` for report UI rules; keep scripts and remote resources out.
- Generated PR CI runs offline against the exact base SHA with a trusted base policy,
  read-only permissions, and no provider secrets. Verify release availability before
  claiming the generated installation step works on GitHub.

## Development and validation

Read `docs/architecture.md` and the relevant module before changing contracts.
Use offline deterministic agents and meaningful fault tests. Do not require API keys.
CI must run untrusted agent code without repository secrets or write permissions.

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --workspace --locked
```

Integration tests require Python 3 (`python3` on Unix, `python` on Windows). TypeScript uses `npm ci`
and `npm run build` in `examples/typescript-agent`. Run `python3 -m unittest discover -s scripts/tests`
for adapter/installer/packaging changes. `scripts/external-pilot.py` executes pinned
upstream orchestration offline; its optional installation step requires network. Exercise both the passing and
deliberately failing demo whenever execution/comparison contracts change.

Use an installed Rust toolchain matching the workspace MSRV. Do not edit user shell
profiles or commit machine-specific paths. See [CONTRIBUTING.md](CONTRIBUTING.md).

Do not publish releases, push branches, or choose a distribution license unless the
user requests it. Implement and validate packaging locally first. Record precisely
which platforms ran, which merely type-checked, and what remains unverified.

The repository is public and Apache-2.0 licensed. v0.5.0 is published; later release
publication needs its own user request. The generated PR check uses the published v0.5.0 binary against the offline RAG example.
Refresh `THIRD_PARTY_LICENSES.txt` with `scripts/license-notices.py` when dependencies
change. Read `docs/statistical-gating.md` before changing rate decisions; never turn
inconclusive evidence into a passing gate. Run `scripts/pilot.py` for RAG changes.

## Automated mock-agent trial

Read `docs/automated-trial.md` before operating `scripts/trial.py`. The standalone
support application is an offline mock. Keep calibration faults, Codex development
regressions, and independent product evidence separate. Candidate changes belong
only in the directory returned by `next`; never edit frozen tests, policy, baseline,
or old results. Task acceptance is separate from the regression gate. A passing
queue is insufficient evidence of incremental value without reviewed useful catches.

Read `docs/historical-pilot.md` before operating `scripts/historical-pilot.py`.
Keep historical reproductions distinct from prospective findings. Run upstream
tests unchanged and report the selected subset; a later targeted unit test can
detect the same defect. Preserve incomplete experiments and completed evidence.

Read `docs/application-pilot.md` before operating `scripts/application-pilot.py`.
Edit only the returned candidate's approved application modules; keep offline
fixtures and upstream tests frozen. Report developer-selected local changes
separately from maintainer adoption and retrospective bug reproductions.

Read `docs/coverage-challenge.md` before operating `scripts/coverage-challenge.py`.
Seeded defects calibrate coverage; do not count them as prospective discoveries.
Keep witness validation, upstream overlap, controls, and execution errors separate.

Read `docs/first-use.md` before operating `scripts/first-use.py`. Its prepared
fixtures measure mechanical setup only; do not claim human authoring time or buyer
validation. Keep market offers, Wraith technical results, and paid demand separate.

Read `docs/live-pilot.md` before operating `scripts/live-pilot.py`. Preparation is
offline; live execution needs explicit spending authorization. Never reset the
shared budget, retry an attempted experiment, or turn ten live observations into
a production-accuracy or causal-regression claim.

Read `docs/feature-queue.md` before operating `scripts/change-pilot.py`. Keep the
frozen suite and component tests unchanged. Candidate patches implement features,
not seeded faults; report recorded-model replay separately from new live calls.
Keep acceptance, test overlap, execution errors, and reviewed useful catches separate.

Read `docs/maintained-agent.md` before operating `scripts/maintained-pilot.py`.
Keep source-guided existing-defect reproductions separate from blind discoveries.
The deliberately failing diagnostic baseline is not an approved CI baseline.
Partial comparisons can pass while retaining debt; require all fixed contracts
for the combined fix. Edit only returned candidate modules, preserve upstream
tests, and report optimized/strict-warning controls alongside ordinary tests.


Read `docs/workflow-value.md` before operating `scripts/workflow-pilot.py`.
Keep the original feature development separate from recorded reproduction and
known-defect calibration. Require a green fixed baseline; never weaken the suite
for a candidate. Record machine runtime separately from human effort and avoid
claiming a false-positive rate or customer ROI from repeated deterministic runs.

Read `docs/upstream-study.md` before operating `scripts/upstream-pilot.py`. Freeze
selection rules before inspecting candidate changes; keep blocked merges and setup
failures in the denominator. Never replace blocked PRs, resolve prerequisite patch
conflicts, or retry an incomplete attempt. Recorded reproduction is not new evidence.
Source-path overlap alone does not establish that changed behavior was tested.

Read `docs/weather-comparison.md` and `docs/product-assessment.md` before operating
`scripts/weather-study.py`. Keep equal requirements and observation code across
runners, new-feature acceptance separate from old-behavior checks, and seeded
controls separate from natural catches. Preserve qualification drafts and completed
evidence. Report process-isolation differences and machine timing separately from
human savings. The current decision pauses feature expansion and commercial-service
work until a concrete repeated workflow benefit is demonstrated.

## Experimental ingestion verification

Read `docs/index-product-decision.md` and `docs/index-audit.md` before changing
`wraith index check` or `adapters/index/`. Keep database SDKs outside Rust core.
Index exports/reports use their own schema 1. Exact identities are scoped by tenant
and document; content equality must not collapse source identities.

Expected manifests must come from intended ingestion, never from observed output.
Incomplete scans, missing revision/manifest data and concurrent writes cannot pass.
An absent source entry is not a deletion tombstone. Quiescence is an explicit
exporter attestation; equal counts do not establish snapshot consistency. Keep
read-only checks separate from repair, retrieval exposure and compliance claims.
Run the index Rust tests and `scripts/tests/test_index_export.py`; validate optional
Qdrant changes with the local demo. Controlled defects and scale measurements are
engineering evidence, not adoption or revenue. The original broad expansion pause
remains in effect outside this bounded capability.

For `examples/verified-ingestion/`, read `docs/verified-ingestion.md`. The optional
LlamaIndex integration is a full local rebuild: create expectations before writes,
keep candidate collections separate, promote only after exit 0, and retain failed
attempts. Do not enable writes to arbitrary or existing servers, or claim concurrent-reader
safety from local Qdrant tests. The owned loopback server runner has its own explicit scope. Run its separate `tests/test_workflow.py --wraith <source-binary>`
with the pinned optional dependencies. Keep plain-script results and injected faults
distinct from natural findings, human savings and adoption.

Read `docs/ingestion-server-checks.md` before operating `server_check.py`. It starts
its own disposable loopback server and uses only deliberate controls. Never point
it at an existing database or claim distributed publisher safety. Preserve completed
and incomplete run directories; do not overwrite old results. Keep killed-publisher
orchestration separate from the missing-chunk gate and from naturally found defects.
Report logical file lengths separately from allocated blocks; neither is customer ROI.
The optional fixture downloader pins public binary/archive hashes. No server binary
or downloaded corpus belongs in Git. Linux CI wiring does not establish a successful
GitHub execution until it has actually run.

Read `docs/ingestion-operations.md` before changing the optional recovery inspector.
It is read-only and its retirement list is for review, never deletion authorization.
Protect every actual alias, retained rollback copies, unfinished-job references and
unbound/invalid evidence. Historical build verification is not live-content health.
Keep old evidence untouched: new job records and evidence hashes use integration
schema 1, separately from native workflow/run/report schemas. Do not retroactively
bind legacy history. Compare trusted-input script answers and validation limits
honestly; controlled recovery cases do not prove adoption or human time savings.
Run the stdlib inspection tests and the owned-server controls when decisions change.

Read `docs/repeated-ingestion.md` before running `repeat_workflow.py`. Freeze and
preserve protocol, inputs, completed and incomplete results. Both lanes share the
operational wrapper; only the checker changes. Never attribute shared recovery,
hash validation or retention rules uniquely to Rust. The reference's trusted-export
scope and JSON-only output differ from native validation/HTML; report those limits.
Job/verification metadata explicitly labels the verifier; reject conflicting or
unknown labels. The ordinary CLI keeps Wraith as its verifier. Public-release
snapshot membership changes are not necessarily upstream file deletions. Keep
normal transitions, deliberate faults and inconclusive outcomes separate. Current
results justify keeping the integration and pausing further feature/SaaS expansion.

Read `docs/upstream-ingestion.md` before changing the optional LlamaIndex manifest
hook or `upstream_check.py`. Use public transformation hooks, not framework patches.
The hook is for uncached synchronous single-worker rebuilds without a docstore;
reject skip modes. Capture source revisions before writes and append capture last.
Keep the hash-pinned upstream recipe and license, offline provider substitutions,
qualification errors and ordinary source changes explicit. Both checkers share
the capture/export work. Routine CI uses this focused compatibility check; do not
repeat full product studies on every push or claim maintenance savings from LOC.
