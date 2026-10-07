# Wraith

**Catch AI agent regressions before they ship.**

Wraith runs the same scenarios before and after an agent change, checks the results,
and explains what broke. Use it locally while editing prompts, tools, retrieval,
or model configuration, then run the same checks in CI.

## Quick start

This checkout is v0.5 development. Native packages and a checksum-verifying installer
are prepared; v0.5 has not been published yet. To use this checkout:

```sh
cargo install --path crates/wraith-cli --locked
mkdir wraith-demo && cd wraith-demo
wraith init --demo
wraith doctor
wraith baseline
wraith check
```

The demo is offline and requires Python 3. [Manual testing guide](docs/dogfooding.md). Build requires Rust 1.87+; a native release
needs no Rust installation. See [installation](docs/install.md) for packaged binaries.

## Connect your agent

Export a Python or TypeScript function that accepts `(input, context)` and returns
JSON. Wraith supplies the adapter; your application owns its dependencies.

```sh
wraith init --entrypoint agent.py:evaluate
# TypeScript: wraith init --entrypoint agent.ts:evaluate
```

Edit the generated scenarios to define correct behavior, then:

```sh
wraith doctor
wraith baseline
# Change your agent
wraith check
wraith report
```

Each check saves a local HTML report and JSON evidence. Reports show failed
expectations, baseline/candidate outputs, recorded usage, and run history. The
baseline remains fixed until you deliberately refresh it with `baseline --replace`.
See [the integration guide](docs/getting-started.md) for function examples and live budgets.

## What it checks

- Structured fields, allowed values, counts, uniqueness, and numeric ranges.
- Required or forbidden tools, expected retrieval sources, and optional exact traces.
- Recorded latency, tokens, and estimated cost when your adapter supplies them.
- Repeated observations, with optional statistical gates and explicit inconclusive results.

Wraith checks your expectations; it does not automatically judge whether an answer
is correct. Starter checks need review. A single live run is a smoke check, and live
request caps cover calls instrumented through the adapter helpers.

## CI and examples

`wraith ci init` creates an offline PR workflow that evaluates the exact base commit
and candidate, then retains reports. Review its dependency step and publish the
pinned Wraith version before enabling it. [CI guide](docs/ci-setup.md).

The [external pilot](examples/external-agents/README.md) clones pinned PydanticAI and
LangGraph examples and tests their actual orchestration with offline dependencies.
The Push / Pull integration exercises a real application's workout pipeline.

Runs stay local by default. No Wraith account, hosted service, or telemetry is required.
Inputs, outputs, and diagnostics may contain application data; keep `.wraith/` ignored.

[Configuration](docs/configuration.md) · [Structured checks](docs/structured-output.md) ·
[Statistical gates](docs/statistical-gating.md) · [Protocol](docs/protocol.md) ·
[Architecture](docs/architecture.md) · [Verification](docs/verification.md)

Apache-2.0. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_LICENSES.txt).
