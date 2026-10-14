# Wraith

**Regression tests for AI agents.**

A prompt, model, tool, or retrieval change can fix one task and break another.
Wraith runs the same scenarios before and after a change, then shows what stopped
passing and why. Use it locally during development and on pull requests.

Connect Python or TypeScript functions, or other languages through a JSON subprocess
protocol. No Wraith account or hosted service is required.

## What you can catch

| Change | Check |
| --- | --- |
| Approval handling changes | A denied action does not execute |
| A prompt skips a required lookup | The expected tool was called |
| Retrieval starts returning an outdated policy | The answer contains the current value and cites the expected source |
| Generated JSON breaks an application contract | Required fields, allowed IDs, item counts, uniqueness, and numeric ranges |
| A change increases resource use | Recorded latency, token usage, or reported cost stays within your limits |

Reports show failed expectations, baseline/candidate outputs, and recorded activity.
Harmless output differences stay visible without failing the gate. Wraith checks
your expectations; it does not automatically judge answer quality.

## Tested with evidence

- **A real approval regression:** reproduced a historical upstream bug where an
  unapproved action ran after resuming saved history. Wraith failed the buggy
  revision and passed the fix. [Reproduction](docs/historical-pilot.md).
- **A partial fix exposed another failure:** in pinned smolagents source, Wraith
  flagged new crashes in two scenarios while the selected upstream tests passed.
  Those scenarios already failed other requirements. Combined local fixes
  passed 9/9 contracts. [Reproduction and test overlap](docs/maintained-agent.md).
- **Measured workflow cost:** a 16-case offline baseline/candidate comparison took
  4.96 seconds median with four jobs, versus 14.03 seconds sequentially, on the
  tested Mac. Installation and build time are excluded.
  [Workflow study and limits](docs/workflow-value.md).

These are scoped engineering results, not production accuracy or measured customer ROI.

## Try it in five minutes

Download [install.py](https://github.com/bzlatin/WRAITH/releases/download/v0.5.0/install.py)
and install the native binary:

```sh
python3 install.py --version 0.5.0
```

Add the printed directory to PATH. In an empty directory:

```sh
wraith init --demo
wraith doctor
wraith baseline
wraith check
```

Open `.wraith/index.html` in your browser. The demo needs Python 3.10+ and no API
key. Native packages support macOS, Linux, and Windows without Rust. On Windows,
use `python` instead of `python3`. [Installation details](docs/install.md) ·
[Try a deliberate failure](docs/dogfooding.md).

## Use your own agent

Export a function accepting `(input, context)` and returning JSON:

```sh
wraith init --entrypoint agent.py:evaluate
# TypeScript: wraith init --entrypoint agent.ts:evaluate
```

Review the generated inputs and expectations, then:

```sh
wraith doctor
wraith baseline
# Change your prompt, model, tools, or retrieval.
wraith check
```

Each completed run saves JSON evidence and an HTML report. The baseline stays fixed
until `wraith baseline --replace`. A passing comparison can retain existing baseline
failures; reports show them. Start with a few real tasks.
[The integration guide](docs/getting-started.md) covers examples, instrumentation,
and live model calls. The current source build adds
[reviewed initialization and typed case-authoring flags](docs/first-use.md), plus
[native CI comparisons and offline parallel jobs](docs/workflow-value.md).

## Add it to your workflow

`wraith ci init` generates an offline GitHub PR check against the exact base commit
and its policy. Bootstrap your suite and review dependency setup first.
[CI setup](docs/ci-setup.md).

Use [sampling and statistical gates](docs/statistical-gating.md) for variable outputs.
Inconclusive results block CI. Live runs require opt-in; budgets count instrumented
attempts, including failures, but cannot cap hidden SDK retries.

Wraith uploads nothing and collects no telemetry. Your agent may contact services;
outputs and diagnostics may contain application data. Keep `.wraith/` ignored and
review reports before sharing them.

## Documentation and examples

[Documentation](docs/README.md) · [Configuration](docs/configuration.md) ·
[Structured checks](docs/structured-output.md) · [Protocol](docs/protocol.md)

Try the offline [RAG fixture](docs/dogfooding.md#test-a-retrieval-change) or the
[pinned PydanticAI and LangGraph examples](examples/external-agents/README.md).
[Contribute](CONTRIBUTING.md) · [Report a bug](https://github.com/bzlatin/WRAITH/issues).

Apache-2.0. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_LICENSES.txt).
