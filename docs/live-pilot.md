# Capped live-agent evaluation

This source-checkout experiment uses a real model to choose tools and generate final
JSON answers in a synthetic support application. It adds model behavior to the
previous offline workflow checks. It is not a production deployment or an
independently maintained application's development queue.

## Prepare without provider calls

Build the current source (reviewed initialization is not in published v0.5.0):

```sh
cargo build --workspace --locked
python3 -m unittest discover -s scripts/tests -p test_live_agent.py
python3 scripts/live-pilot.py --root .wraith/live-support prepare
```

Set `OPENAI_API_KEY` in your existing environment before preparation; do not put it
in files or commands committed to the repository. Doctor checks presence without
printing its value. The project stores only the credential variable name and pinned
model label. The API endpoint is fixed to `api.openai.com`; redirects are rejected.

The runner freezes the ten reviewed cases, both prompt versions, adapter source,
native binary, and project policy before execution. The candidate is a shorter
prompt intended to preserve the same tool, ownership, approval, evidence, and
citation rules. No fault is deliberately introduced. Cases remain unchanged even
if the model fails them.

## Run only with explicit authorization

```sh
python3 scripts/live-pilot.py --root .wraith/live-support run --allow-live
```

Authorize the cost and request cap before running. **One native 40-request budget
covers baseline plus candidate, including failed HTTP attempts.** Each scenario
uses at most two attempts: model tool selection, then final JSON generation from
real local tool results. No HTTP/SDK retries occur. The pinned model is
`gpt-4.1-mini-2025-04-14`; observed provider model names and token usage are saved.
Cost is not inferred from token counts or changing price tables.

The baseline uses native `baseline --allow-live --max-requests 40`; the candidate
uses `check --allow-live` against its fixed baseline and original budget. No new
budget is created by check. A provider error writes a stop marker before later
scenarios can make more requests. The attempt marker and native budget remain
preserved after failures or interruption. The runner refuses another invocation
on the same attempted root. A fresh root requires separately authorized new
experiment spending; it is not an automatic retry mechanism.

Inputs are synthetic. Policy retrieval and order lookup run locally. Approval and
customer ownership are enforced by the application before a refund action; model
text cannot authorize it. The refund action writes an in-memory receipt only.
The API receives the synthetic prompts/tool results with `store: false`; that
setting is not a claim that provider processing or retention rules cease to apply.

## Inspect and interpret results

Open `.wraith/live-support/report.md`. Native JSON/HTML, the accepted baseline,
shared budget, cases, prompt versions, binary hash, and runner copy remain under
that ignored directory. Original decisions and failures are retained. The budget
counter is authoritative if an execution error lacks completed adapter metadata.
Never publish credentials or raw private application runs.

There is **one independent observation per case per version**. A passing comparison
means no new configured failure was observed. It does not establish statistical
non-regression, a production accuracy rate, or a causal prompt effect. A new failure
requires review against the actual tool/answer evidence; it may reflect model
variability. Existing deterministic unit tests validate budget and authorization
mechanics separately and are not live-model quality evidence.

Recorded setup effort excludes the earlier application/example authoring and
case design. Keep those costs explicit when assessing value. Use
[verification](verification.md) for published results and
[commercial assessment](commercial-assessment.md) for the separate buyer hypothesis.

## Observed results

The authorized run consumed exactly **40 provider attempts**, 20 per version, with
no retries or execution errors. Both versions passed **3/10 original contracts**.
The candidate check exited 0 because there was no new configured failure relative
to an already-failing baseline; it did not mean the application was correct.

Review found six wording-related contract failures: correct policy/order values
were returned inside sentences, and the approval-denial decision used different
wording. The original atomic-string equality rules were too restrictive for those
human-facing answers. Those rules and results remain unchanged. A separate
post-run policy review may inspect them but cannot be presented as a new live run.

One substantive workflow failure affected the approved refund in both versions:
the model selected order lookup, no refund action executed, and no receipt existed.
The candidate nevertheless stated that the refund was processed. Wraith's required
tool and receipt-count checks failed. The two-request orchestration allowed only
one tool-selection step before final generation, so an order-lookup-first path
could not subsequently execute a refund. This is an example-application failure,
not an independently discovered customer bug or evidence that the prompt change
caused it. The existing baseline failure explains the passing comparison.

[Sanitized per-case observations](evidence/live-support.json) retain the synthetic
answers, executed-tool names, and failed requirements without credentials or local
paths. One observation per case does not support a production accuracy estimate.
