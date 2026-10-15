# Equal-requirement weather workflow comparison

This finite offline study compares Wraith with conventional Python integration
tests on PydanticAI's actual weather example. Models and HTTP are scripted; this
is not live model quality or production usage. Upstream source is pinned and MIT
licensed; see `UPSTREAM_LICENSE.txt`.

`requirements.json` defines ten reviewed requirements. `cases.json` expresses the
same assertions for Wraith; `ordinary.py` runs ordinary assertions. `adapter.py`
observes actual tool returns and HTTP requests. `tasks.json` freezes two independent
feature tasks and the stopping rule. The patches reproduce the reviewed changes;
calibration faults remain separate from feature work and useful catches.

See [results and reproduction](../../docs/weather-comparison.md) and the
[product direction decision](../../docs/product-assessment.md). No provider requests,
user data, recurring monitor or new commercial claim is part of this study.
