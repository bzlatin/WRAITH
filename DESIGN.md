---
name: Wraith local reports
description: Compact evaluation evidence for developers reviewing agent changes
colors:
  paper: "#ffffff"
  ink: "#17212b"
  muted: "#495765"
  line: "#d8dee5"
  quiet: "#f5f7f9"
  pass: "#18623b"
  failure: "#a82424"
  warning: "#775400"
  link: "#175c98"
typography:
  title:
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
    fontSize: "32px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  body:
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
    fontSize: "16px"
    lineHeight: 1.6
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "13px"
    lineHeight: 1.55
rounded:
  code: "6px"
spacing:
  group: "12px"
  evidence: "20px"
  section: "24px"
components:
  evidence-block:
    backgroundColor: "{colors.quiet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.code}"
    padding: "16px"
---

## Overview

**A code-review document**
A local report reads as a continuous engineering document. The outcome leads,
followed by failed expectations and inspectable outputs; recorded performance follows
scenario evidence. No remote fonts, assets, scripts, or services are required.

## Colors

Status is expressed with words as well as color. Quiet surfaces distinguish JSON
from explanatory text; thin rules separate observations without nested panels.

## Typography

Native typography keeps the report self-contained and quick to read. Monospace is
reserved for code, artifact identities, and JSON; metrics use tabular numerals.

## Layout

The report is centered within a maximum measure of 1120px. Two evidence columns
collapse into one below 640px; output wraps within its container. Failed scenarios
precede passing ones. Body copy keeps a readable measure near 72 characters.

## Elevation & Depth

Flat paper, thin rules, and quiet code backgrounds. No shadows are implemented.

## Shapes

JSON blocks have gently curved corners. Document sections remain unboxed.

## Components

Native details/summary controls reveal final output and full recorded checks.
Links and disclosures have visible keyboard focus. Hover states underline links or
color disclosures. Reduced-motion preference disables the brief disclosure reveal.

## Do's and Don'ts

- Do lead with actionable failures and show expected/observed evidence.
- Do preserve readable labels when metrics are unavailable or outcomes uncertain.
- Don't render agent strings as markup or load remote report resources.
- Don't use a report's passing state to claim overall model quality.
