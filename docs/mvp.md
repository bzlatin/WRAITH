# Wraith v0.1

This is the original MVP definition. The implemented v0.2 additions are recorded in
[implementation-plan.md](implementation-plan.md), [sampling.md](sampling.md), and
[ci.md](ci.md); the core product boundary remains unchanged. The workflow below
is engineering acceptance; real-agent product validation is defined in
[product-direction.md](product-direction.md).

Wraith answers one question: did an agent change break behavior that worked before?
The deliverable is a local Rust executable and a reusable core library. A developer
defines a suite, runs two agent versions, and compares saved artifacts.

## Scope

- Rust 2024 workspace with `wraith-core` and `wraith-cli`.
- `init`, `run`, and `compare`; human and JSON reports.
- Versioned, strictly validated YAML configuration, protocol, and run artifacts.
- One subprocess per scenario, sequential execution, a whole-invocation deadline,
  bounded pipe capture, actionable errors, and Unix process group cleanup.
- Seven deterministic evaluator kinds: required/forbidden output substrings,
  required/forbidden tools, required sources, maximum latency, maximum tokens.
- Local named runs and comparison against names or JSON paths.
- Pass/fail transitions, evaluator regression classifications, new errors,
  tool/source differences, and output differences.
- Success-rate, mean latency, mean tokens, and mean reported cost thresholds.
- Offline synthetic Python and TypeScript examples, tests, and documentation.

## Architecture decisions

The proposed Rust core and subprocess boundary fit the product. The important
durable boundary is the normalized protocol, rather than any provider integration.
Two crates suffice: modules represent the execution, evaluation, storage, and
comparison boundaries without requiring a plugin system.

Changes alone do not prove degradation. A different tool or source is a warning;
a newly failing deterministic expectation is a failure. Saved comparisons require
the same inputs and expectations to avoid presenting suite changes as agent changes.
Single-run comparisons detect observed regressions; they do not establish statistical
significance for stochastic agents.

Cost is reported by the adapter, not estimated from provider pricing by the core.
Missing usage and cost remain missing. Configured thresholds fail closed if their
metrics cannot be calculated. No generic "tool accuracy" score is fabricated from
unlabelled traces.

## Implementation sequence

1. Define protocol, config, normalized models, and validation.
2. Implement bounded subprocess execution and deterministic evaluation.
3. Add versioned snapshots, compatible-suite comparison, and thresholds.
4. Wire the CLI and examples, then exercise faults and the complete demo.
5. Format, lint, test, build, and document remaining platform limits.

## Excluded

No hosted service, accounts, billing, dashboard, database, infrastructure, telemetry,
OTEL ingestion, trace replay, Git orchestration, provider SDKs, LLM judges, framework
integrations, Python/TypeScript SDKs, GitHub App/Action, enterprise policy language,
custom evaluator plugins, concurrent scheduler, or coding-agent benchmarks.
The starter example needs Python; Wraith itself has no Python/Node runtime dependency.

## Acceptance workflow

```sh
cargo build --locked
./target/debug/wraith run --save baseline
WRAITH_EXAMPLE_MODE=candidate ./target/debug/wraith run --save candidate
./target/debug/wraith compare baseline candidate
```

The baseline succeeds, the candidate exits 1, and comparison names
`find-pto-policy`, `TOOL_SELECTION_REGRESSION`, `search_documents`, and `web_search`.
No keys, network, or model services are needed after building.
