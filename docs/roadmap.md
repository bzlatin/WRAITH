# Roadmap

Priorities follow [product validation](product-direction.md), without a fixed release calendar.

## Available in v0.5

- Python/TypeScript function adapters, guided setup, and `doctor` diagnostics.
- Fixed baselines, checks, local HTML reports, immutable history, and reviewed case import.
- Text, structured JSON, tool, retrieval, resource, and optional exact-trace checks.
- Repeated samples and statistical gates with explicit inconclusive decisions.
- Opt-in live experiments with a shared budget for instrumented provider attempts.
- Native installation and generated offline GitHub PR checks.

See [verification](verification.md) for native release and controlled-fixture results.

## Current source improvements

The source build adds reviewed batch import and initialization, explicit input-only
functions, typed case-authoring flags, per-case expectation diagnostics, and report
context with comparison failures first. These are not in the published v0.5.0
binary. See [faster setup](first-use.md) and [coverage results](coverage-challenge.md).

The source also adds [native CI comparison and bounded offline jobs](workflow-value.md).
These reduce measured run time and custom workflow scripting; v0.5.0 does not
include them.

## Current decision

[Narrow the scope and pause expansion](product-assessment.md). The engine is usable;
additional workflow value and demand remain unproven. The latest
[weather comparison](weather-comparison.md) found equal control detection with
ordinary tests and higher machine runtime for Wraith in the measured setup.

A bounded [public issue audit](public-issue-audit.md) also found no repeated unmet
workflow that justifies a new integration. Post-evaluation trace access is a lead,
not an approved feature or evidence of paid demand. The research step is complete;
there is no further automated validation queue to wait for.

Continue compatibility, reliability fixes and clear documentation. Keep Wraith
local and framework neutral. Existing tests should supply requirements and helpers
where possible; avoid maintaining duplicate application test logic.

## Conditions for the next feature

1. Identify a concrete, repeated review or CI need that existing tests do not meet.
2. Record the benefit and added setup, runtime and maintenance. Review a useful
   natural catch against the actual requirement when one occurs.
3. Implement the smallest change justified by that gap, then validate it in the
   same workflow. Do not add another research framework to manufacture evidence.

A passing synthetic queue, download count or feature list is insufficient. New
releases still require native tests and archive checks before publication. Hosted
features and billing remain deferred. With independent feedback deferred, Codex
can establish engineering behavior but cannot establish adoption or paid demand.
