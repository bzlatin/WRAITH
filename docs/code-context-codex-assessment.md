# Installed Codex assessment and preview decision

October 16, 2026. The owner authorized a source-preview PR and a bounded test of
the actual installed Codex MCP integration, tracked as a Codex goal. This follows
the [automatic-delivery study](code-context-followup.md); it does not reuse its
API budget or change its results.

**Result: the local utility works, but this assessment could not establish a new
agent benefit. Do not describe it as a validated SaaS.**

## What ran

The new workload used two historical fixes with production and test paths unused
in either earlier agent study: Hono CSS descendant combinators and Zod compiler
indent recovery. Selection used commit subjects and paths before inspecting new
production patches. Tests were copied unchanged from the upstream fixes. Both
old versions fail their regression test; both upstream fixed versions pass.
Hono runs 56 tests, including an imported shared helper. Zod runs 155 compiler
tests plus seven global-compiler tests (162 total). This is a selected subset, not either
repository's full CI or type checking. No agent patch was produced.

Initial qualification exposed two external-runner errors: treating Hono's imported
helper as a standalone suite and missing Zod source-package aliases. A subsequent
worktree-path registration error also interrupted setup. All are preserved locally.
The repaired configuration follows upstream helper exclusion and source mapping;
the same task selection and unchanged test files were retained.

The original protocol specified eight subscription sessions, two repetitions of
each task/workflow pair, a seeded counterbalanced order and a two-minute session
deadline. Native runs use native search. Context runs must call the installed
`code_context` tool before editing and may fall back to native search. This is a
comparison of instructed workflows, not voluntary tool adoption.

Three configuration attempts stopped before a development response:

| Attempt | Model | Outcome |
| --- | --- | --- |
| Configured local model | `gpt-6.1-sol` | ChatGPT account rejected model |
| Empty-config catalog default | `gpt-5.5` | ChatGPT account rejected model |
| Final catalog-listed compatibility choice | `gpt-5.4` | ChatGPT account rejected model |

Each failure consumed one of the original eight permitted session attempts.
Corrections were frozen before any agent patch or successful model response;
they did not increase that ceiling. The two repair protocols each planned six
sessions, with two Hono pairs and one Zod pair. All remaining entries in each
stopped protocol are explicitly `not_run_after_stop`; they are not additional
attempts. Five shared slots remain unused and are **closed**, not reusable credit.
No further model substitution, automatic retry or recurring live run is scheduled.

`codex login status` reported ChatGPT sign-in. Every execution forced ChatGPT
authentication, ignored user configuration/rules, disabled web/nested agents and
used a clean environment without provider keys. No API-key benchmark was invoked.
Codex returned no completed-turn token usage, so cost and quota consumption are
unknown; missing usage is not evidence of zero cost. The built-in model catalog
proved insufficient to establish this account's model eligibility.

There were **zero completed development sessions, zero Wraith MCP calls in these
live attempts and no new speed, token or task-success comparison**. Do not combine
these errors with the earlier API study to claim a win. The local raw events,
qualification records, drafts, patches and started/not-run records remain ignored;
the [sanitized result](../experiments/code-context/study/codex-results.json) and
three frozen protocols are public.

## What is supported

The [preview checks](code-context-preview.md) establish local source installation,
the offline demo, real MCP calls, citation/freshness controls and removal behavior.
An installed Codex server-startup check discovered all three tools without a model
turn. These are technical integration checks. They do not prove a coding agent uses
the tool effectively, that a developer saves time, or that a team will pay.

The older automatic-delivery experiment still provides bounded evidence: all six
agent patches passed selected tests, and context used 19 versus 28 model requests.
Its median-cost continuation rule was not met. That study injected initial context;
it did not test the preview's optional MCP workflow.

## Investment decision

Publish the honest free source preview through a scoped PR. Keep accounts, billing,
hosted indexing and further retrieval features paused. No new binary/npm release
or customer outreach is part of this goal. An unsuccessful comparison is a reason
to narrow the claim, not to add another benchmark until one wins.

Before another live comparison, establish a working subscription CLI model outside
a product-performance claim and authorize a new finite experiment. Preserve these
failures. The technical comparison remains unresolved; do not treat an unavailable
model as either a retrieval defect or proof that retrieval helps.

Business progress requires voluntary independent use, return use on another task
and a concrete paid commitment, as specified in the [preview decision](code-context-preview.md).
No observation window has begun: independent users and paid commitments remain
zero. Automated fixtures cannot supply those observations.

Local CPU operation avoids a model/GPU service in the retrieval path. It does not
establish performance on enterprise repositories, permission isolation, availability,
support cost or profitable unit economics. Enterprise scaling and revenue remain
unproven. Do not promise unlimited usage or build a hosted service from these tests.

## Publication and CI

[Source-preview PR #5](https://github.com/bzlatin/WRAITH/pull/5) is open on
`codex/context-source-preview`, based directly on `main`. It excludes the older
unmerged ingestion implementation and financial experiment. At source commit
`e4968f1979cc94c9e0a16a055895998041217b59`, the
[push CI run](https://github.com/bzlatin/WRAITH/actions/runs/38977555527) passed:

- Node preview tests and bundle build on Linux, macOS and Windows.
- Python study-boundary tests on Linux/macOS; this POSIX controller is skipped on Windows.
- Existing Rust build/test/packaging checks, MSRV and workflow lint.

Locally, the exact publication worktree passed 15 Node tests, 14 Python study tests,
a fresh locked dependency install and bundle build. Its Markdown links and privacy
pattern scan passed. A local invocation of the older Rust packaging tests could not
run without a built Rust binary/toolchain in this checkout; the successful native
CI jobs supply that verification. No new release was published. These engineering
results do not resolve the blocked development-benefit comparison or commercial demand.

The Codex goal remains active while the actual development comparison is incomplete.
Finishing packaging and writing this assessment does not satisfy that requirement.
