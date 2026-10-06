# Architecture

```text
YAML config -> scenario definitions -> subprocess adapter -> AgentRun
AgentRun + expectations -> EvaluationResult[] -> ScenarioResult
ScenarioResult[] + thresholds -> RunSnapshot -> local JSON
two RunSnapshots -> comparison + threshold checks -> ComparisonReport
structured results -> CLI human/JSON renderer -> exit code
```

`wraith-core` owns `config`, `model`, `runner`, `evaluation`, `snapshot`,
`comparison`, and `error`. `wraith-cli` owns argument parsing, starter files,
rendering, and exit codes. Evaluation never parses YAML; comparison never executes
agents; the protocol contains no terminal formatting. Provider calls, workflows,
tools, databases, and agent state belong to the adapter/application.

## Protocol and process lifetime

Protocol version 1 sends one UTF-8 JSON line on stdin and closes stdin. The request
requires `protocolVersion`, `scenarioId`, `input`, and `metadata`. One invocation
handles exactly one scenario. The response must contain `protocolVersion: 1`, the
same `scenarioId`, and a non-null `output`. It may contain `toolCalls`, `retrievals`,
`usage`, `estimatedCostUsd`, and `metadata`. See [protocol.md](protocol.md).
No persistent process, negotiation, streaming messages, or provider assumptions.

Stdout contains exactly one JSON value, normally followed by a newline. Surrounding
whitespace is accepted; extra messages, banners, or JSON values are rejected.
Stderr is for diagnostics. Successful stderr is discarded rather than stored.
Failure diagnostics retain at most 64 KiB; invalid stdout previews retain 512 bytes.
Stdout is capped at 1 MiB. Readers continue draining over-budget pipes so the child
cannot deadlock on a full buffer; oversized stdout causes a protocol error.

The command uses shell-style quoting to obtain arguments, then launches the
executable directly. Shell expansion, pipelines, redirection, and variable
assignment are not implemented. Paths resolve from the configuration directory.
Environment is inherited without being enumerated, printed, or serialized.

Tokio concurrently writes the request, drains both output pipes, and waits for
exit. One deadline covers that entire exchange, including a descendant retaining
an open pipe. On failure/timeout/cancellation the process tree is killed and the direct child is waited on, with a five-second cleanup deadline. On Unix, each
agent starts in its own process group; cleanup kills ordinary descendants even
after a successful parent exit. A drop guard handles task cancellation, with
Tokio kill-on-drop as a direct-child fallback. This is execution isolation, not
a security sandbox: agents may access the host's files and network.

Windows uses the safe [`process-wrap` JobObject wrapper](https://docs.rs/process-wrap/10.0.1/process_wrap/tokio/struct.JobObject.html),
which suspends creation, assigns the job, and resumes the agent. Kill-on-close and
explicit termination cover descendants. The runner waits on the inner direct child
before cleanup rather than blocking on the lifetime of the whole job. Job assignment
failure is an execution error; no uncontained fallback is allowed. The dependency
requires Rust 1.87, which is the workspace minimum.

The CLI registers Ctrl-C handling before polling execution, shares a cancellation
token, and awaits the same execution future through cleanup. Cancellation stops
further observations and returns exit 130 without saving a partial run. Dropping an
execution task still invokes the process guard. Native-platform timeout, cancellation,
and parent-exit/pipe tests run in the CI matrix. Local Windows compilation verifies
types, not kernel behavior.

Unix descendants that detach into another session escape process-group cleanup.
Hard termination of Wraith itself cannot run Unix drop guards. This remains process
containment rather than a filesystem/network sandbox. Spawn can fail before the
async deadline begins; OS stalls during creation are outside its guarantee.

## Evaluation and comparison

A scenario passes when the subprocess succeeds with a valid response and every
configured expectation passes. With no expectations, valid execution is enough.
Each expectation produces its own expected value, observed value, pass flag, and
message. Text checks are case-sensitive substrings of a string output or
`output.text`; missing text fails both positive and negative checks. Tool checks
test the presence of a name, regardless of reported success. Source checks use
`retrievals[].source`, not document IDs. Missing token usage fails a token budget.
Latency includes startup, pipe transfer, execution, and cleanup.

Comparison requires identical scenario ID sets, sample counts, and identical scenario input,
metadata, and expectations. Reordering the suite is allowed; changing it requires
rerunning the baseline. There is no partial-suite success that hides removed tests.
Artifacts validate duplicate IDs, response identities, and consistency of evaluation
results by recomputing deterministic checks before comparison.

New failed expectations are classified as output, tool selection, source, policy
(forbidden tool), latency, or token regressions. Pass-to-fail and new execution
errors always fail the comparison. Fail-to-pass is an improvement. Tool and source
sets that differ produce warnings; output differences produce information.
Unchanged behavioral failures in both versions do not count as new regressions;
candidate execution errors still cause exit 2 even if present in the baseline.
These ungated differences remain visible when both scenarios pass. Opt-in
`comparison.tool_arguments` and `comparison.document_ids` compare exact trace
multisets and fail on changed behavior or missing instrumentation. See
[sampling.md](sampling.md) for independent observation aggregation. Tool/retrieval order and retrieval ranking are not gated; counts and invocation
boundaries are retained by exact argument/document comparisons.

Candidate snapshots carry the comparison thresholds and exact comparison options.
An explicit CLI `--policy` supplies a trusted configuration, validates its entire
suite, and overrides both policy fields without rewriting either snapshot.
Reports record `policySource` and effective exact comparison options for review.
A comparison without an override needs no YAML
file; policies are reviewable inside the candidate JSON. In CI, keep the configuration
under review: a candidate can relax thresholds. Success-rate allowance is a decline
in **percentage points**; latency, tokens, and cost allowances are **relative percent
increases in the suite mean**. Equality at the boundary passes. An allowed success-rate
decline does not override an individual pass-to-fail regression.

Token/cost means exist only if every scenario reports them. Missing baseline or
candidate metrics fail a configured threshold with an explicit unavailable message;
without a threshold they are displayed as unavailable. Zero-to-zero passes; zero
to any positive value fails every finite percentage-increase allowance. Decreases
pass. These are deterministic arithmetic checks, not confidence intervals. Adapter
reported cost is accepted as a nonnegative finite USD value; provider pricing is
outside the core.

## Storage, secrets, and versioning

Named runs live at `.wraith/runs/<name>.json`. Names are constrained to ASCII letters,
digits, underscores, and hyphens. A save atomically replaces an existing named run
using a same-directory temporary file and flushes the file before replacement.
Temporary files have restricted permissions. Directory fsync for power-loss
durability is deferred. Errors never upload anything.

Config version, protocol version, run schema version, and package version are
independent. Current run schema is 3, with protocol and YAML version still 1. Unsupported schemas are rejected before typed
deserialization, with an upgrade hint. The reader migrates schema 1 to schema 3 with `samplesPerScenario: 1`,
`sampleIndex: 1`, and default comparison options, then validates the result. Preserve fixtures from each supported version; never silently reinterpret
unknown versions. Schema 2 also migrates to strict schema 3 in memory. Comparison JSON has
`schemaVersion: 3`, adding statistical decisions and an explicit inconclusive flag.
See [statistical-gating.md](statistical-gating.md) for the opt-in rate policy.

Saved runs retain scenario inputs/metadata/expectations, normalized responses,
evaluations, durations, Unix millisecond timestamps, and structured errors. They
do not include the process environment or a command field (errors may quote the
command for diagnostics). Adapter outputs, tool arguments,
metadata, and error diagnostics can contain application secrets. No redaction
engine is provided. Keep `.wraith` ignored and apply your own retention/access policy.
The files are trusted local artifacts, not signed attestations.

## Growth without replacing the core

New deterministic evaluators can extend the small evaluator enum and evaluation
function. A custom executable evaluator can later operate on the same normalized
models; a dynamic plugin registry is unnecessary now. Python and TypeScript SDKs
should wrap request/response serialization and instrumentation only, preserving
one authoritative Rust evaluation/comparison engine.

Future OTEL ingestion can map a root workflow span to scenario/timing metadata,
tool spans to `ToolCall`, retrieval spans to `Retrieval`, model usage to `TokenUsage`,
and final outputs/errors to the normalized response/run. Ordered model/workflow
events may require a schema addition rather than hiding them in metadata. Trace
replay must capture fixtures for external state and nondeterministic tool results;
a saved prompt alone cannot reproduce production behavior.

For deterministic CI, keep IDs, inputs, expectations, and adapter fixtures fixed.
Use key/ID ordering for reports, no color or terminal escape sequences in JSON,
no environment serialization, and explicit exit codes. Real latency/timestamps
are intentionally nondeterministic; do not byte-compare entire artifacts.

The implemented composite action wraps the existing binary. The baseline workflow
persists a commit-named artifact; PRs retrieve a successful baseline for exactly the
base SHA, run the candidate, compare JSON with trusted base policy, and honor exits.
No privileged PR event or provider secret is used. The workflow is described in
[ci.md](ci.md); it requires bootstrapping into the default branch before PR use.

Async Rust benefits subprocess I/O, deadlines, cancellation, and future bounded
concurrency. Parsing, evaluation, comparison, and small artifact file operations
are straightforward synchronous functions. Sequential execution avoids an elaborate
scheduler; traits, separate policy languages, databases, and additional crates
should follow demonstrated needs.
