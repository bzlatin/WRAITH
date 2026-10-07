# Install Wraith

## Native binary (recommended)

Download [install.py](https://github.com/bzlatin/WRAITH/releases/download/v0.5.0/install.py)
from the [v0.5.0 release](https://github.com/bzlatin/WRAITH/releases/tag/v0.5.0), then run:

```sh
python3 install.py --version 0.5.0
```

On Windows, use `python` instead of `python3`. The installer detects your platform,
verifies the archive and binary SHA-256 checksums, and installs to `~/.local/bin`.
Add the printed directory to PATH, open a new terminal if needed, and verify:

```sh
wraith --version
```

To choose another location, add `--directory /path/to/bin`. The installer replaces
the binary atomically and does not edit shell profiles. No Rust installation is needed.

| Platform | Package |
| --- | --- |
| macOS Apple Silicon | `aarch64-apple-darwin.tar.gz` |
| macOS Intel | `x86_64-apple-darwin.tar.gz` |
| Linux x86_64, GNU | `x86_64-unknown-linux-gnu.tar.gz` |
| Windows x86_64, MSVC | `x86_64-pc-windows-msvc.zip` |

Linux binaries are built on Ubuntu 24.04 with glibc; older systems may need a source
build. Other architectures also require source builds. Checksums detect corruption;
release signing is not implemented.

For manual installation, download the archive and matching `.sha256` file, verify
its SHA-256, extract it, and put `wraith` or `wraith.exe` on PATH. To install an
already-downloaded archive with the installer:

```sh
python3 install.py --version 0.5.0 \
  --archive wraith-0.5.0-aarch64-apple-darwin.tar.gz \
  --checksum wraith-0.5.0-aarch64-apple-darwin.tar.gz.sha256
```

Use filenames for your platform. The same installer is also in `scripts/install.py`
in a source checkout.

## Build from source

From the repository root, with Rust 1.87+:

```sh
cargo install --path crates/wraith-cli --locked
wraith --version
```

Alternatively, run `cargo build --release --locked` and use `target/release/wraith`
(`wraith.exe` on Windows).

## Agent runtimes

Wraith itself has no Python or Node dependency. Its Python function adapter needs
Python 3.10+; the demo needs Python too. Direct TypeScript execution needs Node
22.18+. Existing JavaScript applications can use a compatible Node runtime.
Your application supplies its own dependencies and provider SDKs.

Next: [try the offline demo](dogfooding.md) or [connect an agent](getting-started.md).
