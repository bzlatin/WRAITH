# Verification record

## v0.5 increment — October 6, 2026

Package 0.5.0 adds guided function-adapter setup, `doctor`, immutable local workflow
history, shared live request budgets, HTML reports, reviewed case import, a CI setup
generator, and a checksum-verifying native installer. Protocol/config remain 1;
run/comparison schemas remain 4; project and workflow records use independent schema 1.

Verified locally on macOS arm64:

- 42 Rust tests and seven Python adapter/packaging/CI tooling tests passed.
- Formatting, Clippy with warnings denied, Rust 1.87 all-target checks, and locked
  debug/release builds passed.
- Python, JavaScript, direct TypeScript, compiled TypeScript, repeated-observation,
  and exact-trace demos passed with both passing and deliberately failing agents.
- RAG pilot: 21 comparisons, 0/213 false positives, 0/39 missed controlled regressions.
  These deterministic fixtures do not estimate live-model accuracy.
- Pinned official PydanticAI and LangGraph repositories were cloned locally. Their
  real orchestration passed three cases each; all six controlled tool-skipping
  regressions were detected. Mock model/tool boundaries used zero live model calls.
- Live workflow tests verified explicit opt-in, shared request exhaustion, reserved
  failed calls, and refusal to silently replace a failed experiment's request budget.
- The generated PR workflow and native release workflow passed actionlint. Dependency
  license notices remain current; no new Rust dependency versions were introduced.
- Native macOS arm64 archive metadata/checksums, extracted-binary init/run/compare,
  and atomic local installation passed. Bad checksums preserve an existing binary.
- HTML reports were inspected in Chrome at desktop 1440px and mobile 390px: failures
  precede performance, output disclosures work, and page width does not overflow.
  A malformed mobile capture was discarded and recaptured in a fresh context.
  The visual review was performed in-thread; see [report-design.md](report-design.md).

The local development pass made no additional live model requests or publication.
Subsequently, the owner authorized pushing v0.5 and making WRAITH public. The first
[native release matrix](https://github.com/bzlatin/WRAITH/actions/runs/37557996087)
passed on Linux x86_64, Apple Silicon/Intel macOS, and Windows x86_64 MSVC, including
extracted archive execution. The initial general CI run exposed a Windows workflow
fixture failure under its inherited three-second deadline; the state/evidence test
now uses a separate 30-second allowance and prints full failure diagnostics.
Dedicated timeout tests and the product's configured timeout remain unchanged.
Publication and installed-binary PR checks are recorded after completion below.
External pilots establish integration behavior, not natural bug discovery or adoption.


## v0.4 increment — October 6, 2026

Package 0.4.0 adds structured-output assertions for the Example application integration.
Protocol/config remain version 1; run/report schemas are 4 with in-memory migration
from schemas 1–3. This increment has been verified locally on macOS arm64; native
CI results below apply to v0.3, not these unpushed changes.

- 36 Rust tests passed, plus five packaging/CI tooling tests.
- Formatting, Clippy with warnings denied, Rust 1.87 all-target check, and locked
  release build passed. Python/TypeScript passing and failing adapter demos passed.
- Example application server type-check and 141 unit tests passed. The existing
  `upNextIntelligence` test needs a dummy localhost `DATABASE_URL` at import time;
  no real database was used. The three adapter tests pass without database config.
- The production generation body was moved verbatim into a shared module; the
  adapter exercises it without loading the database or fatigue-query modules.
- Ten offline baseline cases passed; harmless wording triggered 0/10 alarms;
  all 50 delivered-output mutations were detected. These are controlled fixtures.
- Four live baseline and four live candidate cases passed using 8 of 20 approved
  requests. Candidate added a concise-reasoning instruction. This is a smoke check,
  not a live false-positive-rate estimate or statistical equivalence result.
- The separate baseline/edit/candidate workflow was exercised offline: frozen suite,
  ten detected wrong-equipment failures, and refusal to overwrite the candidate.

The app's `server/evals/wraith/README.md` documents repeat use. Local evidence stays
under its ignored `server/.wraith/evals/` directory. The next validation is a useful
natural regression during a real change. No extra model requests, deployment,
release publication, or push occurred after the eight-request experiment.


## v0.5.0 release — October 6, 2026

The owner authorized publication and selected a public source repository. Tag
`v0.5.0` points to `90bd18db677db84b69253b0c56dcc93f8bf44e79`.

- The [tagged native matrix](https://github.com/bzlatin/WRAITH/actions/runs/37558689791)
  passed tests, builds, archive checksums, and extracted-binary smoke tests on Linux
  x86_64 GNU, Apple Silicon/Intel macOS, and Windows x86_64 MSVC.
- The [corrected general matrix](https://github.com/bzlatin/WRAITH/actions/runs/37558419597)
  and [tagged general matrix](https://github.com/bzlatin/WRAITH/actions/runs/37558689781)
  passed, including Windows workflow/tooling tests, MSRV, demos, and workflow lint.
- All four downloaded draft archives matched their checksum sidecars and binary
  metadata. The installer source matched after normalizing Windows line endings;
  the standalone attachment was replaced with the canonical LF copy. Future release
  jobs normalize this attachment before merging platform artifacts.
- [v0.5.0](https://github.com/bzlatin/WRAITH/releases/tag/v0.5.0) is published in the
  public repository. Anonymous installer download and checksummed installation to
  `~/.local/bin` passed on macOS arm64. The installed binary passed init, doctor,
  baseline, intentionally failing check, and passing check with no model calls.

Generated published-binary PR CI was bootstrapped with the existing offline RAG
suite. Both temporary PRs were tested without merging their agent modifications:

- [Harmless wording PR](https://github.com/bzlatin/WRAITH/pull/1): the
  [generated check](https://github.com/bzlatin/WRAITH/actions/runs/37559442806)
  passed. Output changes were informational; all configured expectations passed.
- [Controlled refund regression PR](https://github.com/bzlatin/WRAITH/pull/2): the
  [generated check](https://github.com/bzlatin/WRAITH/actions/runs/37559459123)
  failed with `OUTPUT_REGRESSION` and `PASS_TO_FAIL`. Neither version had execution
  errors. JSON comparisons and self-contained HTML reports were retained for both.
- The [bootstrap main build](https://github.com/bzlatin/WRAITH/actions/runs/37559351853)
  passed. The PR check downloaded v0.5.0 without authentication and evaluated each
  exact base/candidate pair with the base configuration and policy.

Main requires the GitHub Actions `check` context with branches up to date before
merging, including repository administrators. These fixtures validate distribution
and gating; they do not establish live-model quality or natural bug discovery.

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
