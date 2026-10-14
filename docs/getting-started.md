# Connect an agent and check a change

Wraith evaluates your application function. It supplies small, dependency-free
Python and TypeScript adapters; you supply representative inputs and reviewed
expectations. Existing subprocess adapters remain supported.

## Python

Save this working offline example as `agent.py`, or export a wrapper around your
existing application function:

```python
# agent.py
def search_documents(query):
    # Offline example; replace this with your application's real lookup.
    return {"text": "Employees receive 20 PTO days."}


def evaluate(input, context):
    query = input["text"]
    result = search_documents(query)
    context.tool("search_documents", {"query": query}, result)
    return result
```

```sh
wraith init --entrypoint agent.py:evaluate --language python
wraith doctor
```

The function can be synchronous or asynchronous. A current source build also
supports `init --input-only` for an existing single-argument function and `--cases`
for reviewed initial scenarios; see [faster setup](first-use.md). `module:function` and
`path.py:function` are supported. Logs printed during import or invocation go to
stderr. Return JSON-compatible values; convert Pydantic models explicitly with
`model_dump(mode="json")`. Use `--runtime /path/to/venv/bin/python` for dependencies
in an existing virtualenv. Activate that environment when using a plain `python3`.

For async agent frameworks, export `async def evaluate(...)` and await the agent's
async API. The adapter invokes functions inside an event loop; calling an API such
as PydanticAI's `run_sync()` there raises “event loop is already running.”
For a synchronous CLI/API that manages its own event loop, call it from an async
entrypoint with `await asyncio.to_thread(sync_function, input, context)`.

## TypeScript

In a separate directory, save this as `agent.ts`. Init generates the adapter and its
type declarations alongside your function:

```typescript
// agent.ts
import type { Context } from './wraith-adapter.mjs';
function searchDocuments(query: string) {
  // Offline example; replace this with your application's real lookup.
  return {text: "Employees receive 20 PTO days."};
}

export function evaluate(input: {text: string}, context: Context) {
  const result = searchDocuments(input.text);
  context.tool("search_documents", {query: input.text}, result);
  return result;
}
```

```sh
wraith init --entrypoint agent.ts:evaluate --language typescript
```

Node 22.18+ can run TypeScript using native type stripping. For projects using
unsupported TypeScript syntax, path aliases, or a separate build step, point at the
compiled `.js` export and run your build first. `.mjs` and `.cjs` also work.
No npm package installation is required for Wraith's adapter itself.

Without flags, `init` offers an entrypoint prompt on an interactive terminal and
chooses the language from the file extension/project. `init --demo` creates the
three-case deterministic example. Init refuses to overwrite existing starter files.
`--template tools` or `--template rag` supplies a draft tool/source expectation;
review the names. The default JSON starter only checks that output exists.

## Define the promise

The generated `wraith.yaml` is JSON, which is valid YAML. Replace the starter input
and expectation with something meaningful, for example:

```yaml
version: 1
agent:
  command: "python3 wraith_adapter.py agent.py:evaluate"
tests:
  - id: policy-answer
    input: {text: "How many PTO days do we receive?"}
    expect:
      output_contains: ["20"]
      tools_called: [search_documents]
```

The examples above record a lookup that actually ran. Record application activity
at the point it occurs:

| Activity | Python | TypeScript |
| --- | --- | --- |
| Tool call | `context.tool(name, arguments, result, success)` | `context.tool(name, arguments, result, success)` |
| Retrieved document | `context.retrieval(source, document_id)` | `context.retrieval(source, documentId)` |
| Observed token counts | `context.usage(input_tokens, output_tokens)` | `context.usage(inputTokens, outputTokens)` |

Repeated usage calls accumulate. Do not invent trace
or usage values. These helpers record claims; Wraith cannot independently observe
uninstrumented application activity.

`wraith doctor` validates config, runtime/script/entrypoint paths, and declared
credential presence without importing your agent. It hides credential values. It
cannot discover every runtime dependency or validate a function without execution;
baseline errors retain actionable diagnostics. It flags individual scenarios with
no behavioral constraints beyond presence checks, even within a stronger suite.
This review does not measure source coverage or discover unrecorded tool calls.

## Save, change, check

```sh
wraith baseline
# Edit prompts, model choices, or agent code.
wraith check
wraith history
wraith report
```

Reports are written automatically under `.wraith/history/<id>/report.html`;
`.wraith/index.html` links the history. Open the printed path in your browser.
`report --run <id>` regenerates a specific report without rerunning the agent.
`compare baseline candidate --html report.html` adds HTML to legacy saved comparisons.

History stores full runs, effective comparison results, the agent command, declared
model label, Git commit and working-tree state, timestamp, and request budget identity.
The model label is declared in `wraith.project.json`; it is not auto-detected or
verified against provider configuration. Git state does not fingerprint every
uncommitted file. For reproducibility, commit your code and keep external fixtures
fixed. Environment values are never enumerated or saved.

Changing inputs, metadata, expectations, sample counts, or offline/live mode requires
`baseline --replace`; check rejects those changes before executing the agent. Model
or code changes are candidates, not reasons to silently replace the baseline. Old
history is retained. Baseline execution/instrumentation errors are saved but never
accepted. Existing behavioral failures can be baseline debt and remain visible.

Current source builds also support `baseline --jobs 4` for independent offline
observations. Later checks inherit that setting; changing it requires a new
baseline. Shared-state and live agents stay sequential. See the
[measured workflow](workflow-value.md) before enabling concurrency.

## Live requests

For a new integration, add `--mode live` to `wraith init`. For an existing one, set
`mode` to `live` in `wraith.project.json`. Declare `model` and `requiredEnv` names
if useful. Credentials belong in your environment or your app's existing loader,
never in the project file. Wraith does not automatically read `.env`.

```sh
wraith baseline --allow-live --max-requests 20
# Change the agent.
wraith check --allow-live
```

One budget covers baseline plus all checks, failed calls, and retries. Check cannot
raise or reset it. Another baseline requires a deliberate `--replace` and creates a
new experiment. A failed/interrupted attempt consumes any slots already reserved.
The next invocation never gets an automatic fresh budget.

Wrap **every actual provider attempt**, including retries:

```python
with context.model_call():
    response = await client_call()
```

```typescript
const response = await context.modelCall(() => clientCall());
```

Disable provider SDK automatic retries or instrument each transport attempt; a
helper around a call containing hidden retries cannot count those internal requests.
The helper reserves a slot before calling, locks the shared file, and fails closed
on exhausted/invalid/locked budgets. This is cooperative instrumentation, not a
network sandbox: arbitrary application network requests cannot be forcibly capped.
The live workflow requires budget instrumentation metadata from its adapter.

Offline mode has no budget; calling the model-call helper fails before invoking the
provider. The generated SDK cannot prevent code that bypasses it from using network.
Routine tests and generated CI should use explicitly offline fixtures.

## Add a regression case

A current source build can also [add typed expectations from CLI flags](first-use.md#add-expectations-without-a-separate-json-file).

Prepare `input.json` with the request input and `expect.json` with reviewed Wraith
expectations, then:

```sh
wraith cases add --id reported-bug --input input.json --expect expect.json
```

Or copy a scenario's input/metadata from a saved run:

```sh
wraith cases add --id reported-bug --from-run saved-run.json \
  --scenario original-case --expect expect.json
```

For a reviewed batch, save a JSON array in `cases.json`:

```json
[
  {
    "id": "approval-denied",
    "input": {"approve": false},
    "expect": {"tools_not_called": ["delete_record"]}
  },
  {
    "id": "result-count",
    "input": {"text": "Find two records"},
    "expect": {"json": [{"path": "/records", "check": {"op": "length", "min": 2, "max": 2}}]}
  }
]
```

```sh
wraith cases import --file cases.json
```

Batch import requires a nonempty array and an explicit `expect` object per case.
It validates the entire merged suite before writing; one invalid case leaves
configuration and the accepted baseline untouched. Empty expectations remain
possible but receive a `doctor` warning. **Batch import and per-case expectation
warnings require a current source build; they are not in published v0.5.0.**

Observed output is never automatically treated as correct. Duplicate IDs and invalid
expectations fail before rewriting config. The command serializes config as JSON;
YAML comments are not retained. Refresh the baseline after reviewing the new case.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Configured checks passed |
| 1 | Failed expectations, a regression, or a threshold failure |
| 2 | Execution or setup error |
| 3 | Inconclusive statistical comparison; blocks CI |
| 130 | Interrupted; no partial run saved as complete |

A baseline with behavioral debt may exit 1; that does not make its failures new.
A check compares changes and can pass despite unchanged debt. Current source
builds warn about remaining failed observations in CLI and HTML; the saved gate
decision and exit code are unchanged. Use `wraith run` for a current-code check
that requires every configured expectation to pass.
One observation per version cannot establish statistical non-regression. Use
`baseline --samples N` and [statistical gating](statistical-gating.md) when appropriate.
Live repeated sampling still needs explicit budget authorization.

## Troubleshooting

- **Executable or import not found:** run `wraith doctor`, select your application's
  runtime with `init --runtime`, and install its dependencies in that environment.
- **Suite differs from baseline:** review changed inputs, expectations, metadata,
  sample counts, or mode. Use `baseline --replace` only when that change is intended.
- **No tool/source evidence:** add context recording where the real activity occurs;
  Wraith cannot infer calls from the final answer.
- **Unexpected failures:** inspect expected/observed values and both outputs in the
  report before weakening checks. For variable behavior, read [sampling](sampling.md).

Next: [add offline PR checks](ci-setup.md) or [review the configuration reference](configuration.md).
