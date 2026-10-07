# Report design

A report should answer what broke and why, then let the reader inspect the recorded
evidence. It is a standalone engineering document, generated from saved results.

## Reading order

1. Outcome, scenario/sample scope, and provenance.
2. Failed expectations with expected and observed values.
3. Baseline/candidate outputs and recorded activity, in native expandable disclosures.
4. Passing scenarios, measured performance, and local history links.

Use explicit status words alongside color. Display missing metrics and inconclusive
evidence clearly. Escape application strings and wrap long output. Reports contain
no scripts, remote fonts, or other remote resources.

## Layout and interaction

Native fonts, thin rules, and quiet JSON backgrounds keep the evidence readable.
Two evidence columns collapse below 640px. Links and disclosures support keyboard
focus; reduced-motion preferences disable the brief disclosure animation.
[DESIGN.md](../DESIGN.md) contains the tokens and component rules.

## Validation

Review real passing and failing reports at desktop and mobile widths, with an open
output disclosure. Check failure ordering, escaped hostile strings, unavailable
metrics, keyboard operation, and horizontal overflow. A passing report describes
configured checks on its scenarios; it does not claim overall model quality.
