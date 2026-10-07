# Contributing

Report bugs or suggest improvements in [GitHub issues](https://github.com/bzlatin/WRAITH/issues).
Include the Wraith version, platform, expected behavior, and a minimal reproducible
case. Review logs and artifacts for private data before sharing them.

## Development

Use Rust 1.87+ and Python 3. Read [architecture](docs/architecture.md) and the relevant
module before changing contracts. The core owns execution and evaluation; the CLI
owns setup, history, reports, and exit codes. Provider logic belongs in adapters.

From the repository root:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --workspace --locked
python3 -m unittest discover -s scripts/tests
```

For adapter changes, run `python3 scripts/demo.py`. TypeScript examples require
Node 22.18+, `npm ci`, and `npm run build` in `examples/typescript-agent`. For RAG
changes, run `python3 scripts/pilot.py`. Dependency changes require refreshing
`THIRD_PARTY_LICENSES.txt` with `scripts/license-notices.py`.

## Documentation

Lead with the task and its result. Use short sentences, concrete examples, and
commands readers can run without a contributor's local setup. Explain limitations
where they affect a decision. Keep the README focused on value and first use; put
technical detail in linked guides. Avoid unsupported quality claims and private
project references.

Pull requests should explain the resulting behavior and relevant validation.
Use offline deterministic fixtures for tests; do not require provider credentials.
