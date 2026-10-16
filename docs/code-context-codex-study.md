# Repaired-client Codex study: stopped attempt

October 16, 2026. After [CLI repair](code-context-codex-assessment.md#cli-repair-after-the-stopped-study),
the owner explicitly approved one new experiment: nine ChatGPT subscription
sessions, comprising a read-only compatibility check and eight development runs.
The [protocol](../experiments/code-context/study/repaired-codex-protocol.json),
[controller](../experiments/code-context/study/repaired_codex.py) and
[sanitized results](../experiments/code-context/study/repaired-codex-results.json)
are preserved separately from every earlier experiment.

**The account/CLI compatibility check succeeded. The development comparison did
not complete. No new Wraith-versus-native performance result exists.**

## Recorded outcome

| Session | Outcome |
| --- | --- |
| Read-only `gpt-6.1-sol` response | Completed in 4.28 seconds through ChatGPT sign-in |
| First native Hono development run | Timed out at 120.01 seconds; interrupted patch passes all 56 frozen tests externally |
| Remaining seven development runs | Not run after the timeout, following the frozen stop rule |

Two of nine session slots were reserved. The other seven are closed; they are not
refunded credit or authorization to retry. No Wraith MCP development session ran.
The native patch's passing tests do not make the interrupted session an accepted
task. There is no matched pair, median-speed comparison or new context-use claim.

Codex 0.163.0 used `gpt-6.1-sol` at medium reasoning, ephemeral sessions and the
workspace sandbox. User configuration/rules were ignored, ChatGPT authentication
was forced, provider keys were excluded and the retrieval implementation stayed
frozen. Source and tests came from the same pinned Hono/Zod historical inputs.
These remain source-guided reproductions rather than prospective discoveries.

The access diagnostic reported 15,666 input tokens, 9,600 cached input tokens and
six output tokens. Cached input is part of input, not an additional total. The
interrupted development run has no completed-turn usage record. Do not treat it as
zero usage or combine the two observations into a bill estimate. No API-key runner
was used; actual ChatGPT credit consumption is not measured by these records.

Session timing includes Codex startup and any MCP startup, but excludes worktree
preparation and the controller's final test verification. It is machine time,
not measured human effort.

## Test-environment finding

The native agent located and edited the minifier, then tried normal repository
test commands. The prepared fixture lacked `pnpm` and a Vite plugin; a Vite config
loader also tried writing through the shared dependency symlink outside the
workspace sandbox. The agent attempted alternative direct checks and reached the
time limit. These are evaluation-environment limitations, not evidence that Wraith
helps or that a developer's normal checkout would behave the same way.

The external acceptance runner already used an explicit source-only Vitest config
and the native config loader. That selected-test command was not supplied to the
agent. This made the development environment less usable than the passing external
qualification implied. Preserve the attempt; do not erase it by extending its timer.

## Offline correction

The [sandbox qualification helper](../experiments/code-context/scripts/check-study-sandbox.py)
created fresh base/fixed worktrees and ran those exact unchanged tests through
`codex sandbox -P :workspace`, with an explicit config and native config loader.
No model turn was started. Hono's base fails and fixed version passes 56 tests;
Zod's base fails and fixed version passes 162 tests. Host and sandbox outcomes
agree in all four controls. Test runtime was approximately 0.6–1.2 seconds in
these sandbox invocations, excluding checkout/setup.

A future study should give both workflows the same prepared test command, state
that full upstream CI is unavailable, and use a newly frozen time limit. Its
results would describe that selected-test workflow. They would not establish
compatibility with each repository's complete development environment.

## Decision

The CLI repair works for an actual model response, and the prepared acceptance
command works in the intended sandbox. The product-benefit requirement is still
incomplete. Keep the source preview available and preserve the earlier study that
missed its cost checkpoint. No hosted service, telemetry or billing implementation
is justified by this attempt. Independent return use, enterprise scale and paid
demand remain unproven.

Any further live experiment requires a new approval and budget. The old stopped
attempts and this nine-session experiment remain closed.
