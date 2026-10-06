#!/usr/bin/env python3
"""Verify checksum, unpack, and run the native release's init/run/compare loop."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import zipfile
import argparse


def smoke(archive):
    archive = Path(archive).resolve()
    expected = archive.with_name(archive.name + ".sha256").read_text().split()[0]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise ValueError("Archive checksum mismatch")
    with tempfile.TemporaryDirectory(prefix="wraith-package-") as directory:
        directory = Path(directory)
        # Only consume our own freshly built archive, with a single package prefix.
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as container:
                container.extractall(directory)
        else:
            with tarfile.open(archive) as container:
                container.extractall(directory, filter="data")
        package, = directory.iterdir()
        for name in ["LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.txt"]:
            if not (package / name).read_text(encoding="utf-8").strip():
                raise ValueError(f"Missing license material: {name}")
        metadata = json.loads((package / "RELEASE.json").read_text())
        binary = package / ("wraith.exe" if "windows" in metadata["target"] else "wraith")
        if hashlib.sha256(binary.read_bytes()).hexdigest() != metadata["binarySha256"]:
            raise ValueError("Binary checksum mismatch")
        work = directory / "workspace"
        work.mkdir()
        for args in [["--version"], ["init"], ["run", "--save", "baseline"],
                     ["run", "--save", "candidate"], ["compare", "baseline", "candidate"]]:
            subprocess.run([str(binary), *args], cwd=work, check=True)
        print(f"Native package verified: {metadata['target']} {metadata['version']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    smoke(parser.parse_args().archive)
