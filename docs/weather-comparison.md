# Wraith and ordinary tests on a weather workflow

Two local changes to PydanticAI's official weather example passed the same ten
requirements in Wraith and conventional Python tests. Both runners detected the
same two deliberately introduced faults. No naturally introduced regression was
found. This supports the engine's correctness, not superior detection or demand.

## Requirements and changes

The source is the MIT-licensed [upstream weather example](https://github.com/pydantic/pydantic-ai/blob/0ba01f92be3fc361f89970502cd6e7dd3611aec3/examples/pydantic_ai_examples/weather_agent.py).
It executes the actual PydanticAI agent, coordinate lookup and forecast tools.
A FunctionModel replaces provider calls, and HTTP fixtures replace the example's
random demo endpoints. Logfire export and real model requests are disabled; a
cooperative socket guard detects accidental network access.

Ten requirements cover location-to-forecast chaining, forwarding coordinates,
zero/negative/fractional temperatures, Unicode locations, repeated runs, unavailable
services and invalid coordinates. Cases, observations and expectations are shared
with conventional `unittest` assertions. This intentionally tests equal detection
on the same requirements; it does not compare independent test design. The whole
upstream SDK test suite was not run.

Before candidate edits, the requirements and two feature acceptance checks were
frozen. Each independent candidate changes only the exported application module:

- Retry one transient 503 from a forecast endpoint, preserving permanent errors.
- Add caller-selected Fahrenheit while keeping Celsius as the default.

Both acceptance checks fail on the original and pass on their candidate. Both
candidates pass all ten old-behavior requirements. These are developer-selected
changes to an upstream example, not maintainer-requested changes, contributions,
production agent use, or independent adoption. Scripted models do not test prompt
quality or whether a live model chooses the right tools.

## Result

| Observation | Ordinary Python tests | Wraith |
| --- | --- | --- |
| Ten requirements, each feature candidate | Pass | Pass |
| Coordinate-swap control | Seven failing cases | Same seven cases |
| Removed HTTP-status check control | One failing case | Same case |
| New useful natural regressions | None observed | None observed |
| Retry feature, base + candidate | 2.25 s | 7.00 s |
| Unit feature, base + candidate | 2.04 s | 6.99 s |

Times are single warm-dependency runs on macOS arm64 with Python 3.13 and a debug
Wraith binary. They include executing both versions and writing evidence, excluding
installation, source preparation, build, acceptance checks and human work. Ordinary
tests run one process per version; Wraith isolates each scenario, using four jobs,
and generates a comparison and HTML report. These are descriptive measurements,
not statistically estimated speed differences or representative production latency.

The controls calibrate parity: two seeded defects affect eight case results. They
are not eight bugs or new discoveries. Equal assertions are expected to have equal
detection; this result does not prove either runner catches untested failures.

The initial qualification failed in both runners because the draft expected a
specific validation exception. PydanticAI retries and wraps that error. The draft
was preserved; before candidate edits, a new study froze the user-facing requirement
that invalid coordinates produce no forecast and no weather request. Raw exception
classes remain visible without gating on a library-specific wrapper.

Wraith supplies fixed policies, per-scenario subprocesses, portable history and a
before/after HTML report. The standard test helper also saves observed JSON, so the
comparison does not claim that ordinary tests cannot retain evidence. Whether
Wraith's report saves review work was not measured. [Sanitized evidence](evidence/weather-comparison.json).

## Reproduce

From a current source checkout with Git and Python 3.12+:

```sh
cargo build --workspace --locked
python3 scripts/weather-study.py --root .wraith/weather-replay reproduce --install
```

This installs the pinned dependencies in a new sibling bootstrap directory, exports
the pinned example, applies the reviewed feature patches, runs both runners and
the labeled controls, and seals completed evidence. Reproduction is recorded replay,
not another natural development observation. Read `assessment.json` in the selected
root; HTML reports are under `runs/*/native/report.html`.

The original run was local on macOS. Linux/Windows application execution has not
been verified by this study. No recurring automation or additional PR job is needed
for this completed experiment. Standard repository CI tests the evidence boundaries.

To evaluate a genuinely new task, `prepare` accepts explicit `--binary`, `--python`
and `--upstream` paths; the clone must match the pinned revision. It returns the only
editable candidate files. `evaluate retries`, `evaluate units`, `calibrate`, `finish`
and `verify` operate on the finite frozen study. Existing roots, old evidence and
frozen policies are preserved. Feature acceptance, regression checks and calibration
remain separate. Research command success means evidence collection completed;
individual native exits retain the actual gate decision.
