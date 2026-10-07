import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "target/debug" / ("wraith.exe" if os.name == "nt" else "wraith")


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


packager = load("packager", "package-release.py")
ci = load("ci", "ci-check.py")
lookup = load("lookup", "find-baseline.py")
demo = load("demo", "demo.py")


class Packaging(unittest.TestCase):
    def test_archive_checksums_metadata_and_reproducible_packaging(self):
        for target in ["aarch64-apple-darwin", "x86_64-pc-windows-msvc"]:
            with tempfile.TemporaryDirectory() as directory:
                archive = packager.package(BINARY, target, directory)
                original = archive.read_bytes()
                digest = hashlib.sha256(original).hexdigest()
                self.assertEqual(archive.with_name(archive.name + ".sha256").read_text(), f"{digest}  {archive.name}\n")
                prefix = archive.name.removesuffix(".zip").removesuffix(".tar.gz")
                if "windows" in target:
                    with zipfile.ZipFile(archive) as container:
                        metadata = json.loads(container.read(prefix + "/RELEASE.json"))
                        binary = container.read(prefix + "/wraith.exe")
                        self.assertIn(b"Apache License", container.read(prefix + "/LICENSE"))
                        self.assertIn(b"third-party", container.read(prefix + "/THIRD_PARTY_LICENSES.txt"))
                else:
                    with tarfile.open(archive) as container:
                        metadata = json.load(container.extractfile(prefix + "/RELEASE.json"))
                        binary = container.extractfile(prefix + "/wraith").read()
                        self.assertIn(b"Apache License", container.extractfile(prefix + "/LICENSE").read())
                        self.assertIn(b"third-party", container.extractfile(prefix + "/THIRD_PARTY_LICENSES.txt").read())
                        self.assertEqual(container.getmember(prefix + "/wraith").mode, 0o755)
                self.assertEqual(metadata["target"], target)
                self.assertEqual(metadata["binarySha256"], hashlib.sha256(binary).hexdigest())
                packager.package(BINARY, target, directory)
                self.assertEqual(archive.read_bytes(), original)

    def test_license_version_and_path_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                packager.package(BINARY, "../../escape", directory)
            with self.assertRaises(ValueError):
                packager.package(BINARY, "native", directory, expected_version="9.9.9")
            # Simulate the unlicensed project irrespective of later licensing choices.
            with patch.object(packager, "ROOT", Path(directory)):
                with self.assertRaisesRegex(ValueError, "LICENSE"):
                    packager.package(BINARY, "native", directory, require_license=True)


class CiContract(unittest.TestCase):
    def test_demo_command_preserves_paths_with_spaces_quotes_and_backslashes(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            script = directory / "agent with space's.py"
            script.write_text("import sys,json\nr=json.load(sys.stdin)\nprint(json.dumps({'protocolVersion':1,'scenarioId':r['scenarioId'],'output':sys.argv[1]}))\n")
            marker = r"C:\Users\example\quoted path"
            contents = 'version: 1\nagent:\n  command: "placeholder"\ntests:\n- id: quoting\n  input: hi\n'
            config = directory / "wraith.yaml"
            config.write_text(demo.config_with_command(contents, [sys.executable, str(script), marker]))
            result = subprocess.run([str(BINARY), "--config", str(config), "run", "--output", "json"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["scenarios"][0]["run"]["response"]["output"], marker)

    def test_exit_propagation_report_and_output_file(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            config = directory / "wraith.yaml"
            python = "python" if os.name == "nt" else "python3"
            config.write_text(f"version: 1\nagent: {{command: '{python} agent.py'}}\ntests:\n- id: hi\n  input: hi\n  expect: {{output_contains: [good]}}\n")
            agent = directory / "agent.py"
            agent.write_text("import sys,json\nr=json.load(sys.stdin)\nprint(json.dumps({'protocolVersion':1,'scenarioId':r['scenarioId'],'output':'good'}))\n")
            output = directory / "outputs"
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}):
                self.assertEqual(ci.check(BINARY, config, 2, "run", "baseline"), 0)
                agent.write_text(agent.read_text().replace("'good'", "'bad'"))
                self.assertEqual(ci.check(BINARY, config, 2, "run", "candidate"), 1)
                report = directory / "reports/comparison.json"
                self.assertEqual(ci.check(BINARY, config, 2, "compare", baseline="baseline", candidate="candidate", policy=config, report=report), 1)
                self.assertFalse(json.loads(report.read_text())["passed"])
                self.assertEqual(ci.check(BINARY, config, 2, "compare", baseline="missing", candidate="candidate"), 2)
            self.assertEqual(output.read_text().splitlines(), ["exit-code=0", "exit-code=1", "exit-code=1", "exit-code=2"])

    def test_exact_successful_push_baseline_selection(self):
        valid = {"head_sha":"a" * 40, "head_branch":"main", "event":"push", "conclusion":"success", "id":7}
        invalid = [dict(valid, head_sha="b" * 40), dict(valid, event="pull_request"),
                   dict(valid, conclusion="failure"), dict(valid, head_branch="feature")]
        self.assertIsNone(lookup.select_run(invalid, "a" * 40, "main"))
        self.assertEqual(lookup.select_run(invalid + [valid], "a" * 40, "main")["id"], 7)


if __name__ == "__main__":
    unittest.main()
