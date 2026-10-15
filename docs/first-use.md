# Faster setup and case authoring

These additions require a current source build; they are not in published v0.5.0.
They reduce config and wrapper editing while preserving explicit expectations,
fixed baselines, native exit codes, and local history.

## Connect an existing function

Use `--input-only` for a function that accepts its request and returns JSON:

```sh
wraith init --entrypoint agent.py:answer --input-only --cases cases.json
wraith doctor
wraith baseline
```

Python and TypeScript support the flag. It explicitly passes one argument; Wraith
does not guess signatures, retry calls after a TypeError, or add instrumentation.
Without the flag, `(input, context)` remains the default. Use that default when
you need Wraith's tool/retrieval recording or live-attempt budget helpers. Existing
synchronous APIs that manage their own event loop still need the async worker
wrapper described in [getting started](getting-started.md).

`--cases` reads a nonempty JSON array of reviewed scenarios before creating any
starter files. Each case needs an explicit `expect` object. Invalid cases fail
before writing the adapter, config, or project file. The
[batch example](getting-started.md#add-a-regression-case) shows the format. Init
never overwrites existing setup. The provided cases replace its placeholder only
when creating a fresh configuration; they never replace an accepted baseline.

## Add expectations without a separate JSON file

Use a saved run to recover the original input and metadata, then specify the
requirement explicitly:

```sh
wraith cases add --id pending-denied --from-run saved-run.json \
  --scenario pending-request \
  --json-equals /executions 0 --forbid-tool delete_record
```

`--json-equals POINTER JSON` can repeat. Values are typed JSON: `0`, `false`,
`null`, arrays, objects, or a JSON-quoted string. For a string in a POSIX shell:

```sh
wraith cases add --id denied-message --input input.json \
  --json-equals /status '"denied"' --contains denied
```

PowerShell/CMD quoting differs; use `--expect expect.json` for complex values or
shell-independent file exchange. `--require-tool`, `--forbid-tool`, and `--contains`
can also repeat. These flags conflict with `--expect`; they never infer correctness
from the recorded response. Invalid JSON, pointers, duplicate IDs, and invalid
rules fail before rewriting config. Changed suites still require deliberate
`wraith baseline --replace`; old results remain retained.

## Assisted benchmark

From a source checkout with the earlier coverage resources available:

```sh
cargo build --workspace --locked
python3 scripts/first-use.py --root .wraith/first-use/benchmark \
  --resources .wraith/coverage-expanded-validated \
  --before-binary /path/to/earlier/wraith --binary target/debug/wraith
```

Use a different explicit root for another run. Existing and incomplete roots are
preserved. An earlier v0.5 binary supports the before path. The resources come from
[the offline coverage challenge](coverage-challenge.md). The runner snapshots
binaries, source, cases, logs, and reports; it executes native commands serially
and seals the completed experiment. No provider model is called.

Both paths start in a fresh configuration directory and reach a passing baseline,
a passing equivalent change, the same deliberately failing approval check, and a
passing restoration. They use identical eighteen-case suites and existing offline
application dependencies. The improved path removed **two manual config/expectation
file operations**; both paths used seven native commands. A separate utility check
connects LLM's unmodified schema parser with no custom wrapper in two commands;
that utility is not agent orchestration or evidence of model quality.

The reviewed dataset and application wrapper were prepared before timing. This is
an assisted mechanical comparison, not complete cold-start onboarding, independent
user success, reduced human authoring time, natural bug discovery, or superiority
over the application's existing tests. See ignored `.wraith/first-use/benchmark/report.md`
for local evidence. Use the constraints to decide what to improve next rather than
claiming complete setup is automatic.
