"""Pinned public fixture downloads must preserve integrity and local boundaries."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ingestion_fixtures", ROOT / "examples/verified-ingestion/fetch_fixtures.py"
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def archive(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name, data in files:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    return output.getvalue()


class FixtureTests(unittest.TestCase):
    def test_download_rejects_checksum_mismatch(self):
        with patch.object(
            fixtures.urllib.request, "urlopen", return_value=io.BytesIO(b"wrong")
        ):
            with self.assertRaisesRegex(ValueError, "checksum"):
                fixtures.download(
                    "https://example.test/fixture",
                    hashlib.sha256(b"expected").hexdigest(),
                )

    def test_corpus_selection_license_and_no_overwrite(self):
        data = archive(
            [(f"source/Doc/library/{i:03}.rst", str(i).encode()) for i in range(201)]
            + [
                ("source/LICENSE", b"license"),
                ("source/Doc/tutorial/skip.rst", b"skip"),
            ]
        )
        with tempfile.TemporaryDirectory() as work:
            destination = Path(work) / "fixture"
            with patch.object(fixtures, "download", return_value=data):
                fixtures.fetch(destination, corpus=True)
                with self.assertRaises(FileExistsError):
                    fixtures.fetch(destination, corpus=True)
            files = sorted((destination / "documents").glob("*.txt"))
            self.assertEqual(len(files), 200)
            self.assertEqual(files[0].read_text(), "0")
            self.assertEqual(files[-1].name, "199.txt")
            self.assertEqual(
                (destination / "CPYTHON-LICENSE.txt").read_text(), "license"
            )
            self.assertEqual(
                json.loads((destination / "provenance.json").read_text())["commit"],
                fixtures.CPYTHON_COMMIT,
            )

    def test_corpus_path_cannot_escape_destination(self):
        data = archive(
            [
                ("source/Doc/library/../../../escape.rst", b"escape"),
                ("source/LICENSE", b"license"),
            ]
        )
        with tempfile.TemporaryDirectory() as work:
            with patch.object(fixtures, "download", return_value=data):
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    fixtures.fetch(Path(work) / "fixture", corpus=True)
            self.assertFalse((Path(work) / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()
