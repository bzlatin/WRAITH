# LLM application pilot

An offline integration with the actual [LLM CLI](https://github.com/simonw/llm).
This pilot evaluates isolated source changes; it does not modify an installed
user application or contact model providers.

[Operator guide](../../docs/application-pilot.md) covers setup, the finite work
queue, evidence, and limits.

- `source.json`: upstream revision and license provenance.
- `entrypoint.py`: actual CLI and schema execution through the function adapter.
- `tool_functions.py` / `tool_runtime.py`: harmless tools and observed activity.
- `offline/sitecustomize.py`: cooperative socket guard.
- `contracts.json`: reviewed execution, cancellation, discovery, and schema rules.
- `tasks.json` / `acceptance.py`: legitimate feature work, checked separately.
- `requirements.txt`: pinned pilot dependencies; upstream source installs separately.

The source remains Apache-2.0 licensed. Exports, candidate patches, and reports stay
under ignored `.wraith/`; nothing is uploaded or submitted upstream by this pilot.
