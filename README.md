# WRAITH

**Catch agent regressions before they ship.**

Wraith replays the same scenarios against different versions of your AI agent and
shows what changed. It runs locally, saves JSON artifacts, and returns exit codes
for CI. The Rust core is framework neutral; your agent implements a small JSON
subprocess protocol in any language.

This is a local v0.2 implementation with deterministic checks. No model API,
Wraith account, hosted service, or telemetry is involved.

## Build and try the regression demo

Requires Rust 1.87+ (2024 edition). The synthetic Python demo requires Python 3.
Wraith itself compiles to one executable without a Python or Node dependency.

```sh
cargo build --locked
./target/debug/wraith --version
./target/debug/wraith run --save baseline
WRAITH_EXAMPLE_MODE=candidate ./target/debug/wraith run --save candidate
./target/debug/wraith compare baseline candidate
```

The baseline passes all three scenarios. The candidate deliberately replaces
`search_documents` with `web_search` in `find-pto-policy`; its run and comparison
exit **1**, as expected. Comparison includes:

```text
find-pto-policy: TOOL_SELECTION_REGRESSION
  Baseline: ["search_documents"]
  Candidate: ["web_search"]
  tool "search_documents" must be called

RESULT: FAILED — REGRESSION DETECTED
```

The environment variable affects only the synthetic examples. Your own agent
chooses how to select a version. On PowerShell, set `$env:WRAITH_EXAMPLE_MODE =
"candidate"` before the candidate run and remove it afterward.

## Start a project

Install the binary on your PATH with `cargo install --path crates/wraith-cli --locked`,
then run from an empty project directory:

```sh
wraith init
wraith run --save baseline
wraith run --scenario find-pto-policy
wraith run --samples 10 --save sampled-baseline
```

`init` creates `wraith.yaml`, a synthetic `wraith_agent.py`, and `.wraith/runs/`.
It refuses to overwrite starter files. Replace the agent command and scenarios
with your application. Add `.wraith/` to your project's `.gitignore`.

## Configuration

```yaml
version: 1
agent:
  command: "python3 ./agent.py"
  timeout_ms: 30000
tests:
  - id: find-pto-policy
    input:
      text: "How many PTO days do employees receive?"
    expect:
      output_contains: ["20"]
      output_not_contains: ["I don't know"]
      tools_called: [search_documents]
      tools_not_called: [delete_document]
      sources:
        include: [employee_handbook]
      latency_ms:
        max: 5000
      tokens:
        max: 4000
thresholds:
  success_rate:
    regression: 0
  latency:
    max_increase_percent: 25
  tokens:
    max_increase_percent: 30
  cost:
    max_increase_percent: 20
```

The default configuration is `wraith.yaml`; use `--config path/to/wraith.yaml`
for another file. Agent paths and named artifact paths are relative to that file's
directory. Commands support quoted arguments and launch directly without shell
expansion. Environment variables are inherited, never enumerated or saved.

Unknown YAML fields, duplicate IDs, unsupported versions, contradictory checks,
and invalid limits are rejected. Every expectation runs; every expectation must
pass. A valid execution with no expectations passes. Text checks are case-sensitive
substrings of a string output or `output.text`. Tool presence counts attempted calls,
including ones whose `success` is false. Required sources match `retrievals[].source`.

## Agent protocol

Wraith starts one process per scenario observation, sends a JSON line to stdin, closes stdin,
and expects one JSON response before exit. Logs go to stderr.

```json
{"protocolVersion":1,"scenarioId":"find-pto-policy","input":{"text":"How many PTO days?"},"metadata":{}}
```

Minimal response:

```json
{"protocolVersion":1,"scenarioId":"find-pto-policy","output":{"text":"Employees receive 20 PTO days."}}
```

Add normalized tool calls, retrievals, token usage, and reported cost to enable
those checks. See the complete [protocol contract](docs/protocol.md).

## Saved runs and comparison

```sh
wraith run --save baseline --output json
wraith compare baseline candidate
wraith compare baseline ./candidate.json --output json
```

Named snapshots live in `.wraith/runs/<name>.json`; saving the same name replaces
it atomically. Failed runs are saved too. JSON stdout contains only the structured
result; setup errors go to stderr. Comparison needs no agent execution or YAML
contents, and uses thresholds stored in the candidate snapshot.

Both runs must contain the same IDs, inputs, metadata, expectations, and sample count.
Reordered suites work; changed suites require a fresh baseline. New failed checks and
pass-to-fail transitions fail comparison. Fail-to-pass transitions are improvements.
Tool/source differences without failing checks produce warnings. Output differences
are informational. Thresholds check suite means; success-rate declines use percentage
points, other metrics use relative percentage increases. Zero-to-positive exceeds
any finite allowance. Missing usage/cost is unavailable, and fails a configured
threshold instead of being interpreted as zero. Thresholds do not override individual
behavior regressions. Repeated runs report observed rates and descriptive
intervals. Opt-in [statistical gating](docs/statistical-gating.md) adds minimum samples,
effect-size allowances, simultaneous bounds, and inconclusive results.
An unchanged behavioral failure already present in the baseline is not a new
regression; `run` still exits 1 for it. Any candidate execution error exits 2.

| Exit | Meaning |
|---|---|
| 0 | Evaluation/comparison passed |
| 1 | Failed expectations or detected regression/threshold failure |
| 3 | Statistical comparison is inconclusive; blocks CI |
| 2 | Configuration, artifact, execution, timeout, or protocol failure |
| 130 | Interrupted run; children cleaned up and no partial snapshot saved |

## Exact behavior checks and repeated runs

Opt into exact behavior comparison in the candidate configuration:

```yaml
comparison:
  tool_arguments: true
  document_ids: true
```

These gates compare tool names with complete JSON arguments, and retrieval source
with document IDs. They ignore object-key/call/retrieval ordering and preserve
multiplicity and per-invocation trace boundaries. Changed traces fail comparison.
Missing arguments or document IDs fail an enabled check with
`INSTRUMENTATION_MISSING`; no calls/retrievals is a valid empty trace.

```sh
wraith run --samples 10 --save baseline
# Change the agent version, retaining the same scenario suite.
wraith run --samples 10 --save candidate
wraith compare baseline candidate
```

Each sample starts a fresh agent process with the same input and metadata. Counts
must match. Comparison aggregates scenario and evaluator failures instead of pairing
sample indices across independent runs. Any observed failure-rate increase gates
strictly; the report includes Wilson 95% pass-rate intervals as a description under
binomial independence assumptions, not a significance test. Exact trace checks
also gate distribution changes when explicitly enabled. Read the
[sampling contract](docs/sampling.md) before using stochastic agents in CI.

Run the varying offline fixture with `--config examples/sampling-agent/wraith.yaml`
and `--samples 4`: its baseline passes 3/4, candidate passes 1/4, and both `run`
commands exit 1 because each contains a failed observation.

New runs use schema 3. Schema 1 artifacts migrate on load into one-sample runs;
schema 2 artifacts retain strict comparison semantics after migration;
original files remain untouched.

## CI and releases

The [local composite action](.github/actions/wraith/action.yml) wraps a prebuilt
binary and preserves exits. [Baseline](.github/workflows/baseline.yml) and
[PR regression](.github/workflows/regression.yml) workflows store runs for exact
base commits and enforce the base configuration during comparison:

```sh
wraith compare ./baseline.json candidate --policy ./trusted/wraith.yaml --output json
```

`--policy` validates the entire trusted suite and applies its comparison options and
thresholds, including when a candidate snapshot relaxed them. CI code execution uses
read-only tokens and no provider secrets. The adapters and workspace still run with
host permissions; this is not an adversarial sandbox.

The [build matrix](.github/workflows/ci.yml) covers Linux, macOS, and Windows, plus
MSRV and workflow linting. The [release workflow](.github/workflows/release.yml)
packages four native targets with checksums. Manual dispatch produces build artifacts;
a version tag creates a draft release after checks and requires an owner-selected
`LICENSE`. No release was published during implementation. See [CI and release
setup](docs/ci.md) for bootstrap, retention, and licensing details.

Private packaging from a local release build:

```sh
cargo build --release --locked
python3 scripts/package-release.py --binary ./target/release/wraith \
  --target aarch64-apple-darwin
```

Use the actual target triple for your build. Python is a packaging/CI convenience,
not a runtime dependency of the distributed executable.

## Python and TypeScript examples

The default configuration uses [the Python agent](examples/python-agent/agent.py).
To use [the TypeScript agent](examples/typescript-agent/agent.ts), set:

```yaml
agent:
  command: "node examples/typescript-agent/agent.ts"
```

Node 22.18+ runs this erasable TypeScript source directly. For older Node versions,
use the adjacent equivalent `agent.js` (ES modules; Node 18+), or compile TypeScript:

```sh
cd examples/typescript-agent
npm install
npm run build
```

Then configure `node examples/typescript-agent/dist/agent.js` from the repository
configuration. These examples have no runtime packages or API keys. The optional
TypeScript build uses development packages only.

## Development

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --workspace --locked
python3 -m unittest discover -s scripts/tests -v
python3 scripts/demo.py  # after compiling the TypeScript example
```

Integration tests require Python 3. The core tests cover validation, evaluators,
threshold edges, serialization, compatibility, subprocess faults, and contained descendant
cleanup. CLI tests exercise initialization, saved comparisons, JSON, filtering,
and exit codes. Build dependencies require network access once; execution and tests
use synthetic local agents.

## Data and process boundaries

Wraith uploads nothing and does not persist environment variables. Artifacts can
contain sensitive inputs, outputs, metadata, tool arguments, and error diagnostics.
Keep them local and manage retention. There is no redaction system yet.

The subprocess runner is not a security sandbox. Unix process-group cleanup covers
ordinary descendants; detached sessions can escape it. Windows uses a Job Object
assigned before the agent resumes, covering its
descendants. Ctrl-C cancels execution, waits for direct-child cleanup, and exits 130.
Hard-killing Wraith prevents Unix drop guards from running. Windows and Linux runtime tests execute on native CI hosts. The release workflow
checksums, extracts, and smoke-tests each platform archive before retaining it.

Read [MVP scope](docs/mvp.md), [architecture decisions](docs/architecture.md), and
the [directional roadmap](docs/roadmap.md). The [verification record](docs/verification.md)
includes exercised commands and this session's temporary toolchain setup.
Hosted features, provider integrations,
OTEL ingestion, replay, and SDKs are intentionally deferred.

## License

Wraith is licensed under [Apache-2.0](LICENSE). Dependencies retain their own
licenses; see [third-party notices](THIRD_PARTY_LICENSES.txt). Native archives include
the license and notices. See [manual dogfooding](docs/dogfooding.md) for a realistic
RAG pilot and [statistical gating](docs/statistical-gating.md) for uncertainty-aware checks.

The offline RAG pilot covers 12 scenarios, three benign changes, and four deliberate
defects. Run `python3 scripts/pilot.py` after building, or follow the
[step-by-step dogfooding guide](docs/dogfooding.md).
