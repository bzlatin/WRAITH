# Code context: retrieval and automatic delivery

October 16, 2026. A bounded follow-up authorized by the owner after reviewing the
[original experiment](code-context-study.md). It tests whether supplying task
context automatically helps an agent make correct changes. It does not authorize
a hosted service, launch, external outreach or recurring model spending.

## What needed fixing

The original candidate agents never called `code_context` in any of the three
tasks. They called `code_symbols` once in total and never called `code_references`.
This is evidence of poor optional-tool adoption in that harness. It is insufficient
to judge the main retrieval method's contribution. The original commercial
continuation threshold was not met, but a definitive rejection of retrieval quality
from those live results alone was too strong.

An offline audit found concrete weaknesses too. Common names outranked the
identifier in the task, long functions always returned their first forty lines,
and only the first few anonymous test matches were considered. Correct citations
can still cite the wrong code.

The revised retrieval keeps whole identifiers and their camel/snake-case pieces,
weights words by their frequency across source files, and ranks overlapping source
windows with enclosing syntax names. It searches late test blocks and suppresses
overlapping hits. It remains lexical/syntax retrieval; there are no embeddings,
model calls, compiler-resolved references or complete coverage guarantees.

## Comparison rules

[Tasks](../experiments/code-context/study/followup-tasks.json) and
[protocol](../experiments/code-context/study/followup-protocol.json) were frozen
before the retrieval changes. Three historical fixes use different production
and test modules from the original study: Hono precompressed responses, Zod
memoizer retention and tRPC lazy-router path boundaries. Selection used commit
subjects and changed-path metadata, with no task replacements after qualification.
These remain source-guided historical reproductions, not prospective discoveries.

Both lanes receive the same task, approved production/test paths, native tools and
model snapshot. The context lane receives one automatically generated, task-only
bundle before its first model request. It does not receive witness ranges, the
upstream production fix or its diff. Both lanes can read the same unchanged
acceptance tests, including the regression tests from the historical fix.

The file-reading interface now uses `start` and `count`, with explicit limits and
continuation lines. Both lanes get up to thirty provider attempts and three requested
test runs plus final verification. Initial context generation counts in machine
time, and its serialized input counts in provider token usage. Worktree setup is
reported separately. This measures automatic initial delivery, not voluntary MCP
adoption or a comparison against current Serena.

The owner separately approved **180 total requests**, including failures, for
experiment `code-context-delivery-2026-10-16`. The original budget is untouched.
No automatic retries, budget resets or replays are allowed. Frozen source hashes,
controller hashes, input bundles, model responses and every run remain under
ignored `.wraith/code-context-study/context-followup-2026-10-16/`.

Before live execution, each old production version failed its selected unchanged
test file and each upstream fixed version passed: Hono 40 tests, Zod 43, tRPC 7.
These use the existing external Vitest configuration, not full upstream CI or
type checking. All six qualification checks completed locally.

Offline retrieval scores report file hits, intersections with historical diff
hunks and exact citation validation separately. Hunk intersection is a proxy:
it does not prove that an entire fix, assertion or necessary context was supplied.
Insertion-only old-code hunks use the adjacent old line as an explicit proxy.
The original tasks are development diagnostics. The revised candidate was frozen
before querying the new tasks; no tuning follows those results.

## Results

Both approaches passed all three selected test files. Every model run finished
before its request limit, and there were no tool errors. All 47 provider attempts
completed; the unused 133 requests remain unused and are not a new budget.

| Task | Requests: native / context | Estimated cost: native / context | Seconds: native / context |
| --- | --- | --- | --- |
| Hono precompressed responses | 11 / 8 | $0.02235 / $0.02037 | 19.929 / 24.118 |
| Zod memoizer retention | 9 / 6 | $0.01615 / $0.01609 | 21.546 / 15.817 |
| tRPC lazy-router boundary | 8 / 5 | $0.01406 / $0.00836 | 12.301 / 14.933 |

The context lane used **19 requests versus 28**, with identical selected test
completion. Its total estimated provider cost was **$0.04482060 versus $0.05255775**,
14.7% lower. Its median estimated cost was **$0.01609425 versus $0.01614780**,
only **0.33% lower**. Costs use provider-reported cached/uncached input and output
tokens with the dated [official rates](https://developers.openai.com/api/docs/pricing);
they are list-price estimates, not reconciled bills or guaranteed future savings.
All six runs together were estimated at $0.09737835.

The time column includes initial retrieval and the final test run, excluding
worktree setup. Context generation took 1.4–1.9 seconds. Two tasks took longer
with context, one took less time; total observed time was 54.868 seconds with
context and 53.776 without. No human-effort savings were measured.

Offline, the original diagnostic tasks went from **1/4 to 3/4 production hunk
intersections**. The different fresh tasks went from **1/13 to 4/13**. All returned
citations matched their source hashes and exact line text. The revised retrieval
still missed most fresh production hunks and the tRPC regression-test file. These
are intersections with historical diff ranges, including nonessential changes;
they are not percentages of a complete fix or an accuracy score. File-level hits
alone would have hidden the missing context.

[Sanitized evidence](../experiments/code-context/study/followup-results.json)
includes every run, token accounting, optional-tool usage from the original
experiment, retrieval metrics, and the frozen source/controller hashes. Original
results and the intermediate offline tuning attempts were preserved locally.

## Decision

All three pairs must qualify and complete. Require no reduction in accepted task
count and at least 20% lower median estimated provider cost over the same jointly
passed task pairs, with at least two such pairs. Failed tasks stay visible and do
not count as cheap successful work. Machine timing is secondary. This small-sample
rule is an internal investment checkpoint, not statistical significance, accuracy
equivalence or evidence of paid demand.

**The continuation threshold was not met.** Automatic context reduced model
round-trips in these observations and improved retrieval coverage. This is a
specific technical benefit, rather than proof that the code has no use. The
predeclared median-cost improvement was absent, and runtime did not improve
consistently. One observation per task cannot establish a reliable future saving.

Keep the prototype available as a local utility. Stop this bounded investment;
do not extend it with another tuning/benchmark cycle or a SaaS build. The result
does not establish independent demand, repeat adoption or willingness to pay.
Any later commercial decision needs new evidence from an actual recurring user
problem, rather than another automatically generated feature queue.

## Run locally

The [prototype README](../experiments/code-context/README.md) covers ordinary use.
Those commands need no model provider. The study's offline setup, from the root:

```sh
python3 experiments/code-context/study/prepare.py --install-tests
python3 experiments/code-context/study/context_followup.py prepare \
  --output .wraith/code-context-study/your-new-preparation
```

Preparation clones pinned public code through the existing setup script, installs
optional test dependencies, freezes the candidate and qualifies the unchanged
upstream files. It makes no provider calls. Preserve existing output directories.
The study controller requires POSIX process groups; ordinary prototype support is
separate. Live execution needs a separately approved experiment and request cap;
copying this command or having an API key is not spending authorization.

Validation on macOS arm64 with Node.js 22.19.0 and Python 3.13.0: 11 prototype
tests, 10 study-boundary tests, the standalone bundle and the six upstream
qualification checks passed. Linux/Windows and GitHub CI were not executed here.
The Rust engine was not changed for this follow-up.
