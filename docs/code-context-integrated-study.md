# Actual Codex MCP comparison

October 16, 2026. This separately approved experiment tests the source preview's
actual MCP workflow after the earlier [test setup](code-context-codex-study.md)
and [approval failures](code-context-ready-tests.md). Earlier experiments remain
closed; their unused allowances and results were not reused.

[Protocol](../experiments/code-context/study/integrated-codex-protocol.json) ·
[Controller](../experiments/code-context/study/integrated_codex.py) ·
[Sanitized results](../experiments/code-context/study/integrated-codex-results.json).

**Model-directed Wraith delivery works. The full comparison stopped on a timeout,
so a development benefit remains unproven. Keep hosted expansion paused.**

## Outcome

| Session | Result | Session time |
| --- | --- | --- |
| Setup 1, per-tool `auto` | MCP approval denied | 10.98 s |
| Setup 2, per-tool `approve` | Real context returned | 8.08 s |
| Hono native, repetition 1 | Completed; 56 tests passed | 28.25 s |
| Hono Wraith, repetition 1 | Completed; real context; 56 tests passed | 44.12 s |
| Zod Wraith, repetition 1 | Real context; 162 tests passed; no final completed turn before timeout | 180.02 s |
| Remaining five coding sessions | Not run after timeout | — |

Five of 12 session slots were consumed. The remaining seven are **closed**:
two unused setup slots and five unattempted coding runs. All old budgets remain
closed. There are no scheduled retries or automatically continuing live studies.

The timed-out Zod patch is minimal, stays in the approved module, preserves the
prepared helper/tests and passes external verification. Its agent also ran the
prepared command successfully. It is still **not an accepted completed session**
under the frozen rule. The final turn and usage record are absent. The trace does
not establish why the final response failed to arrive; do not attribute the timeout
to retrieval or count missing usage as zero.

The one completed Hono pair passed the same tests in both workflows. Wraith took
56.2% longer in that observation. This is neither a repeated comparison nor a
causal estimate. The full median-time criterion cannot be evaluated; reporting a
median win or task-success advantage from this attempt would be misleading.

Both coding context calls returned nonempty payloads before the first recorded
file edit. Hono context included its approved production module; Zod's initial
results did not include `doc.ts`, and the agent located/read it with native tools.
This is a post hoc relevance observation, not a new held-out retrieval test or
proof of what caused the timings. The retrieval implementation was not changed.

Completed-turn usage is preserved per session in the results. Timeout usage is
unknown. Setup usage is listed separately from development. Cached-input tokens
are included in input totals; these are not subscription charges or bill estimates.

## Setup and method

The owner approved a shared ceiling of 12 ChatGPT subscription sessions: up to
four short configuration checks, then eight coding sessions. Check one used
per-tool `auto` and was denied. Check two used per-tool `approve` and returned
nonempty context through an actual model-directed `code_context` call. Those
settings were frozen before development. Only the three named Wraith read tools
received that setting; global prompting remained disabled. The optional
`--allow-read-tools` configuration helper now emits the working `approve` value.
The ordinary helper keeps client-default approvals.

Codex CLI 0.163.0 used `gpt-6.1-sol`, medium reasoning, ChatGPT authentication,
ephemeral sessions and a workspace sandbox on macOS arm64. The controller ignored
user configuration/rules, stripped provider keys and disabled web and nested
agents. No API-key runner was used. The session ceiling does not expose or cap
provider-internal attempts, and recorded tokens are not measured subscription
credit consumption or a reconciled bill.

Two pinned historical tasks were each run twice per workflow. The seeded,
counterbalanced order was fixed in the protocol. Native runs used native search;
Wraith runs were instructed to call `code_context` before editing and could use
native tools afterward. Each fresh worktree received the same prepared test
command, task requirements and production-only edit limits. Each session had
180 seconds with no retry. Failures and interruptions would stop the task stage.

These are repeated historical reproductions, not fresh prospective discoveries.
The same tasks produced patches in earlier stopped setup studies, but no prior
patch or transcript was supplied to the new sessions. Retrieval code, pinned
upstream source/tests and the prepared helper stayed unchanged. Configuration was
repaired against the separate prepared demo, without tuning retrieval on results.

Hono's selected CSS suite runs 56 tests. Zod's two compiler suites run 162.
Frozen old versions fail and upstream fixed versions pass in both host and Codex
sandbox controls. Acceptance requires a completed session, a nonempty patch only
in approved production paths, unchanged upstream tests/helper, and passing selected
tests run by both the agent and external checker. This does not cover full upstream
CI, type checking or every possible patch regression.

The continuation rule requires all eight sessions completed, real context payloads
in all four Wraith sessions, no reduction in accepted task count, and at least
20% lower median Wraith session time than median native time. Time includes CLI
and MCP startup, but excludes worktree preparation and external acceptance checks.
It measures machine runtime, not developer effort. Pair ratios and token usage
must be reported alongside the aggregate; this small two-task study cannot
establish statistical significance, production accuracy or reliable future savings.

## Decision

This attempt resolves the model-mediated MCP approval defect. It does not meet
the product continuation checkpoint or establish a broad advantage over native
search. The source preview remains an experimental, local navigation utility.
No hosted index, billing, enterprise control plane or further retrieval queue is
justified by these observations.

Stop automatic benchmark/configuration loops here. Preserve the working setup,
all three coding patches, complete raw events, test results and unfinished entries.
The Codex goal's full eight-session comparison remains incomplete; publishing this
report does not make it complete. Further live work requires a separately approved
new experiment, not the seven unused slots.

A useful next business signal would be someone voluntarily using the preview on
an ordinary task, returning on another task and identifying a concrete unmet need.
No outreach is authorized here; existing issue forms accept voluntary feedback.
Independent repeat use, willingness to pay, enterprise performance and profitable
unit economics remain unobserved. No automatic new startup pivot is queued.

## Engineering validation

The corrected preview passed 15 Node tests, 20 Python study-boundary tests and a
standalone build locally on macOS arm64 with Node.js 22.19.0 and Python 3.13.0.
The generated `approve` configuration also resolved correctly and returned real
context through Codex's host API with zero additional model turns. That host check
is separate from the successful model-directed setup above. Three frozen retrieval
source hashes and every frozen study input/controller hash still match.
