#!/usr/bin/env python3
"""Collect verbatim dependency license/notice files from locked Cargo metadata.

Includes build, development, and all-platform dependencies (a deliberate superset
of any one native binary). Run after cargo fetch; review after dependency changes.
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def collect(metadata):
    output = ["Wraith third-party license notices\n",
              "Generated from Cargo.lock, including all platforms and build/test dependencies.\n"
              "Each dependency retains its own license; Wraith's Apache-2.0 license does not replace it.\n"]
    for package in sorted(metadata["packages"], key=lambda p: (p["name"], p["version"])):
        if package["id"] in metadata["workspace_members"]:
            continue
        directory = Path(package["manifest_path"]).parent
        files = {p for p in directory.iterdir() if p.is_file() and
                 p.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT"))}
        if package.get("license_file"):
            files.add(directory / package["license_file"])
        # r-efi 6.0.0 declares this choice in README/Cargo metadata, but ships
        # AUTHORS instead of license texts. Select its Apache-2.0 option explicitly.
        if not files and (package["name"], package["version"]) == ("r-efi", "6.0.0"):
            files = {directory / "AUTHORS", ROOT / "LICENSE"}
            output.append("\nr-efi 6.0.0: using its declared Apache-2.0 option.\n")
        if not files:
            raise ValueError(f"No license text found for {package['name']} {package['version']}; review manually")
        output.append(f"\n{'=' * 72}\n{package['name']} {package['version']}\n"
                      f"SPDX: {package.get('license') or 'see license text'}\n"
                      f"Source: {package.get('repository') or package['source']}\n")
        for path in sorted(files, key=lambda p: p.name):
            output.append(f"\n--- {path.name} ---\n{path.read_text(encoding='utf-8')}\n")
    return "".join(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text()) if args.metadata else json.loads(subprocess.check_output(
        ["cargo", "metadata", "--locked", "--format-version", "1"], cwd=ROOT, text=True))
    text = collect(metadata)
    destination = ROOT / "THIRD_PARTY_LICENSES.txt"
    if args.check:
        if destination.read_text(encoding="utf-8") != text:
            raise SystemExit("Dependency notices are stale; run python3 scripts/license-notices.py")
    else:
        destination.write_text(text, encoding="utf-8")
        print(destination)
