# Commercial assessment

Wraith has demonstrated a useful technical workflow: preserve explicit agent
contracts, compare a change against a fixed baseline, and retain a report that
explains a failure. A real historical approval bug reproduced across unmodified
upstream revisions; later calibration improved scenario coverage. See
[verification](verification.md). This is enough to demonstrate the mechanism.
It is not evidence of customer adoption, willingness to pay, or revenue.

## Market evidence

Public offers reviewed on October 14, 2026:

| Product | Public offer | Implication for Wraith |
| --- | --- | --- |
| [Promptfoo](https://www.promptfoo.dev/pricing/) | Free local/self-hosted evaluations and integrations; custom enterprise/on-premise plans include services and support | Local execution and CI are not unique differentiators. A basic testing CLI competes with a strong free alternative. |
| [Braintrust](https://www.braintrust.dev/pricing) | Free tier, Pro listed at $249/month plus usage, custom enterprise plans | Teams are offered a paid combination of evaluation infrastructure, controls, and support. This is an advertised offer, not proof they would buy Wraith. |
| [LangSmith](https://www.langchain.com/pricing) | Free developer tier, Plus listed at $39/seat/month plus usage, custom enterprise hosting/security/support | Commercial products bundle team operations and ongoing services around evaluation. Wraith currently covers a narrower local workflow. |

Prices and packaging can change; consult each source before making comparisons.
These are vendor statements, not audited revenue figures. Wraith has no verified
paid customers. The plausible opportunity is an inference from these offers and
the integration work encountered in Wraith's pilots.

## A focused offer to test later

**Buyer hypothesis:** a small engineering team shipping tool-using agents, with
frequent changes and explicit approval, data-access, or structured-output rules.
An engineering lead owns the release check and can authorize integration work.

**Problem hypothesis:** the team has application tests but lacks a maintained set
of representative end-to-end agent contracts and reviewable evidence on PRs.
The offer must save setup or diagnosis work; another executable alone is weak.

**Initial offer hypothesis:** a fixed-scope agent regression setup delivered into
the team's own repository. Keep the Apache-2.0 CLI free. Charge for optional
integration, reviewed contract design, CI setup, and maintenance support if a buyer
actually requests them. No license change, account system, or hosted data store is
needed to test that offer.

An illustrative pilot could include one adapter, a small agreed set of important
workflows and negative cases, an offline PR gate, before/fail/fix evidence, and
handover documentation. A possible price to test is **$1,000 for that pilot**,
with model/infrastructure charges agreed separately. This is an unvalidated
proposal, not Wraith's published price, a quote, or an earnings forecast. Keep
scope bounded and measure delivery effort before offering ongoing support.

For illustration only, a $1,000 pilot with six delivery hours at an assumed
$100/hour internal cost and $50 of direct expenses leaves $350 before acquisition,
administration, taxes, and other overhead. Twelve hours at the same assumed costs
loses $250. These are arithmetic scenarios, not measured Wraith costs. Track Codex
usage and human review/support effort before claiming a viable margin.

Codex can implement much of the delivery. It cannot establish the buyer's
requirements or a contract by simulating a purchaser. No outreach or sales message
has been sent; external validation remains deferred at the owner's request.

## Evidence required before calling this a business

1. A real prospective buyer identifies a costly workflow problem and reviews a
   report from their own code. An agent-generated approval is not buyer evidence.
2. Someone with purchasing authority accepts a paid pilot, or pays for the agreed
   deliverable. Interest, stars, downloads, and competitor prices are weaker signals.
3. The pilot delivers the promised workflow with recorded setup/support effort and
   customer-approved acceptance criteria. Count model and infrastructure costs.
4. A customer continues using the check during later changes and requests renewal
   or additional work. Measure repeat use voluntarily, without default telemetry.

Until then, describe Wraith as technically demonstrated with a commercial
hypothesis. Do not say product-market fit, proven ROI, production accuracy, or
proven recurring revenue. Keep the public README about the working tool rather
than the hypothetical paid offer.

## Current decision

Continue improving integration and report friction that has been observed. The
[assisted first-use benchmark](first-use.md) tests concrete setup improvements.
Stop using more seeded defects as evidence of demand. Live-model quality needs a
separate budget and representative evaluation; customer demand eventually needs
a real commercial decision. Neither should be silently substituted for the other.
