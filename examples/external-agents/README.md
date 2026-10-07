# Upstream agent pilot

This pilot clones two official repositories at pinned revisions and executes their
actual agent orchestration through Wraith's Python function adapter:

| Repository | Upstream example | Offline boundary |
|---|---|---|
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | `weather_agent.py` | FunctionModel plus mocked HTTP endpoints; original tools execute |
| [LangGraph](https://github.com/langchain-ai/langgraph) | `tools_agent.py` | Upstream fake model and real tool node; search tool executes |

`sources.json` pins source revisions, paths, and MIT license provenance. Wrappers
import the cloned files; no upstream source is copied into Wraith or modified.
Models/tool boundaries are hermetic; Pydantic model network requests and Logfire
uploads are disabled. No model keys are needed or sent.

Requires Python 3.11+, Git, and a built Wraith binary. The first run uses network for
Git and package installation, then evaluates offline:

```sh
cargo build --locked
python3 scripts/external-pilot.py --install
```

Or use an existing isolated environment:

```sh
python3 scripts/external-pilot.py --python /path/to/venv/bin/python
```

Clones and the optional venv live under ignored `.wraith/`. Dependencies are pinned
in `requirements.txt`; it is not a full transitive lockfile. Script refuses to reset
an existing checkout at a different revision. Each rerun deliberately replaces its
pilot baseline while retaining history. Reports are in `.wraith/external-pilot/`.

Verified locally: three PydanticAI and three LangGraph baseline cases passed. A
controlled candidate model response that skips the required tool was detected in
all six cases. The tests prove external integration and regression reporting; they
do not establish live-model quality, false-positive rates, or natural bug discovery.
The next validation is repeat use during a real agent change.
