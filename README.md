# Wraith

**Local code context for coding agents.** Experimental source preview.

Give your agent relevant TypeScript and JavaScript code from the checkout you're
changing. Wraith Context returns definitions, source snippets and candidate tests
with file/line citations and source hashes. Use it to locate an access rule, API
handler or existing test before asking an agent to make a change.

Runs locally with no account, GPU, embedding service or model key. Connect it to
Codex through MCP or query it from your terminal. The tool sends no telemetry;
your coding agent may send retrieved snippets to its model provider.

## Try the preview

With **Node.js 22.12+, npm and Git**, from this source checkout:

```sh
npm --prefix experiments/code-context run preview:install
wraith-context demo --directory ./context-demo
```

Use the full command path printed by the installer if it is not on PATH. The demo
creates a new TypeScript repository with an access policy, API caller and tests.
It makes no model calls. No code-context release or npm package is published yet.

Connect your checkout to Codex:

```sh
wraith-context codex-config --root /absolute/path/to/your/checkout
```

Copy the printed table into your local Codex configuration and restart Codex.
Ask it to use `code_context` for your task. Optional tools are not automatically
called, and retrieval can miss important code. References are lexical candidates;
this is not a complete call graph or a test-coverage guarantee.

[Five-minute guide](experiments/code-context/GUIDE.md#connect-codex) ·
[Commands, privacy and uninstall](experiments/code-context/GUIDE.md) ·
[Preview details](experiments/code-context/README.md) ·
[How it works and evidence](docs/code-context-how-it-works.md).

## What we have measured

On three historical fixes in Hono, Zod and tRPC, automatic initial context used
**19 model requests versus 28** with ordinary search. Both approaches passed all
selected tests. Total estimated model cost was 14.7% lower, but median cost barely
changed and two tasks took longer. These observations do not establish reliable
savings, independent adoption or paid demand.
[Full results and limits](docs/code-context-followup.md).

A later installed-Codex comparison stopped on account/model compatibility errors
before any coding runs. It adds no evidence of agent improvement.
[Current assessment](docs/code-context-codex-assessment.md).

Trying it on your own work? Share what helped, what was missing and whether you
chose to use it again. [Trial feedback](https://github.com/bzlatin/WRAITH/issues/new?template=context-feedback.yml)
· [Setup problem](https://github.com/bzlatin/WRAITH/issues/new?template=context-install.yml).
Feedback is voluntary. Keep private code and credentials out of public issues.

## Existing Wraith tools

The code-context preview is a separate Node.js tool under `experiments/code-context/`.
It does not change the Rust CLI or its release contracts.

| Tool | Availability | Guide |
| --- | --- | --- |
| Run fixed agent scenarios and compare changes | Released Rust CLI v0.5.0 | [Install](docs/install.md) · [Get started](docs/getting-started.md) |

The published v0.5.0 binary does not include code context.
Existing workflows remain supported. [All documentation](docs/README.md) ·
[Contributing](CONTRIBUTING.md).

Apache-2.0. [License](LICENSE) · [Rust notices](THIRD_PARTY_LICENSES.txt) ·
[Code-context notices](experiments/code-context/THIRD_PARTY_NOTICES.txt).
