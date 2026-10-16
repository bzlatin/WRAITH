# Code-context preview: readiness and decision

October 16, 2026. The owner authorized preparing a self-service GitHub preview and
tracking it as a Codex goal after the [automatic-delivery study](code-context-followup.md).
This is a packaging, documentation and first-use task. It does not reopen model
budgets, authorize outreach/publication or establish that the product is profitable.

Later authorization covers a source branch/PR and a bounded actual Codex test.
That test stopped before coding on account/model compatibility; see the
[current assessment](code-context-codex-assessment.md). The original packaging
results below remain unchanged. No outreach or new binary/npm release is authorized.

## Goal and scope

Make the local tool easy to try, describe its actual job and collect useful
voluntary feedback. Keep code-context setup separate from the Rust CLI. A website,
accounts, billing, remote indexing and another retrieval feature queue are outside
this preview. The owner can decide whether to publish the reviewed work afterward.

| Readiness check | Acceptance |
| --- | --- |
| Source installation | One npm command builds locked dependencies and installs a standalone payload; no project scripts, shell profiles or agent settings are changed |
| Managed files | Check hashes; refuse existing destinations, symlink redirection and corrupt packages |
| Removal | Verify ownership/content first; preserve user modifications, extra files, repositories, caches and agent settings |
| Demo | Create a fresh TypeScript Git repository, retrieve policy/caller/tests, pass three ordinary application tests; no provider calls |
| Codex setup | Generate fixed-root configuration; actual Codex parses it, starts MCP and discovers all three tools without a model turn |
| Documentation | Explain the job, install, expected output, limits, privacy, evidence, troubleshooting and uninstall |
| Feedback | Public issue forms for setup problems and voluntary real-task/return-use feedback; no automatic collection |

The wrapper pins the Node executable used for installation. Moving that Node
installation requires reinstalling. The source installer and generated payload
retain Apache-2.0 and bundled dependency notices. No new distribution license or
package release was selected.

Verified locally on macOS arm64 with Node.js 22.19.0 and Python 3.13.0:

- The documented one-command source installation completed in an ignored prefix.
- All 15 prototype/preview tests, 10 study-boundary tests and 84 repository script
  tests passed. Tests include the standalone demo, MCP calls and uninstall, plus
  conflict, corruption, traversal and preservation controls.
- Codex CLI 0.143.0 parsed the installed preview's configuration, started the
  server and discovered all three tools. No model turn was started.
- The prepared demo passed its three application tests and returned the policy,
  subscription rule, API caller and test file.
- README local links and GitHub issue-form YAML validated. The frozen retrieval
  source hashes still match the completed follow-up experiment.

Sandbox DNS initially blocked npm downloads; a separately recorded authorized
network run completed the source installer. That environment failure is not a
successful installation observation. Linux/Windows and GitHub CI execution remain
unverified here. The Rust engine was not changed or retested for this preview.

## What the evidence says

The local tool works, and a bounded three-task study observed fewer model requests
with automatic initial context. Its median-cost threshold was not met. The public
README includes both facts and links to the full results. This preview adds no
new model observations, customer outcomes or claims about future savings.

Prepared demo results measure setup/navigation mechanics. Codex's MCP catalog
check proves connection mechanics, not whether an agent will choose the tools or
whether people will keep using them. It is important to distinguish the preview's
optional MCP integration from the study's automatically supplied initial context.

Current independent trial observations: **zero**. No independent repeat use, paid
commitment or profitability has been established. GitHub stars, downloads and
successful automated tests cannot substitute for these observations.

## Bounded next decision

After a separately authorized public preview, invite voluntary self-service use.
No invitation has been sent and no recurring automation is configured by this task.
Begin a two-week observation window with the first independent trial, rather than
running a timer while the preview is unavailable. Record all known setup attempts,
including blocked installations and people who do not return.

Use the recommendation's small internal checkpoints: ten independent developers
successfully try it, five choose it again for a different task on another day, and
two teams make a concrete paid commitment before starting hosted-service work.
These are investment rules, not statistically representative market estimates.
Separate people who tried only the demo from those who used their own codebase.
Exclude owner/Codex-operated fixtures, prompted repeat trials and known historical
tasks from independent return use. Non-response remains unknown, not a successful
trial or a confirmed rejection.

Ask what task they had, their usual alternative, what context helped or was missing,
what friction it added, and why they returned or stopped. Asking what someone
*might* pay is exploratory feedback; it is not a purchase or contract. Keep private
customer details and any local analysis in ignored `.wraith/`.

At the end of the window, make a written continue/stop decision using the actual
denominators and examples. If repeat use is absent, shelve this positioning.
If the observation window has too little participation, mark demand unknown and
pause further engineering; do not start another automated benchmark to fill the gap.

Codex can prepare updates, investigate submitted reproductions and summarize
feedback when authorized. It cannot supply independent users or manufacture paid
demand. A completed preview-readiness goal is not a completed business-validation goal.

## Distribution status

This task prepares source files, a locally built payload and GitHub issue forms.
They are not published merely because they exist in the checkout. The installer
works from the source tree; there is no public code-context release or npm package.
The existing v0.5.0 Rust release is unchanged. Public publishing or messages to
other people require the owner's request.

Ordinary use: [README](../experiments/code-context/README.md) and
[setup guide](../experiments/code-context/GUIDE.md). Previous experiments, their
frozen sources, complete/incomplete evidence and unused request capacity stay fixed.

The subsequently approved [repaired-client study](code-context-codex-study.md)
confirmed subscription access but stopped on its first native timeout. It does
not establish a development-benefit comparison or independent adoption.
