# Configuration reference

`wraith.yaml` defines execution and expectations. JSON is accepted as YAML.
`wraith.project.json` optionally declares onboarding language/entrypoint, offline or
live mode, a model label, and required environment variable **names**. Config version
is 1; project settings version is independently 1. Unknown fields fail validation.

```yaml
version: 1
agent:
  command: "python3 wraith_adapter.py agent.py:evaluate"
  timeout_ms: 30000
tests:
  - id: policy-answer
    input: {text: "How many PTO days?"}
    metadata: {fixtureVersion: 1}
    expect:
      output_contains: ["20"]
      output_not_contains: ["I don't know"]
      tools_called: [search_documents]
      tools_not_called: [delete_document]
      sources: {include: [employee_handbook]}
      latency_ms: {max: 5000}
      tokens: {max: 4000}
thresholds:
  success_rate: {regression: 0}
  latency: {max_increase_percent: 25}
comparison:
  tool_arguments: false
  document_ids: false
```

Agent paths and artifacts resolve from the config directory. Commands are quoted
argument lists executed directly; no shell expansion is performed. Every configured
expectation must pass for an observation to pass. With no expectations, valid
execution alone passes. Doctor warns about weak starter checks.

Text checks are case-sensitive substrings of a string output or `output.text`.
Missing text fails positive and negative checks. Tool checks count attempted calls,
even if reported unsuccessful; source checks inspect `retrievals[].source`.
Missing usage fails token limits. Latency includes process startup and cleanup.
Structured fields use [JSON pointer assertions](structured-output.md).

Suite thresholds compare recorded means: success-rate decline is percentage points;
latency/tokens/cost increases are relative percent. Missing metrics cannot pass a
configured threshold. Exact traces and sampled comparisons are documented in
[sampling](sampling.md) and [statistical gating](statistical-gating.md).

Use `wraith config` to export validated config as JSON. Use `--config path` on any
command for a separate suite. Low-level `run --save` and `compare` remain supported
for custom adapters and automation; the [guided workflow](getting-started.md) adds
baseline lifecycle and local history without changing the evaluation engine.
