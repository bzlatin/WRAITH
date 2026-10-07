# Try Wraith on an agent change

## Five-minute demo

[Install Wraith](install.md) and Python 3.10+. Run these commands in a new, empty directory:

```sh
wraith init --demo
wraith doctor
wraith baseline
wraith check
```

Both runs should pass. Now introduce the demo's deliberate tool-selection defect.
On macOS/Linux:

```sh
WRAITH_EXAMPLE_MODE=candidate wraith check
```

On Windows PowerShell:

```powershell
$env:WRAITH_EXAMPLE_MODE = 'candidate'
wraith check
Remove-Item Env:WRAITH_EXAMPLE_MODE
```

The check exits **1** because the candidate uses `web_search` where the scenario
requires `search_documents`. Open the printed `.wraith/index.html` path in a browser
and select the failing check. Inspect its expected tool, observed tool, and outputs.
Run `wraith check` with the override removed: it passes against the same baseline.
This synthetic demo teaches the workflow without API keys or model calls.

## Test a retrieval change

From a source checkout, build with `cargo build --release --locked`. The following
macOS/Linux commands use an offline RAG agent that retrieves from a small corpus:

```sh
python3 examples/rag-agent/agent.py --ask "What is the refund policy?"
./target/release/wraith --config examples/rag-agent/wraith.yaml run --save baseline
WRAITH_RAG_VARIANT=stale-policy ./target/release/wraith --config examples/rag-agent/wraith.yaml run --save candidate
./target/release/wraith --config examples/rag-agent/wraith.yaml compare baseline candidate
```

The answer should initially contain `30 days` and `[source:refund-current]`. The
candidate retrieves an archived 90-day policy; its run and comparison exit **1**.
The report shows changed answers, sources, and failed expectations. Other defects
are `missing-acl`, `wrong-route`, and `missing-citation`.

Try a harmless wording change against the same baseline:

```sh
WRAITH_RAG_VARIANT=benign-wording ./target/release/wraith --config examples/rag-agent/wraith.yaml run --save harmless
./target/release/wraith --config examples/rag-agent/wraith.yaml compare baseline harmless
```

Both commands pass. The output difference remains visible. `benign-order` and
`benign-ranking` demonstrate other allowed changes. Use `compare ... --html report.html`
for an HTML report or `--output json` for automation. Named runs resolve relative to
the configuration directory; use distinct names for suites sharing that directory.

On Windows, use `target\release\wraith.exe`, change the fixture command to `python`
if needed, and set variants using `$env:WRAITH_RAG_VARIANT = 'stale-policy'`.
Remove the variable before baseline runs.

To reproduce the controlled pilot:

```sh
python3 scripts/pilot.py --binary ./target/release/wraith --repeats 3
```

Results appear under `reports/rag-pilot/`. The recorded run found 0/213 false alarms
and 0/39 missed injected failures across 21 comparisons. These deterministic
fixtures verify checks; they do not estimate live-model accuracy.

## Try statistical decisions

The offline statistical fixture requires at least 100 samples per version:

```sh
./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 20 --save small-baseline
./target/release/wraith --config examples/rag-agent/statistical.yaml run --samples 20 --save small-candidate
./target/release/wraith --config examples/rag-agent/statistical.yaml compare small-baseline small-candidate
```

Comparison exits **3 (inconclusive)**. For a separate experiment, repeat with 200
samples and distinct run names. A `benign-wording` candidate passes; a `stale-policy`
candidate fails. The fixture's 20-point allowance is deliberately large for a quick
demo. Choose tolerances and sample counts before testing your own agent; read
[statistical gating](statistical-gating.md) for the method and limitations.

## Use a real task

1. [Connect your agent](getting-started.md) and define three to ten reviewed cases.
2. Record actual tool/retrieval activity and meaningful output expectations.
3. Save a baseline, change one prompt, model, tool, or retrieval setting, and check it.
4. Review failures before adjusting expectations. Was the change harmful, intentional,
   or too variable for the selected gate?
5. Keep useful cases and repeat the check on your next change. Record missed failures,
   false alarms, and setup friction; this is more useful than growing the suite blindly.

The [upstream examples](../examples/external-agents/README.md) exercise real PydanticAI
and LangGraph orchestration offline. Your own live agent requires explicit opt-in
and a shared request budget. Once offline checks are useful, [add PR CI](ci-setup.md).
