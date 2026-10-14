# smolagents local fix study

Nine fixed Wraith contracts exercise the real upstream `ToolCallingAgent` with a
scripted offline model. Three isolated patches and a combined patch address final
answer validation, callable diagnostics, and stream closing.

[Run the automated study and review its limits](../../docs/maintained-agent.md).
Source and selected existing tests are pinned in [source.json](source.json).
No provider calls, production performance estimates, or maintainer adoption claims.

The patches derive from Hugging Face's Apache-2.0 smolagents source at revision
`96f33faaf028479119ec8d34507b47694cf14e34`. They are local proposed modifications,
not upstream releases. See [the upstream license](UPSTREAM_LICENSE.txt).
Other files in this directory are Wraith evaluation tooling under the repository's
Apache-2.0 license. Evaluation results belong to the source build, not v0.5.0.
