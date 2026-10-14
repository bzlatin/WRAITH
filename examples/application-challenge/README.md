# LLM coverage challenge

Offline calibration against the same pinned, Apache-2.0 LLM source as the
[application pilot](../application-pilot/source.json).

- `entrypoint.py` observes actual sync/async tool execution and saved-history resume.
- `contracts.json` contains eight reviewed requirements added to nine CLI cases.
- `changes.json` declares twelve isolated source faults and four benign controls.
- `oracle.py` checks those requirements separately from native Wraith evaluation.
- `tasks.json` and `acceptance.py` define two subsequent local development changes.

The adapter records tools where their bodies run. Paused or rejected requests are
not recorded as successful execution. The cooperative socket guard and Echo model
keep evaluation offline; this is trusted code, not a security sandbox. A passing
mutation campaign measures the selected contracts, not reasoning or model quality.

See the [operator guide](../../docs/coverage-challenge.md) for preparation, automatic
execution, evidence retention, results, and limits. This fixture is assembled with
the original application pilot wrapper by `scripts/coverage-challenge.py`.
