# Manually dogfood Wraith

## Five-minute check with the new workflow

The current checkout already has a built native binary. These macOS commands create
an isolated offline demo; no API key or model request is needed:

```sh
WRAITH_BIN=/Users/ben/coding_projects/WRAITH/target/release/wraith
WRAITH_DEMO_DIR=$(mktemp -d)
cd "$WRAITH_DEMO_DIR"
"$WRAITH_BIN" init --demo
"$WRAITH_BIN" doctor
"$WRAITH_BIN" baseline
WRAITH_EXAMPLE_MODE=candidate "$WRAITH_BIN" check
open .wraith/index.html
```

The check intentionally exits 1: the candidate uses `web_search` where the scenario
requires `search_documents`. Open the latest check from the history page, expand
its outputs and traces, and inspect expected versus observed tool use. Next run
`"$WRAITH_BIN" check` without the override: it should pass against the same baseline.
This demo is synthetic; it teaches the workflow.

To try actual upstream orchestration, return to the Wraith repository and follow
[the external pilot](../examples/external-agents/README.md). Both cloned examples
already ran locally, with all six controlled regressions detected. To connect your
own application, use [the function integration guide](getting-started.md). Start with
three to ten reviewed cases and one real prompt/tool change; record useful catches
and false alarms before adding more checks. `wraith ci init` generates offline PR CI
once an accessible native release is published.

## Explore the RAG fixture

Run these commands from the repository root on macOS/Linux with Python 3 and Cargo
available. The fixture uses actual corpus retrieval and extractive answers without
network calls or model charges. On this development machine, if Cargo is absent:

```sh
export CARGO_HOME=/private/tmp/wraith-cargo
export RUSTUP_HOME=/private/tmp/wraith-rustup
export PATH="$CARGO_HOME/bin:$PATH"
```

For a permanent Rust installation, use your normal toolchain; the temporary paths
above are specific to the development session.

## 1. Build and ask the agent a question

```sh
cargo build --release --locked
./target/release/wraith --version
python3 examples/rag-agent/agent.py --ask "What is the refund policy?"
```

Expect `30 days` and `[source:refund-current]`. Inspect `corpus.json` and `agent.py`
in `examples/rag-agent`. The agent ranks corpus text, filters archived/private docs,
routes order queries to a lookup tool, and escalates questions lacking evidence.
It never reads the scenario ID to decide an answer.

## 2. Save good behavior, then introduce a defect

```sh
./target/release/wraith --config examples/rag-agent/wraith.yaml run --save baseline
WRAITH_RAG_VARIANT=stale-policy ./target/release/wraith --config examples/rag-agent/wraith.yaml run --save candidate
./target/release/wraith --config examples/rag-agent/wraith.yaml compare baseline candidate
```

Baseline exits 0. Candidate and comparison intentionally exit 1. The refund cases
should show 30 days becoming 90 days, obsolete evidence, and failed expectations.
Runs are saved even when expectations fail. Read the report before changing anything.
Other defects: `missing-acl`, `wrong-route`, and `missing-citation`.

Then try a harmless change:

```sh
WRAITH_RAG_VARIANT=benign-wording ./target/release/wraith --config examples/rag-agent/wraith.yaml run --save harmless
./target/release/wraith --config examples/rag-agent/wraith.yaml compare baseline harmless
```

Both exit 0. Output differences are visible while the behavior checks still pass.
Also try `benign-order` and `benign-ranking`, or edit the actual retrieval code.

## 3. Reproduce the measured pilot

```sh
python3 scripts/pilot.py --binary ./target/release/wraith --repeats 3
```

This runs isolated temporary fixtures and writes `reports/rag-pilot/summary.json`
plus one report per variant. Prespecified labels are in `pilot-cases.json`.
The first local run measured 0/213 false positives and 0/39 missed regressions across
21 comparisons. Repeated deterministic checks test stability; these are not independent
LLM trials or production estimates. The script fails if either count becomes nonzero.

## 4. Exercise inconclusive, pass, and regression decisions

```sh
./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 20 --save small-baseline
./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 20 --save small-candidate
./target/release/wraith --config examples/rag-agent/statistical.yaml compare small-baseline small-candidate
```

Comparison exits **3 / INCONCLUSIVE** because each version needs at least 100 samples.
For a separate, fixed-size experiment:

```sh
./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 200 --save stats-baseline
WRAITH_RAG_VARIANT=benign-wording ./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 200 --save stats-harmless
./target/release/wraith --config examples/rag-agent/statistical.yaml compare stats-baseline stats-harmless
WRAITH_RAG_VARIANT=stale-policy ./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 200 --save stats-broken
./target/release/wraith --config examples/rag-agent/statistical.yaml compare stats-baseline stats-broken
```

The harmless comparison passes; the broken comparison fails. This demonstrates the
policy mechanics on a deterministic fixture. The 20-point allowance is deliberately
large for a quick demo; choose your own tolerance before testing a stochastic agent.
Read [statistical-gating.md](statistical-gating.md) for the method and limitations.

Append `--output json` to a comparison and redirect stdout to a file for inspection.
To enforce a reviewed policy, append `--policy examples/rag-agent/statistical.yaml`.
Named runs resolve relative to the configuration directory; different configurations
in the same directory share `.wraith/runs`, so use distinct names as above.

## 5. Connect your own agent

1. Export a Python/TypeScript function accepting `(input, context)` and returning JSON.
2. Run `wraith init --entrypoint agent.py:evaluate` (or `agent.ts:evaluate`) beside
   your app. Use its runtime/virtualenv and review `wraith doctor` diagnostics.
3. Define representative inputs and expected behavior from real tasks. Record actual
   tool/retrieval activity using the supplied context helpers.
4. Run `wraith baseline`; change one prompt, model, tool, or retrieval setting; run
   `wraith check`. Inspect the HTML report and compare the output evidence.
5. Record useful catches, missed failures, false alarms, setup time, and whether you
   would run this again. See [getting-started.md](getting-started.md) for live request
   opt-in/budgets and importing reviewed cases from recorded failures.

Supply provider credentials through your usual environment only when testing your
own live agent. Account for each scenario/sample invoking it again. Keep live provider
calls out of untrusted PR workflows. Do not change assertions simply to silence a
valid regression; intentional suite changes require a refreshed baseline.

Windows: use `target\release\wraith.exe`, change `python3` to `python` in the fixture
configuration if needed, and set variants with `$env:WRAITH_RAG_VARIANT='stale-policy'`
in PowerShell. Remove the override with `Remove-Item Env:WRAITH_RAG_VARIANT` before
baseline runs. The automated pilot selects the current Python interpreter itself.
