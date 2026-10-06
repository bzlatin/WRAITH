# Manually dogfood Wraith

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

1. Create a new directory with `wraith --config /path/to/project/wraith.yaml init`.
2. Replace the starter command with an adapter for your real agent. Read one JSON
   request from stdin, invoke your agent, and write one JSON response to stdout.
   Keep logs on stderr. See [protocol.md](protocol.md) and the Python/TypeScript examples.
3. Define representative inputs and expected behavior from real tasks. Preserve
   identical scenarios, metadata, and expectations across both versions.
4. Save a baseline; change one prompt, model, tool, or retrieval setting; save a
   candidate; compare. Restore the old agent and rerun if a finding looks noisy.
5. Record useful catches, missed failures, false alarms, setup time, and whether you
   would run this again. Repeat-use evidence is the next product milestone.

Supply provider credentials through your usual environment only when testing your
own live agent. Account for each scenario/sample invoking it again. Keep live provider
calls out of untrusted PR workflows. Do not change assertions simply to silence a
valid regression; intentional suite changes require a refreshed baseline.

Windows: use `target\release\wraith.exe`, change `python3` to `python` in the fixture
configuration if needed, and set variants with `$env:WRAITH_RAG_VARIANT='stale-policy'`
in PowerShell. Remove the override with `Remove-Item Env:WRAITH_RAG_VARIANT` before
baseline runs. The automated pilot selects the current Python interpreter itself.
