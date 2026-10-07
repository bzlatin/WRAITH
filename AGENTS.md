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
- Project/workflow records use schema 1 separately from run/comparison schema 4.
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
