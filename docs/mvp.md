# Original MVP

Historical context: v0.1 established the local run/save/compare loop. Current setup
uses [baseline and check](getting-started.md), and current priorities are in the
[roadmap](roadmap.md).

The original scope was a Rust CLI and core library with a strict YAML configuration,
one JSON subprocess invocation per scenario, deterministic expectations, saved
runs, and readable comparisons. The offline Python and TypeScript examples
exercised passing and deliberately failing agents.

## Decisions that still apply

- Compare the same inputs and expectations before and after a change.
- Treat unchecked differences as information; configured expectations determine failures.
- Keep provider SDKs, application state, tools, and pricing outside the core.
- Preserve unavailable usage instead of fabricating token or cost estimates.
- Keep artifacts local and report clear execution errors separately from regressions.

## Original acceptance workflow

From a source checkout with Python 3 and Rust installed:

```sh
cargo build --locked
./target/debug/wraith run --save baseline
WRAITH_EXAMPLE_MODE=candidate ./target/debug/wraith run --save candidate
./target/debug/wraith compare baseline candidate
```

The baseline passes; candidate and comparison exit 1 for the changed tool in
`find-pto-policy`. This synthetic acceptance test needs no model service.

Later versions add containment on Windows, cancellation, sampling, statistical
gates, structured JSON checks, function adapters, history, HTML reports, and CI.
See [architecture](architecture.md) for their current implementation.
