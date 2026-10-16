# Wraith

**Catch incomplete AI search indexes before they go live.**

AI applications search small pieces of your documents, called chunks. Wraith checks
that a loading job stored the chunks it promised, at the intended versions. The
example workflow keeps the previous index selected when the new one fails its check.
It runs locally and produces reports and exit codes for your existing workflow.

| Workflow | Availability |
| --- | --- |
| Verify ingestion manifests against a serving index | Experimental source build |
| Run fixed agent scenarios and compare changes | Released in v0.5.0 |

## Verify an ingestion job

A successful job can leave missing chunks, outdated revisions, or data that should
have been deleted. `wraith index check` compares intended chunk IDs and revisions
with the actual index export. Findings name the document, affected chunks, and job.
Incomplete exports and unfinished ingestion return an inconclusive result.

From this source checkout, with Rust 1.87+:

```sh
cargo run --locked -p wraith-cli -- index check \
  --manifest examples/index-audit/manifest.jsonl \
  --inventory examples/index-audit/partial.jsonl
```

Expect exit 1: chunk `1` is missing. Replace `partial.jsonl` with `complete.jsonl`
to see a passing check. Add `--html .wraith/ingestion/report.html` for a local report.
This example needs no database, Python, API key, or model calls.

Use the check after ingestion or before promoting a new index generation. It needs
an authoritative manifest created before writes and consistent exports. It does
not judge answer quality or automatically repair data.
[Try the LlamaIndex document-search workflow](docs/verified-ingestion.md) ·
[Connect Qdrant or another index](docs/index-audit.md) ·
[Inspect recovery and old indexes](docs/ingestion-operations.md) ·
[Research and current limits](docs/index-product-decision.md).

## Check an agent change

The released workflow runs the same scenarios before and after a prompt, model,
tool, or retrieval change. Reports show failed expectations, both outputs, and
recorded activity. You define what must stay correct; harmless output differences
remain visible without failing the gate.

Download [install.py](https://github.com/bzlatin/WRAITH/releases/download/v0.5.0/install.py),
then install the native binary and try the offline demo in an empty directory:

```sh
python3 install.py --version 0.5.0
# Add the printed installation directory to PATH.
wraith init --demo
wraith doctor
wraith baseline
wraith check
```

Open `.wraith/index.html`. The demo needs Python 3.10+ and no API key. Native packages
support macOS, Linux, and Windows; use `python` on Windows.
[Installation](docs/install.md) · [Try a deliberate failure](docs/dogfooding.md).
**The published v0.5.0 binary does not include `index check`.**

Connect Python or TypeScript functions with `wraith init --entrypoint agent.py:evaluate`,
or another language through the JSON subprocess protocol. Review the generated
inputs and expectations, save a baseline, then use `wraith check` during changes.
The baseline stays fixed until explicitly replaced.
[Integration guide](docs/getting-started.md) · [Offline PR checks](docs/ci-setup.md).

## Evidence and privacy

The LlamaIndex/Qdrant example blocks incomplete candidate indexes and inspects
recovery evidence without deleting data. A repeated-update comparison used public
CPython documents: Wraith and plain reconciliation made matching decisions in all
14 steps per checker. This supports the integration's technical utility; the study
did not establish an additional operational benefit from the Rust checker.
[An upstream LlamaIndex recipe](docs/upstream-ingestion.md) also passed four normal
transitions with both checkers, using a public transformation hook. Wraith remains
an optional local utility; commercial expansion is paused pending a concrete advantage.
[Results and limits](docs/repeated-ingestion.md) · [Recovery](docs/ingestion-operations.md) · [Tool comparison](docs/index-product-decision.md).

Earlier agent studies demonstrated configured regression detection, without proving
a workflow advantage over ordinary tests. Repeat adoption and paid demand remain
unvalidated. [Product assessment](docs/product-assessment.md).

Wraith uploads nothing and collects no telemetry. Your agent or configured database
exporter may contact services. Reports can contain application data; keep `.wraith/`
ignored and review artifacts before sharing. No account is required.

## Documentation

[All guides](docs/README.md) · [Ingestion verification](docs/index-audit.md) ·
[Agent configuration](docs/configuration.md) · [Structured checks](docs/structured-output.md) ·
[Statistical gates](docs/statistical-gating.md) · [Protocol](docs/protocol.md) ·
[Contribute](CONTRIBUTING.md) · [Report a bug](https://github.com/bzlatin/WRAITH/issues).

Apache-2.0. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_LICENSES.txt).
