#!/usr/bin/env python3
"""Download pinned public fixtures. Runtime server checks themselves need no internet."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import tarfile
import urllib.request

VERSION = "1.19.0"
CPYTHON_COMMIT = "60403a5409ff2c3f3b07dd2ca91a7a3e096839c7"
CPYTHON_SHA256 = "37c8e18b35e659da6ff4db74caea50ed4170cf66c6d51f97d22e436e338d7b5b"
CPYTHON_RELEASES = {
    "3.13.0": (CPYTHON_COMMIT, CPYTHON_SHA256),
    "3.13.1": (
        "067145177975eadd61a0c907d0d177f7b6a5a3de",
        "0b6d65938149865c981de9ee61626998479b154e92895022493a04d5c0db80d7",
    ),
    "3.13.2": (
        "4f8bb3947cfbc20f970ff9d9531e1132a9e95396",
        "8bf75c04592f43fcfcf25aa8019f1d473f0d12436a603b922c4657862a72e076",
    ),
}
ASSETS = {
    ("Darwin", "arm64"): (
        "aarch64-apple-darwin",
        "4e279a80cc1ebe73e859318ff86375af54c123887dd7ae46605c0eb6cb7c44e8",
    ),
    ("Darwin", "x86_64"): (
        "x86_64-apple-darwin",
        "e7afefcc125856157b33c6184c00ddee3f1d5b112474649070592d9fdd9a3f54",
    ),
    ("Linux", "x86_64"): (
        "x86_64-unknown-linux-gnu",
        "e4405091f67d02f96fb941695ef8a6974e677632507ff7b04a3fcbb332ad9c19",
    ),
}


def download(url, digest):
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if len(data) > 100 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Fixture size/checksum mismatch")
    return data


def fetch(output, corpus=False, release="3.13.0"):
    output.mkdir(parents=True, exist_ok=False)
    if corpus:
        commit, checksum = CPYTHON_RELEASES[release]
        data = download(
            f"https://codeload.github.com/python/cpython/tar.gz/{commit}",
            checksum,
        )
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            members = sorted(
                (
                    m
                    for m in archive.getmembers()
                    if m.isfile()
                    and "/Doc/library/" in m.name
                    and m.name.endswith(".rst")
                ),
                key=lambda m: m.name,
            )[:200]
            for member in members:
                relative = Path(member.name.split("/Doc/library/", 1)[1]).with_suffix(
                    ".txt"
                )
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe corpus path")
                path = output / "documents" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.extractfile(member).read())
            license_member = next(
                m
                for m in archive.getmembers()
                if m.name.endswith("/LICENSE") and m.name.count("/") == 1
            )
            (output / "CPYTHON-LICENSE.txt").write_bytes(
                archive.extractfile(license_member).read()
            )
        provenance = {
            "kind": "public technical documentation, RST imported as plain text",
            "release": release,
            "commit": commit,
            "archive_sha256": checksum,
            "selection": "first 200 sorted regular Doc/library/**/*.rst files",
            "files": len(members),
            "bytes": sum(m.size for m in members),
        }
    else:
        target, digest = ASSETS[(platform.system(), platform.machine())]
        data = download(
            f"https://github.com/qdrant/qdrant/releases/download/v{VERSION}/qdrant-{target}.tar.gz",
            digest,
        )
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            binary = next(
                m
                for m in archive.getmembers()
                if m.isfile() and Path(m.name).name == "qdrant"
            )
            (output / "qdrant").write_bytes(archive.extractfile(binary).read())
        (output / "qdrant").chmod(0o755)
        provenance = {
            "version": VERSION,
            "target": target,
            "archive_sha256": digest,
            "source": "official qdrant/qdrant release",
        }
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(json.dumps(provenance))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory")
    parser.add_argument(
        "--corpus", action="store_true", help="Fetch CPython docs instead of Qdrant"
    )
    parser.add_argument(
        "--release",
        choices=list(CPYTHON_RELEASES),
        default="3.13.0",
        help="Pinned CPython corpus release",
    )
    args = parser.parse_args()
    fetch(args.output, args.corpus, args.release)
