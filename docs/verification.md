# Verification record

## v0.3 increment — October 6, 2026

Package 0.3.0; protocol/config remain version 1; run/report schemas are 3. The
owner selected Apache-2.0 and requested a push to the default branch. New native
CI/package results are available in the repository's GitHub Actions runs; the older
sections below preserve the evidence and limitations at their original milestones.

Verified locally on macOS arm64:

- 32 Rust tests, including statistical bounds, minimum samples, allowances,
  inconclusive CLI exit 3, policy overrides, migration, and process cleanup.
- Five packaging/CI script tests, including Windows path quoting; license and dependency notices included.
- Formatting, Clippy warnings denied, Rust 1.87 all-target checks, release build,
  TypeScript compilation, and workflow linting.
- RAG pilot: 21 comparisons, 0/213 false positives, 0/39 missed labeled regressions.
  These are deterministic controlled mutations, not live-model accuracy estimates.
- Manual statistical fixture: 20 samples yielded exit 3; 200-sample harmless change
  passed; 200-sample stale-policy defect failed.
- Checksummed native macOS archive extracted and executed through init/run/compare.

The first hosted native package run passed on Linux x86_64, macOS arm64/x86_64,
and Windows x86_64 MSVC, including tests and extracted archive smoke checks:
[release validation](https://github.com/bzlatin/WRAITH/actions/runs/37549126668).
The initial Windows general-CI demo exposed a YAML/backslash quoting bug; the demo
now JSON-encodes the command scalar separately from subprocess argument quoting,
with a regression test covering spaces, quotes, and backslashes. The default-branch
[baseline artifact](https://github.com/bzlatin/WRAITH/actions/runs/37549112672) succeeded.

Reproduce with `scripts/pilot.py`, `scripts/smoke-package.py`, and
[the manual dogfooding guide](dogfooding.md). Raw local reports are ignored under
`reports/`; named runs remain local under `.wraith/`. Native CI runs the RAG pilot
on Linux, macOS, and Windows; the release matrix also includes Intel macOS.


## v0.2 increment — October 6, 2026

Implemented all three follow-up workstreams and added root `AGENTS.md` plus an
implementation plan. Current package version is 0.2.0; protocol/config remain version
1, run/report schemas are 2, and the minimum Rust version is now 1.87 because the
Windows process-containment dependency requires it.

Verified on macOS arm64:

- Formatting and Clippy with all targets and warnings denied.
- **28 Rust tests** and **4 Python packaging/CI tests**, all passing.
- Debug and optimized release builds.
- Rust 1.87.0 `check --workspace --all-targets --locked --offline`.
- Windows GNU target `check --workspace --all-targets --locked --offline` from macOS.
  This compiles the Windows implementation and tests; it does not execute them.
- TypeScript strict compilation; Python, JavaScript, direct TypeScript, and compiled
  TypeScript baseline/candidate workflows at both 1 and 4 observations per scenario.
- Genuine CLI SIGINT returning 130, preserving an existing named snapshot, and
  preventing its agent descendant from writing a delayed orphan marker.
- Cooperative cancellation, task abort, timeout, and an exited parent whose child
  retains stdout. Unix descendant cleanup passed; Windows variants are in native CI.
- Migration of the original saved schema 1 demo without changing its file bytes.
- A varying synthetic fixture declining from 3/4 to 1/4 observed passes, with
  failure-rate/output classifications and explicit descriptive Wilson intervals.
- A CLI exact-trace fixture where both scenario runs passed but changed tool
  arguments/document IDs correctly caused comparison failure.
- `actionlint` 1.7.12 on all four workflows (shellcheck disabled because unavailable),
  and parsing of all workflow/composite-action YAML files.
- Release archive SHA-256, executable metadata/mode, reproducible tar/ZIP packaging,
  required-license/version checks, and execution of the extracted native release
  binary through `--version` and the three-scenario passing demo.

Current artifacts: `release/wraith-0.2.0-aarch64-apple-darwin.tar.gz` and its SHA-256
sidecar; `reports/sampled-comparison.json` and `reports/exact-trace-comparison.json`;
new `.wraith/runs/sampled-baseline.json` and `sampled-candidate.json`; varying fixture
snapshots under `examples/sampling-agent/.wraith/runs/`. Generated files are ignored.

The original temporary Rust directories below still apply. Rust 1.87.0 and a
Windows GNU standard-library target were added for checks. This machine's Python
shim selects an incompatible x86 Node on its internal PATH; adapter verification
used `WRAITH_DEMO_NODE=/home/developer/.nvm/versions/node/v22.19.0/bin/node` without editing
shell profiles. The demo script supports that override explicitly.

Native Linux/Windows execution and remote GitHub baseline/PR/release jobs have **not
run**. Windows MSVC packaging is defined in CI but was not built locally. No pushes,
tags, GitHub releases, or public distribution occurred. A chosen `LICENSE` is needed
for tag-triggered draft publication; private packaging includes an unlicensed notice.
There are no significance tests, instrumented real-provider/RAG pilots, signing,
redaction, or adversarial sandbox guarantees. The original v0.1 limitations below
are historical and are superseded where this section reports completed work.

## Initial v0.1 implementation (historical)

Verified locally on macOS arm64 on October 6, 2026. This is evidence for this
checkout, not a cross-platform release certification.

## Toolchain

The machine had no Rust toolchain on PATH. Rustup installed Rust 1.99.0, rustfmt,
and Clippy into temporary directories without editing shell profiles:

```sh
export CARGO_HOME=/private/tmp/wraith-cargo
export RUSTUP_HOME=/private/tmp/wraith-rustup
export PATH="$CARGO_HOME/bin:$PATH"
```

With those directories still present, the normal Cargo commands below work.
For a lasting development setup, use the [official Rust installation guide](https://rust-lang.org/tools/install/).
The declared Rust 1.85 minimum was not separately exercised.

Python 3 was available. Node 22.19.0 arm64 was used to run all JavaScript/TypeScript
adapters. An unrelated x86 Node on the escalated npm PATH caused an initial npm
failure; invoking the existing native Node and npm CLI by absolute path resolved it.
TypeScript 5.9.3 and Node type definitions were installed as development dependencies,
with scripts disabled during installation. The checked-in `agent.js` matches `tsc`
output; `dist/` and `node_modules/` remain ignored.

## Completed checks

```sh
cargo fmt --all
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked --offline -- -D warnings
cargo test --workspace --locked --offline
cargo build --workspace --locked --offline
git diff --check
```

All passed on the final source state: **15 Rust tests**, zero failures, zero ignored
tests. Coverage includes:

- Config field paths, unknown fields/versions, duplicate IDs, limits, command quoting.
- Missing text/usage, forbidden tools, required output/tools/sources, and budgets.
- Threshold equality, zero baselines, missing metrics, costs, and improvements.
- Compatible suites, new errors, warning-only differences, snapshot round-trip,
  inconsistent evaluation flags, safe names, and future run schemas.
- Missing executable, invalid/empty/multiple/oversized stdout, wrong response
  version/ID, token overflow, nonzero exit, large stderr, timeout, and Unix descendants.
- CLI init overwrite protection, scenario selection, named/path comparison,
  JSON parseability, saved failed runs, config-free comparison, and exit codes.

The TypeScript compiler completed with `strict: true` and `noEmitOnError: true`.
No model services were called.

## Exercised vertical slice

```sh
./target/debug/wraith --version
./target/debug/wraith run --save baseline
WRAITH_EXAMPLE_MODE=candidate ./target/debug/wraith run --save candidate
./target/debug/wraith compare baseline candidate
./target/debug/wraith compare baseline candidate --output json
```

Observed: version `0.1.0`; baseline 3/3 passes with exit 0; candidate 2/3 passes
with exit 1; comparison reports `PASS_TO_FAIL` and `TOOL_SELECTION_REGRESSION`
for `find-pto-policy`, with `search_documents` versus `web_search` and exit 1.
JSON comparison output parsed successfully and contained the expected classification.
Baseline and candidate snapshots remain in the ignored `.wraith/runs/` directory.

The same run/save/compare checks passed using `agent.js`, `agent.ts`, and
`dist/agent.js` with temporary configurations. Those temporary adapter snapshots
were removed with their temporary directories. No Wraith core changes were needed
when switching languages.

## Remaining limits

Windows process-tree cleanup, explicit Ctrl-C handling, detached descendants,
the declared minimum Rust version, and Linux/Windows builds were not verified here.
There is no statistical treatment of repeated stochastic runs, automatic redaction,
custom evaluator execution, hosted service, trace ingestion, replay, or Git integration.
The distribution license remains a founder decision before publication.
