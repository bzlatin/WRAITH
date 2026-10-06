#!/usr/bin/env python3
"""Exercise passing and regressing adapters offline on any supported host."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "target/debug" / ("wraith.exe" if os.name == "nt" else "wraith")


def execute(config, args, expected, candidate=False):
    environment = dict(os.environ)
    environment.pop("WRAITH_EXAMPLE_MODE", None)
    if candidate:
        environment["WRAITH_EXAMPLE_MODE"] = "candidate"
    result = subprocess.run([str(BINARY), "--config", str(config), *args],
                            env=environment, text=True, capture_output=True)
    if result.returncode != expected:
        raise RuntimeError(f"Unexpected exit {result.returncode} for {args}:\n{result.stdout}\n{result.stderr}")
    return result


def main():
    node = os.environ.get("WRAITH_DEMO_NODE") or shutil.which("node")
    adapters = [[sys.executable, str(ROOT / "examples/python-agent/agent.py")]]
    if not node:
        raise RuntimeError("Node 22.18+ is required to verify the TypeScript adapters")
    try:
        subprocess.run([node, "--version"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("The selected Node executable cannot run; set WRAITH_DEMO_NODE to a working Node 22.18+ executable") from error
    for filename in ["agent.js", "agent.ts", "dist/agent.js"]:
        adapters.append([node, str(ROOT / "examples/typescript-agent" / filename)])
    contents = (ROOT / "wraith.yaml").read_text()
    for adapter in adapters:
        with tempfile.TemporaryDirectory(prefix="wraith-demo-") as directory:
            config = Path(directory) / "wraith.yaml"
            config.write_text(contents.replace("python3 examples/python-agent/agent.py", " ".join(shlex.quote(part) for part in adapter)))
            for samples in [1, 4]:
                execute(config, ["run", "--samples", str(samples), "--save", "baseline"], 0)
                execute(config, ["run", "--samples", str(samples), "--save", "candidate"], 1, True)
                result = execute(config, ["compare", "baseline", "candidate", "--policy", str(config), "--output", "json"], 1)
                report = json.loads(result.stdout)
                kinds = {change["classification"] for change in report["changes"]}
                assert "TOOL_SELECTION_REGRESSION" in kinds
                assert report["samplesPerScenario"] == samples
                assert report["scenarioSampling"][1]["baseline"]["passed"] == samples
                assert report["scenarioSampling"][1]["candidate"]["passed"] == 0
        print(f"Verified {adapter[-1]}: passing baseline and expected regression at 1/4 samples")
    for fixture, samples, baseline_exit, candidate_exit, expected_kinds in [
        ("trace-agent", 4, 0, 0, {"TOOL_ARGUMENTS_REGRESSION", "DOCUMENT_REGRESSION"}),
        ("sampling-agent", 4, 1, 1, {"FAILURE_RATE_REGRESSION", "OUTPUT_REGRESSION"}),
    ]:
        with tempfile.TemporaryDirectory(prefix="wraith-fixture-") as directory:
            config = Path(directory) / "wraith.yaml"
            source = ROOT / "examples" / fixture
            command = " ".join(shlex.quote(part) for part in [sys.executable, str(source / "agent.py")])
            config.write_text((source / "wraith.yaml").read_text().replace("python3 agent.py", command))
            execute(config, ["run", "--samples", str(samples), "--save", "baseline"], baseline_exit)
            execute(config, ["run", "--samples", str(samples), "--save", "candidate"], candidate_exit, True)
            report = json.loads(execute(config, ["compare", "baseline", "candidate", "--policy", str(config), "--output", "json"], 1).stdout)
            assert expected_kinds <= {change["classification"] for change in report["changes"]}
            assert report["policySource"] == "trusted_config"
        print(f"Verified {fixture}: expected comparison failures with complete independent samples")
    print("All offline adapter demos passed.")


if __name__ == "__main__":
    main()
