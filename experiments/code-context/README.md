# Wraith Context — local preview

**Give your coding agent relevant code and tests from the checkout you're changing.**

Wraith Context searches TypeScript and JavaScript source and returns snippets with
file/line citations and source hashes. Use it to locate a policy, its callers and
candidate tests before editing. It works with local Git checkouts and worktrees.

No account, GPU, embedding service or model key is needed by the tool. This is a
separate Node.js preview; the released Wraith v0.5 Rust binary does not include it.

## Install and try

Requirements: **Node.js 22.12+, npm and Git**. From a source checkout of this repo:

```sh
npm --prefix experiments/code-context run preview:install
wraith-context demo --directory ./context-demo
```

The first command installs locked build dependencies with lifecycle scripts
disabled, builds the preview and installs its standalone files. It uses your
network for npm installation. Ordinary queries and the demo run locally.
No code-context npm package or GitHub release has been published.

The installer prints the command path. If `wraith-context` is not on PATH, use
that full path. The default is `~/.local/bin/wraith-context` on macOS/Linux;
Windows uses a `bin` directory under `%LOCALAPPDATA%\WraithContext`. Shell profiles
and agent settings are left for you to configure. [Custom locations and uninstall](GUIDE.md#install-and-uninstall).

The demo creates a new Git repository, runs its three application tests and saves
`.wraith/context.json`. It finds the access rule, subscription policy, API caller
and tests. Existing directories are refused. This is a prepared demonstration.

## Connect Codex

```sh
wraith-context codex-config --root /absolute/path/to/your/checkout
```

Copy the printed table into your local Codex `config.toml`, then restart Codex.
Start with this explicit request:

> Use Wraith's code_context tool to find the implementation and tests for
> [my task]. Explain the relevant code with citations before editing.

The server is fixed to the selected checkout. Use a separate configuration for
each worktree. Optional tools are not guaranteed to be called automatically.
[Five-minute Codex guide](GUIDE.md#connect-codex) · [Try a CLI query](GUIDE.md#commands).

## What to expect

- Finds syntax definitions, ranked source/test snippets and lexical occurrences.
- Refreshes on edits and branch changes; hash-checks returned citations.
- Reuses parsed content across worktrees while keeping dirty checkouts separate.
- Keeps bounded output and reports omitted or truncated results.

Retrieval can miss important code or return irrelevant snippets. References are
lexical candidates, including shadowed names; there is no complete call graph,
type checking or guaranteed test coverage. Source text remains untrusted data.

The tool sends no telemetry or uploads. Your agent may send retrieved snippets to
its model provider. Ignore rules and common private filenames are filtered, but
this is not a secret detector. [Privacy and limits](GUIDE.md#privacy-and-limits).

## Does it help?

In three historical code-change tasks, automatic initial context used **19 model
requests versus 28** with ordinary search; both passed all selected tests. Total
estimated provider cost was 14.7% lower, but median cost barely changed and two
tasks took longer. These observations do not establish reliable savings or demand.
[Results and methodology](../../docs/code-context-followup.md).

The actual Codex integration now returns model-directed MCP context. Its one
completed Hono pair passed the same 56 tests, but Wraith took 44.12 seconds versus
28.25 for native search. The next Wraith session passed 162 Zod tests but timed out
before a final response; the comparison stopped. A workflow advantage is still
unproven. [Latest results and decision](../../docs/code-context-integrated-study.md).

Try it on your own task and tell us what helped, what was missing and whether you
chose to use it again. [Trial feedback](https://github.com/bzlatin/WRAITH/issues/new?template=context-feedback.yml)
· [Setup problem](https://github.com/bzlatin/WRAITH/issues/new?template=context-install.yml).
Feedback is voluntary; no repository upload is needed.

Apache-2.0 for original code. Bundled dependencies retain their
[third-party licenses](THIRD_PARTY_NOTICES.txt). [Build and contributor notes](GUIDE.md#development).
