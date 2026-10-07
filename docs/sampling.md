# Sampling and exact behavior comparison

`wraith run --samples N` runs 1–1000 observations for each selected scenario.
Each observation has a new contained process and identical request input/metadata.
The adapter owns external state and randomness. Wraith does not inject a seed or
silently alter user metadata. Execution remains sequential.

Run schema 4 stores `samplesPerScenario` and each observation's 1-based `sampleIndex`.
Every scenario must have exactly that many distinct indices and identical definitions.
Schemas 1–3 migrate in memory to schema 4; schema 1 gets one sample. Old files are unchanged.
Unknown future versions, partial sample sets, duplicate indices, or inconsistent
evaluation flags are rejected. Interrupted sampling has no completed snapshot.

Opt-in [statistical gating](statistical-gating.md) adds configurable minimum samples,
effect allowances, simultaneous confidence bounds, and exit 3 for inconclusive
comparisons. The strict semantics below apply when that policy is omitted.

## What the default gate means

Baseline and candidate must use the same suite and sample count. Their samples are
independent: sample 2 on one side is not sample 2 on the other. Comparisons count
passes, execution errors, and failed observations of each configured expectation.
More candidate failures produce the corresponding evaluator regression. A lower
observed pass count produces `FAILURE_RATE_REGRESSION` for repeated runs; the
single-sample case keeps `PASS_TO_FAIL`. Candidate execution errors still exit 2.

The gate is strict on **observed rates**, not on statistically established degradation.
The report includes counts and descriptive 95% Wilson intervals for scenario pass
rates, using the [NIST Wilson score formula](https://itl.nist.gov/div898/handbook/prc/section2/prc241.htm).
These intervals describe binomial proportions under independent, stable sampling
assumptions. Shared caches, memory, changing tools, and correlated provider responses
can violate those assumptions. Intervals do not establish a significant difference
between versions; no p-value, significance claim, or multiple-testing correction is
provided. Small samples remain visibly uncertain even if all pass.

Suite success rate and latency/token/cost means use every observation. Missing
usage/cost in any observation makes its suite mean unavailable. Existing threshold
semantics remain: no configured metric can silently pass when unavailable, and
success-rate allowances do not override per-scenario/evaluator observed regressions.

## Opt-in exact trace gates

```yaml
comparison:
  tool_arguments: true
  document_ids: true
```

Arguments are compared as `(tool name, complete JSON arguments)` and documents as
`(source, documentId)`. JSON object keys are canonicalized through the normalized
JSON model. A multiset of calls/retrievals forms each invocation trace, and a multiset
of those traces forms the observed sample distribution. Call order, retrieval order,
and sample order are ignored; multiplicity and invocation boundaries are preserved.
Two calls in one observation differ from one call in each of two observations.
Changed values produce `TOOL_ARGUMENTS_REGRESSION` or `DOCUMENT_REGRESSION` with
the observed traces. These gates represent an explicit promise of exact stability;
they are usually inappropriate for naturally varying query paraphrases or document IDs.

A reported tool call without non-null arguments, or a retrieval without a nonempty
document ID, causes `INSTRUMENTATION_MISSING` when that projection is enabled.
Empty call/retrieval lists are valid, inspectable empty traces. Execution errors
are handled separately rather than being represented as empty traces. Source-only
and required/forbidden-tool checks remain available for less strict testing.

## Varying offline fixture

```sh
./target/debug/wraith --config examples/sampling-agent/wraith.yaml run --samples 4 --save baseline
WRAITH_EXAMPLE_MODE=candidate ./target/debug/wraith --config examples/sampling-agent/wraith.yaml run --samples 4 --save candidate
./target/debug/wraith --config examples/sampling-agent/wraith.yaml compare baseline candidate
```

The adapter cycles through four outcomes: baseline 3/4 passes, candidate 1/4 passes.
Both run commands and comparison exit 1. Its `.wraith/sampling-counter` is synthetic
adapter state; remove it to reset the cycle, or run complete cycles of four observations.
This deterministic fixture demonstrates aggregation, not model randomness.

The separate `examples/trace-agent/wraith.yaml` fixture keeps both scenario runs
passing while changing only tool arguments and retrieved document IDs. Run/save
both versions with that configuration and compare them to exercise the two exact
trace gates. `scripts/demo.py` exercises both fixtures in temporary directories.
