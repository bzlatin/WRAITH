# Install Wraith

The v0.5 onboarding implementation is currently local and unpublished. The release
workflow builds archives for macOS Apple Silicon/Intel, Linux x86_64 GNU, and Windows
x86_64 MSVC. Publishing those assets is a separate owner-controlled step.

## From the current checkout

Requires Rust 1.87+:

```sh
cargo install --path crates/wraith-cli --locked
wraith --version
```

Or use `cargo build --release --locked` and the executable in `target/release`.
Python integrations need Python 3.10+; TypeScript integrations need Node 22.18+.
The Wraith executable has no Python/Node dependency; only adapters need their runtime.

## From a published native release

Download the native archive and matching `.sha256` file from GitHub Releases. The
installer detects your platform, checks archive and binary SHA-256, and atomically
installs the executable. It changes no shell profiles and requires no Rust.

After v0.5.0 is published, the one-command install from a checkout is:

```sh
python3 scripts/install.py --version 0.5.0
```

The same `install.py` is attached to the release and included in its archives. For a
locally built archive, or an authenticated download from a private repository:

```sh
python3 scripts/install.py --version 0.5.0 \
  --archive release/wraith-0.5.0-aarch64-apple-darwin.tar.gz \
  --checksum release/wraith-0.5.0-aarch64-apple-darwin.tar.gz.sha256 \
  --directory /desired/bin
```

The default destination is `~/.local/bin`; add it to PATH if needed. Windows users
can use the same installer with Python, or extract `wraith.exe` from the native ZIP
and put it in a directory on PATH. Checksums detect corrupted downloads; release
signing is not implemented. Unsupported platforms need a source build.
