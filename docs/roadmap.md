# Roadmap

Priorities follow [product validation](product-direction.md), without a fixed release calendar.

## Local code-context preview

The owner authorized a separate [source preview](code-context-preview.md) under
`experiments/code-context/`, one installed Codex MCP comparison, and a public PR.
The retrieval tool works locally; prior studies did not meet their continuation
threshold. Preserve those results. Independent repeat use and paid demand remain
unknown. The [installed Codex study](code-context-codex-assessment.md) stopped on
account/model errors before coding. Keep the free utility available; do not build a hosted service or add
features to avoid the adoption decision. Existing Rust release contracts stay fixed.

## Available in v0.5

- Python/TypeScript function adapters, guided setup, and `doctor` diagnostics.
- Fixed baselines, checks, local HTML reports, immutable history, and reviewed case import.
- Text, structured JSON, tool, retrieval, resource, and optional exact-trace checks.
- Repeated samples and statistical gates with explicit inconclusive decisions.
- Opt-in live experiments with a shared budget for instrumented provider attempts.
- Native installation and generated offline GitHub PR checks.

See [verification](verification.md) for native release and controlled-fixture results.

## Next priorities

1. **Use a real agent during real changes.** Catch a useful natural regression and
   fix integration or report friction revealed by the exercise.
2. **Repeat the workflow on independent projects.** Learn which checks are useful,
   where false alarms occur, and whether developers keep running them in CI.
3. **Address the strongest recurring gap.** Select the next improvement from evidence
   rather than adding integrations or evaluators for their own sake.

| Observed need | Possible response |
| --- | --- |
| Common framework activity is hard to record | Targeted adapter hooks |
| Important output contracts cannot be expressed | Additional evaluators |
| Sampling produces too many uncertain decisions | More efficient statistical methods, retaining honest uncertainty |
| Production failures are difficult to reproduce | Trace import and replay experiments |
| Creating useful cases takes too much effort | Better reviewed case authoring |
| Reviewers miss findings in CI artifacts | Clearer PR reporting |
| Teams repeatedly need shared history | Optional collaboration features |

Provider logic stays outside the core. New releases should repeat native tests and
archive checks before publication. Live-model accuracy and repeat adoption remain
unproven; neither is implied by the controlled demos.
