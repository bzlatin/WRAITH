#!/usr/bin/env python3
"""Package a native Wraith binary; no third-party Python dependencies."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def package(binary, target, output, require_license=False, expected_version=None):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", target):
        raise ValueError("target must be a Rust target triple without path separators")
    binary = Path(binary).resolve()
    result = subprocess.run([str(binary), "--version"], check=True, capture_output=True, text=True)
    match = re.fullmatch(r"wraith (\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?)\s*", result.stdout)
    if not match:
        raise ValueError("binary did not return an expected Wraith version")
    version = match[1]
    if expected_version is not None and version != expected_version:
        raise ValueError(f"tag version {expected_version!r} does not match binary version {version!r}")
    license_path = ROOT / "LICENSE"
    if require_license and (not license_path.is_file() or not license_path.read_text().strip()):
        raise ValueError("Publication requires a nonempty LICENSE file chosen by the project owner")
    prefix = f"wraith-{version}-{target}"
    executable = "wraith.exe" if "windows" in target else "wraith"
    files = {executable: binary.read_bytes(), "README.md": (ROOT / "README.md").read_bytes(),
             "PROTOCOL.md": (ROOT / "docs/protocol.md").read_bytes(),
             "RELEASE.json": (json.dumps({"version": version, "target": target,
                                          "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
                                         indent=2) + "\n").encode()}
    # Ship the onboarding kit and detailed guides alongside the binary.
    for directory in ["adapters", "docs"]:
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in (".py", ".mjs", ".mts", ".md"):
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files["install.py"] = (ROOT / "scripts/install.py").read_bytes()
    if license_path.is_file():
        files["LICENSE"] = license_path.read_bytes()
    else:
        files["LICENSE-NOTICE.txt"] = b"No distribution license has been selected. This private build grants no license.\n"
    for name in ["NOTICE", "THIRD_PARTY_LICENSES.txt"]:
        path = ROOT / name
        if path.is_file():
            files[name] = path.read_bytes()
        elif require_license:
            raise ValueError(f"Publication requires {name}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (prefix + (".zip" if "windows" in target else ".tar.gz"))
    if "windows" in target:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as container:
            for name, contents in sorted(files.items()):
                entry = zipfile.ZipInfo(f"{prefix}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
                entry.external_attr = (0o755 if name == executable else 0o644) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                container.writestr(entry, contents)
    else:
        # Stable member metadata and gzip header, so identical inputs package identically.
        import gzip
        with archive.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as container:
                    for name, contents in sorted(files.items()):
                        entry = tarfile.TarInfo(f"{prefix}/{name}")
                        entry.size = len(contents)
                        entry.mode = 0o755 if name == executable else 0o644
                        container.addfile(entry, io.BytesIO(contents))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + ".sha256").write_text(f"{digest}  {archive.name}\n")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", default=ROOT / "release", type=Path)
    parser.add_argument("--require-license", action="store_true")
    parser.add_argument("--expected-version")
    args = parser.parse_args()
    try:
        print(package(args.binary, args.target, args.output, args.require_license, args.expected_version))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Release packaging failed: {error}\n")
