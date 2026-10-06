# Statistical failure-rate gates

Strict observed-rate comparison remains the default. Opt in through configuration
or a trusted `compare --policy` file:

```yaml
comparison:
  statistical:
    min_samples: 100
    max_failure_rate_increase_pp: 20
    alpha: 0.05
```

The 20 percentage-point allowance is illustrative; set an acceptable degradation
for your application before collecting observations. This policy applies to each
scenario's failure rate and each individual expectation's failure rate. The example
in `examples/rag-agent/statistical.yaml` contains one scenario to keep sampling quick.
All three fields are required. Minimum samples must be 2–1000, allowance 0–100,
and alpha greater than zero and at most 0.25; nonfinite values are rejected.

## Decision and CI contract

- **Passed (exit 0):** every interval's upper bound is at or below the allowance,
  all endpoints meet the minimum count, and all other configured gates pass.
- **Regression (exit 1):** at least one lower bound exceeds the allowance, or a
  strict trace/metric gate fails.
- **Inconclusive (exit 3):** no definite failure, but too few samples or an interval
  crosses the allowance. This blocks CI; it is not a statistical pass.
- **Execution/setup error (exit 2):** malformed data or candidate execution errors.
  These take precedence. Interruption remains exit 130.

`run` still exits 1 when any observation fails an expectation. `compare` applies
the policy to the accumulated evidence. Existing exact argument/document checks
and suite success-rate/latency/token/cost thresholds remain strict and may override
statistical acceptance. Omit those strict gates when their observed sensitivity is
not intended. Forbidden-tool expectations also use the statistical allowance when
enabled; for zero-tolerance requirements retain a separate strict comparison.

Report schema 3 adds `statisticalResults` and `inconclusive`. Every endpoint records
sample counts, failure counts, observed increase, simultaneous interval, allowance,
alpha, family size, method, decision, and reason. `passed` is false for inconclusive
results. An explicit `--policy` overrides candidate statistical settings just as it
already overrides exact checks and thresholds. Run schemas 1 and 2 migrate in memory
to schema 3 with strict behavior; files are not rewritten. Older Wraith versions
reject schema 3 rather than silently ignore the new policy.

## Method and limits

Let d be candidate failure proportion minus baseline failure proportion. For n
independent observations per version and m prespecified endpoints, use

```
radius = sqrt(log(2*m/alpha) / n)
interval = [max(-1, d-radius), min(1, d+radius)]
```

The implementation applies the bounded-sum inequality to the difference of the two
sample means, then a union bound over all endpoints. It counts unchanged checks too.
See [Hoeffding's original paper, Theorem 2](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf).
This yields conservative simultaneous coverage of at least 1-alpha under the stated
sampling assumptions. Dependence between different checks is allowed; independent
observations within and between versions are required. No pairing by sample index,
normal approximation, p-value, or overlapping-Wilson-interval heuristic is used.

This bound can need many observations. At n=200, m=6, alpha=0.05 the radius is about
16.55 percentage points; at n=1000 it is about 7.40 points. Minimum sample count alone
does not make an interval narrow. A zero allowance generally cannot certify unchanged
behavior with finite samples; use the strict mode for deterministic invariants.

Fix your suite, allowance, and sample count before the experiment. Repeated peeking,
trying policies until one passes, correlated caches, evolving corpora, and provider
drift invalidate the claimed experiment-level guarantee. The correction covers one
comparison's rate endpoints, not unlimited comparisons, strict trace gates, or suite
metric thresholds. The descriptive Wilson intervals remain separate from this gate.
