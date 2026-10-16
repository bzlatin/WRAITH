# Prepared-test study: MCP approval failure

October 16, 2026. The owner approved a fresh eight-session comparison after the
[earlier timeout](code-context-codex-study.md). The
[protocol](../experiments/code-context/study/ready-tests-protocol.json),
[controller](../experiments/code-context/study/ready_tests_codex.py) and
[results](../experiments/code-context/study/ready-tests-results.json) are preserved.
Each session had 180 seconds and the same sandbox-qualified selected-test command.

**The test-environment correction worked. The Wraith treatment did not execute:
Codex denied both MCP calls. This is not a valid Wraith performance comparison.**

| Session | Outcome |
| --- | --- |
| Hono native, repetition 1 | Completed in 38.66 seconds; prepared command ran and all 56 tests passed |
| Hono instructed MCP, repetition 1 | Completed in 56.68 seconds using native fallback; Wraith call denied; all 56 tests passed |
| Zod instructed MCP, repetition 1 | Completed in 21.48 seconds using native fallback; Wraith call denied; all 162 tests passed |
| Zod native, repetition 1 | Interrupted by the operator after the MCP setup failure was identified |
| Remaining four sessions | Not run after stop |

Four slots were reserved; the other four are closed. The operator stopped the
controller to avoid spending further sessions on a known nonfunctional treatment.
The interrupted native session is not an accepted task. Successful fallback patches
do not count as successful Wraith use. Do not pool these timings or token counts
as evidence of retrieval benefit. There were **zero successful Wraith calls**.

## Cause and bounded correction

Both calls returned `MCP tool call requires approval, but approval policy is never`.
The unattended runner prohibited prompts without explicitly permitting Wraith's
read tools. The earlier checks established startup, discovery and a model response
separately; they did not establish model-mediated tool execution under that policy.
This was an integration/evaluation omission.

The source-preview helper now has an explicit `--allow-read-tools` option. It
prints `approval_mode = "auto"` for `code_context`, `code_symbols` and
`code_references` individually. It changes no global approval policy, grants no
new tools automatically, and writes no Codex settings. Ordinary generated
configuration retains the client's normal approval behavior. The tools inspect
the fixed checkout and write local syntax caches; they do not edit application
source or call a model.

Codex 0.163.0 resolved all three settings. A host-dispatched
`mcpServer/tool/call` returned real context without a model turn. A default-config
control also succeeded through that host API, so it **does not validate the
model-mediated approval path**. A real model-directed tool-call preflight is still
required before another development comparison. The added preview tests verify
the opt-in scope and default behavior; they do not supply product-value evidence.

Read the [Codex configuration documentation](https://learn.chatgpt.com/docs/extend/mcp)
for server/per-tool approval controls. A future study must first verify the exact
tool/configuration/model path it will measure, then freeze it before development
runs. All previous failed attempts, budgets and source hashes remain intact.

## Current decision

The CLI can run the model and the selected tests work in its sandbox. The
unattended MCP workflow still needs the integrated preflight above. The product
benefit requirement remains incomplete. Keep the source utility available with
these limits, and keep hosted work, scaling claims and monetization promises
paused. No independent repeat use or paid commitment has been observed.
