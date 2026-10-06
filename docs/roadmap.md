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

The remaining product priorities are:

1. **Dogfood the core loop.** Use a real, independently useful agent with a small
   scenario suite. Change prompts, tools, or retrieval; capture a regression that
   would be tedious to find manually. Fix installation, configuration, and report
   friction found during this exercise. Synthetic demos remain test fixtures.
2. **Validate distribution and CI.** Run the native OS matrix, inspect packaged
   binaries, and verify the README install-to-comparison path. When the owner
   authorizes publication, bootstrap workflows onto the default branch, select a
   distribution license, and inspect the draft release before promotion. GitHub
   Actions is the first distribution integration; measure real PR use.
3. **Pilot and choose the next feature.** Have roughly 5–10 AI developers try Wraith
   against their own agents. Record setup blockers, misleading gates, missing
   diagnostics, and voluntary reports of repeat use. Prioritize the strongest
   repeated problem rather than implementing every suggested extension.

Potential follow-on work is conditional:

| Observed problem | Candidate response |
|---|---|
| Sample noise causes misleading or inconclusive gates | Statistical decision policy with minimum samples, effect sizes, explicit tests, and multiple-test handling |
| Existing checks cannot express important regressions | Additional or custom evaluators |
| Adapter boilerplate blocks adoption | Thin Python/TypeScript instrumentation SDKs |
| Scenario authoring blocks useful coverage | Scenario generation experiments |
| Production failures are hard to reproduce | Trace ingestion and replay experiments |
| Teams miss useful findings during review | Richer PR reporting |
| Repeated team use requires shared history or governance | Optional collaboration and enterprise features |

Statistical gating was implemented at the owner's explicit request in v0.3. Further
statistical methods should follow evidence from live agent use. The policy
must preserve the strict observed-rate option and distinguish inconclusive evidence
from a passing gate. Timelines, pricing, and monetization remain hypotheses.

Keep provider integrations, hosted history, and replay at replaceable boundaries.
