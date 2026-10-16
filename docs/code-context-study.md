# Code context: implementation and comparison

October 16, 2026. The owner authorized the complete bounded plan in
[the recommendation](startup-recommendation-2026-10-16.md), then explicitly approved
a fresh shared cap of 180 model requests. The local implementation and finite
comparison are complete. **The commercial continuation threshold was not met.**

A separately authorized [retrieval and automatic-delivery follow-up](code-context-followup.md)
diagnosed optional-tool non-use, fixed concrete retrieval weaknesses and tested
three different tasks. It reduced model requests but did not meet its median-cost
continuation threshold. The original evidence below remains unchanged; the current
prototype includes the later retrieval changes and has different source hashes.

Keep the prototype and evidence. Do not build a hosted service, add more features
to rescue this result, or market measured task-cost savings from this experiment.
The result does not prove that code-context products are useless; it does not
justify further investment in this implementation under the agreed checkpoint.

## What was implemented

[The separate Node.js prototype](../experiments/code-context/README.md) provides:

- A read-only CLI and a stdio MCP server for TypeScript/JavaScript Git checkouts.
- Syntax definitions, ranked task snippets, candidate tests and lexical occurrences.
- Source hashes and line citations, bounded snippets and explicit omissions.
- Relative import resolution within indexed source; external imports remain unknown.
- Content-addressed syntax reuse with separate worktree and dirty-content identities.
- Refresh on edits, branch switches, renames and deletions; stale citation errors.
- Limits and diagnostics for unreadable/oversized sources, syntax errors and caches.
- A standalone JavaScript bundle, dependency notices, instructions and CI wiring.

The tool does not call models or execute project scripts to index code. It uses the
TypeScript parser and official MCP SDK; it is not a new Rust CLI command. References
remain lexical candidates. There is no complete call graph, compiler type checking,
remote semantic search or atomic repository-wide filesystem snapshot.

Nine Node tests and four Python benchmark-boundary tests pass on macOS arm64.
They cover dirty worktrees, refresh, citation races, ignored/private paths, symlinks,
cache corruption, size limits, byte budgets, the official MCP client and persistent
request reservation. The symlink control is skipped on Windows; Windows execution
has not been verified. CI wiring does not establish a successful GitHub run.

The bundle was copied to a temporary directory without runtime npm packages and
successfully found a definition in the pinned Hono checkout. It requires Node.js
22.12+ and Git; it is not a native executable. No release or package was published.

## Frozen sources and comparison

[Protocol](../experiments/code-context/study/protocol.json) and
[historical tasks](../experiments/code-context/study/agent-tasks.json) were frozen
before candidate development. The public repositories are Zod, tRPC and Hono,
pinned to full commits. Serena is pinned to source commit
`d9e4c796fae0207ba6848d1df4b331122a5567b5` (package metadata 2.0.1.dev0).

Initial setup failures remain in the local evidence. Sandbox DNS blocked source/
language-server downloads; authorized network access allowed installation. Serena
auto-selected Vue in tRPC; a separately recorded TypeScript-only configuration
completed the comparison on the intended scope. These environment/configuration
failures are not candidate quality wins. Subsequent Serena runs disabled its usage
reporting. The initial upstream default attempted reporting through blocked networking.

Current configured Serena successfully completed all three initial symbol/pattern
lookups. Native ripgrep also found the selected symbols quickly. The candidate's
warm lookups reused syntax for 509 Zod, 906 tRPC and 439 Hono source files without
reparsing. All queries still enumerate/read/hash files; this is not evidence that
filesystem work or a whole agent task disappeared.

Six deliberately conflicting dirty-worktree observations—two per repository—passed
for **all three approaches**. This validates the control and shows that checkout
isolation is already served by the tested baselines. It is not a discovered defect
or a unique product advantage. The candidate unit test separately verified shared
syntax reuse and distinct checkout/content identities.

Sourcebot and Augment were not benchmarked. Docker was not available for the
Sourcebot setup, and no Augment account or paid access was created. Their documented
offers remain competitive context, not defeated baselines. REA was unnecessary for
these open-source targets and was not installed or run.

## Live task results

The same `gpt-5.4-mini-2026-03-17` snapshot, low reasoning, shared basic tools and
15-request-per-task limit were used in nine runs. The three tool lanes were native
file search, Serena's read tools, and the candidate's read tools. Run order was
counterbalanced across repositories. Tool schemas differ, so this compares the
complete configured tool choice, not retrieval algorithms in isolation.

Each task reproduces a **known historical fix**. Its full selected upstream test
file remains unchanged and hash-checked. The old code fails, and the upstream fixed
code passes, before any live task is attempted. These are source-guided historical
reproductions, not naturally discovered regressions or independent developer use.

| Historical task | Native search | Serena | Candidate |
| --- | --- | --- | --- |
| Hono regex parameters in `basePath()` | Failed | Passed | Failed |
| Zod union rejection from checks | Failed | Failed | Failed |
| tRPC premature JSONL stream closure | Passed | Failed | Passed |
| Selected acceptance files passed | **1/3** | **1/3** | **1/3** |

Seven runs exhausted the request limit. Hono/Serena had a passing edited file at
the limit, so its acceptance is still counted as passed. Incomplete attempts are
retained in the denominator. The short cap and single observation per task do not
establish general success rates, statistical equivalence or model capability limits.

On the only task both native search and the candidate passed, their observed
task-loop-plus-final-check times were **19.358 s and 20.303 s**, respectively. The
candidate was not faster in that observation. Standard-list-price estimates were
**$0.025893 and $0.028860**, respectively; the candidate was not cheaper there either.
These are observations, not causal performance estimates. Startup is reported
separately, and no human-effort savings were measured.

Candidate runs that failed sometimes ended sooner or used fewer tokens. Failed
work is not a demonstrated efficiency gain. Nor does equal aggregate completion
hide the fact that Serena passed a task the candidate failed.

**135/180 requests were reserved and completed; zero automatic provider retries.**
Total estimated standard-list-price token cost was **$0.273658**. This estimate uses
provider-reported input, cached-input and output tokens with the published
[OpenAI rates](https://developers.openai.com/api/docs/pricing); it is not a reconciled
bill. No remaining capacity was used to tune or rerun the completed experiment.
[Sanitized results and rates](../experiments/code-context/study/results.json).

## Qualification and evidence limits

The selected tests run under explicit external Vitest configuration, not full
repository CI or TypeScript checking. Hono uses Vitest 5.0.1; Zod uses 4.1.5.
tRPC uses 5.0.1 with its upstream `printBasicPrototype`/mock-reset settings and
SuperJSON 1.13.3 matching its declared dependency range. The selected test code was
never changed. Earlier attempts with a missing dependency, different serializer/
snapshot defaults or blocked HTTP sockets are retained as setup failures.

tRPC's unchanged tests start temporary HTTP servers. Their child environment does
not include the provider key. Agent edits are restricted to each task's approved
production module; test hashes are checked before and after execution. The live
controller reserves each request durably before attempting it, including failed
or interrupted requests. Provider credentials and environment dumps are not saved.

Raw sources, complete attempts, model responses, patches and input manifests remain
in ignored `.wraith/code-context-study/`. Public results omit machine paths,
credentials, private app data and account identifiers. The candidate source hashes
are retained so the tested version cannot silently become a later tuned version.
Process-tree RSS could not be measured under the host permissions; it is unknown.

The study controllers require POSIX process-group containment; they are not Windows
benchmark runners. After the completed live comparison, test-process cleanup was
hardened to terminate descendants on timeout/interruption. The original results
remain untouched. This controller cleanup does not change the candidate's frozen
retrieval implementation or establish an additional comparison result.

## Reproduction and ordinary use

For ordinary use, follow the [short tool README](../experiments/code-context/README.md).
From the repository root, optional study preparation is:

```sh
python3 experiments/code-context/study/prepare.py --install-serena --install-tests
```

This downloads pinned public code and installs dependencies; it does not call a
model. `serena_baseline.py` requires `--attempt NAME` and preserves prior evidence.
`candidate_baseline.py` and `worktree_compare.py` refuse an existing output directory.
`acceptance.py` uses the pinned historical files and preserves attempts.

The live controller is a finite experiment, not a recurring automation. Its existing
budget belongs to the completed experiment and may not be reset or reused. Of the
180 authorized requests, 135 were used; the remaining capacity was left untouched.
A new live study requires explicit authorization, a new identity, frozen tasks and
an independently recorded budget. Replaying old output is not new evidence.

## Product decision

The plan required a material end-to-end advantage without observed loss of accepted
task completion before more investment. This candidate did not demonstrate that
advantage. **Stop at the local prototype.** No hosted indexes, team accounts,
enterprise control plane, payment integration, outreach or public launch was added.

The proposed commercial prices remain hypotheses. There are no independent repeat
users or paid commitments. Do not respond to this result with another feature queue
or automatically create another startup pivot. A specific new user requirement or
separate investment decision is needed to reopen the work.
