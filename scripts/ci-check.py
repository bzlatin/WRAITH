#!/usr/bin/env python3
"""Run one CI operation, write its exit to GITHUB_OUTPUT, and propagate it."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def check(binary, config, samples, mode, name=None, baseline=None, candidate=None,
          policy=None, report=None):
    command = [str(binary), "--config", str(config)]
    if mode == "run":
        if not name:
            raise ValueError("run mode requires --save")
        command += ["run", "--samples", str(samples), "--save", name]
    else:
        if not baseline or not candidate:
            raise ValueError("compare mode requires --baseline and --candidate")
        command += ["compare", str(baseline), str(candidate)]
        if policy:
            command += ["--policy", str(policy)]
    if report:
        command += ["--output", "json"]
    if report:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("w") as destination:
            result = subprocess.run(command, stdout=destination)
    else:
        result = subprocess.run(command)
    code = result.returncode if result.returncode >= 0 else 128 - result.returncode
    if path := os.environ.get("GITHUB_OUTPUT"):
        with open(path, "a") as destination:
            destination.write(f"exit-code={code}\n")
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--config", default="wraith.yaml")
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--mode", choices=["run", "compare"], required=True)
    parser.add_argument("--save")
    parser.add_argument("--baseline")
    parser.add_argument("--candidate")
    parser.add_argument("--policy")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        sys.exit(check(args.binary, args.config, args.samples, args.mode, args.save,
                       args.baseline, args.candidate, args.policy, args.report))
    except (ValueError, OSError) as error:
        parser.exit(2, f"CI execution failed: {error}\n")
