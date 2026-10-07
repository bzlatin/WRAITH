# Structured output checks

Use `expect.json` for deterministic contracts on the adapter's final `output`.
This is useful for generated workouts, plans, and other structured responses where
wording can vary but IDs, equipment, counts, and required fields must stay valid.
Wraith v0.4+ supports these checks without provider dependencies or executable rules.

```yaml
version: 1
agent:
  command: "node ./adapter.js"
tests:
  - id: dumbbell-workout
    input: {equipment: [dumbbell]}
    expect:
      json:
        - path: /workout/exercises
          check: {op: length, min: 3, max: 4}
        - path: /workout/exercises
          check: {op: unique, by: /exerciseId}
        - path: /workout/exercises
          each: /exerciseId
          check: {op: in, values: [Dumbbell_Floor_Press, Dumbbell_Shoulder_Press, Dumbbell_Lateral_Raise, Dumbbell_Triceps_Extension]}
        - path: /workout/exercises
          each: /sets
          check: {op: range, min: 3, max: 3, integer: true}
        - path: /workout/reasoning
          check: {op: length, min: 1}
```

Paths are JSON pointers relative to `output`: empty string selects the whole value,
`/a/0/b` selects an array member's field, `~1` escapes `/`, and `~0` escapes `~`.
There are no wildcards or implicit conversions. Optional `each` requires `path` to
select a **nonempty array**, then evaluates the relative pointer on every member.
Use `each: ""` to check the members themselves. A missing field always fails.

| Check | Contract |
|---|---|
| `equals`, `value` | Exact JSON value equality, including explicit null |
| `in`, `values` | Membership in a nonempty list of JSON values |
| `not_in`, `values` | Non-null value absent from a nonempty list |
| `range`, `min` and/or `max` | JSON number within inclusive bounds; optional `integer: true` rejects fractional values |
| `length`, `min` and/or `max` | Array item count or string Unicode character count within inclusive bounds |
| `unique`, optional `by` | Array values are distinct; `by` selects a field on each member; missing/null members or projections fail |
| `exists` | Selected value exists and is non-null |

Bounds must be ordered. Numeric bounds must be finite; range evaluation uses
floating-point numbers, so use exact equality/membership for large integer IDs.
An empty array passes `unique`; add a length minimum if it must contain items.
`length: {min: 1}` accepts whitespace-only strings. The checks do not judge prose
quality, coaching quality, semantic similarity, or facts outside the supplied output.
Unknown operators and fields fail configuration loading.

Each assertion is one expectation (including all members selected by `each`). Run
artifacts retain expected rules and observed values with concrete failing pointers.
A newly failing assertion produces `STRUCTURED_OUTPUT_REGRESSION`. Unchecked output
changes remain informational. Repeated samples and opt-in statistical gates count
failures per assertion, not per array member; the ordinary strict policy is default.
Changing inputs or assertions requires rerunning the baseline, just like other checks.

Run/report schemas are now **4**; protocol and configuration remain version **1**.
Schemas 1–3 migrate in memory, preserving existing checks and schema 3 statistical
policies. Original files stay untouched. Older Wraith versions reject schema 4.

## Push / Pull pilot

The first consumer is the separate `fitness-app` repository's
`server/evals/wraith` integration. Its adapter invokes the same provider and workout
postprocessing as the production route, using ten synthetic profiles and a fixed
catalog without database access. Offline mutations prove the contracts can catch
invalid IDs, equipment, duplicates, set counts, and missing fields.

On October 6, 2026, all ten offline baselines passed, a harmless wording change
triggered zero alarms in ten cases, and all 50 injected failures were detected.
A capped live baseline/candidate experiment passed four cases in each version,
using eight model requests. This small smoke check does not estimate live failure
rates or establish statistical equivalence. No naturally occurring live regression
was discovered. The app's integration README documents the edit/compare workflow;
repeat use and a useful real regression remain the next product validation goals.
