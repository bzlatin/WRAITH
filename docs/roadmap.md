# Directional roadmap

Priorities follow observed developer needs, not a fixed feature ladder or release
calendar. See [product-direction.md](product-direction.md) for the validation goal.

The v0.2 local implementation now includes cancellation, Windows Job Objects,
release packaging, exact-commit baseline/PR workflows, trusted-policy comparison,
exact argument/document gates, schema migration, and repeated-run aggregation.
The v0.3 implementation adds the offline RAG pilot, configurable statistical gating,
Apache-2.0 licensing with dependency notices, and native archive smoke tests.
The owner has authorized bootstrapping these workflows on `main`; native results
are available in GitHub Actions. Release publication remains a separate step.

The v0.4 integration adds structured-output contracts and a live smoke comparison
against Push / Pull’s actual workout generation pipeline. Four baseline/candidate
cases passed within eight provider calls; offline tests detected 50/50 injected
failures. A useful natural regression and repeat adoption remain unproven. See
[structured-output.md](structured-output.md).

The v0.5 implementation reduces setup with Python/TypeScript function adapters,
guided initialization, diagnostics, `baseline`/`check`, local HTML reports/history,
reviewed case import, and generated offline PR CI. A native installer is verified
locally. Pinned PydanticAI and LangGraph examples exercised real orchestration and
caught six controlled regressions without live model calls. v0.5 remains unpublished;
its native matrix and distribution availability still need validation.

The remaining product priorities are:

1. **Dogfood the core loop.** Use a real, independently useful agent with a small
   scenario suite. Change prompts, tools, or retrieval; capture a regression that
   would be tedious to find manually. Fix installation, configuration, and report
   friction found during this exercise. Synthetic demos remain test fixtures.
2. **Validate distribution and CI.** Repeat the native matrix and packaged-binary
   checks for new increments, then measure real project PR use. Default-branch CI
   and Apache-2.0 licensing are in place. Inspect the draft release before any
   owner-authorized publication. GitHub Actions is the first distribution integration.
3. **Pilot and choose the next feature.** Have roughly 5–10 AI developers try Wraith
   against their own agents. Record setup blockers, misleading gates, missing
   diagnostics, and voluntary reports of repeat use. Prioritize the strongest
   repeated problem rather than implementing every suggested extension.

Potential follow-on work is conditional:

| Observed problem | Candidate response |
|---|---|
| Sample noise causes misleading or inconclusive gates | Statistical decision policy with minimum samples, effect sizes, explicit tests, and multiple-test handling |
| Existing checks cannot express important regressions | Additional or custom evaluators |
| Existing function adapters miss common framework hooks | Extend adapters from observed integration gaps |
| Reviewed case import still leaves scenario authoring difficult | Scenario suggestion experiments with explicit review |
| Production failures are hard to reproduce | Trace ingestion and replay experiments |
| Teams miss useful findings during review | Richer PR reporting |
| Repeated team use requires shared history or governance | Optional collaboration and enterprise features |

Statistical gating was implemented at the owner's explicit request in v0.3. Further
statistical methods should follow evidence from live agent use. The policy
must preserve the strict observed-rate option and distinguish inconclusive evidence
from a passing gate. Timelines, pricing, and monetization remain hypotheses.

Keep provider integrations, hosted history, and replay at replaceable boundaries.
