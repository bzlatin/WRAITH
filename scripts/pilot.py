#!/usr/bin/env python3
"""Measure Wraith against labeled benign changes and defects in the offline RAG fixture."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def pilot(binary, output, repeats=3):
    binary = Path(binary).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads((ROOT / "examples/rag-agent/pilot-cases.json").read_text())
    records = []
    with tempfile.TemporaryDirectory(prefix="wraith-rag-pilot-") as temporary:
        work = Path(temporary)
        for name in ["agent.py", "corpus.json", "wraith.yaml"]:
            shutil.copyfile(ROOT / "examples/rag-agent" / name, work / name)
        config = work / "wraith.yaml"
        # Rust's shell_words parser expects POSIX-style quoting even on Windows.
        python = shlex.quote(sys.executable.replace("\\", "/"))
        config.write_text(config.read_text().replace("python3 agent.py", python + " agent.py"))

        def execute(args, variant="baseline", expected=(0, 1)):
            environment = dict(os.environ, WRAITH_RAG_VARIANT=variant)
            result = subprocess.run([str(binary), "--config", str(config), *args, "--output", "json"],
                                    env=environment, capture_output=True, text=True, timeout=120)
            if result.returncode not in expected:
                raise RuntimeError(f"Unexpected exit {result.returncode}: {result.stderr}")
            return result.returncode, json.loads(result.stdout)

        for repeat in range(repeats):
            _, baseline = execute(["run", "--save", "baseline"], expected=(0,))
            ids = {s["scenario"]["id"] for s in baseline["scenarios"]}
            for variant, expected_ids in cases.items():
                execute(["run", "--save", "candidate"], variant)
                code, report = execute(["compare", "baseline", "candidate"])
                actual = {c["scenarioId"] for c in report["changes"] if c["severity"] == "failure"}
                expected = set(expected_ids)
                if not expected <= ids:
                    raise ValueError("Pilot labels refer to unknown scenarios")
                record = {"repeat": repeat + 1, "variant": variant, "exitCode": code,
                          "expectedRegressions": sorted(expected), "detectedRegressions": sorted(actual),
                          "falsePositives": sorted(actual - expected), "falseNegatives": sorted(expected - actual),
                          "negativeScenarios": len(ids - expected), "positiveScenarios": len(expected),
                          "comparisonPassed": report["passed"]}
                records.append(record)
                # Keep one representative complete report for each mutation.
                if repeat == 0:
                    (output / f"{variant}.json").write_text(json.dumps(report, indent=2) + "\n")
        count = Counter()
        for record in records:
            count["falsePositives"] += len(record["falsePositives"])
            count["falseNegatives"] += len(record["falseNegatives"])
            count["negativeScenarios"] += record["negativeScenarios"]
            count["positiveScenarios"] += record["positiveScenarios"]
        count["truePositives"] = count["positiveScenarios"] - count["falseNegatives"]
        summary = {"schemaVersion": 1, "agent": "offline extractive support RAG", "repeats": repeats,
                   "comparisons": len(records), **count,
                   "falsePositiveRate": count["falsePositives"] / count["negativeScenarios"],
                   "falseNegativeRate": count["falseNegatives"] / count["positiveScenarios"],
                   "limitations": "Controlled deterministic mutations with prespecified labels; repeated runs check stability, not independent model draws. No live LLM, production false-positive estimate, or user-adoption evidence.",
                   "records": records}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{len(records)} comparisons; false positives {count['falsePositives']}/{count['negativeScenarios']}; "
              f"missed regressions {count['falseNegatives']}/{count['positiveScenarios']}")
        print(f"Evidence: {output / 'summary.json'}")
        return 1 if count["falsePositives"] or count["falseNegatives"] else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "target/debug" / ("wraith.exe" if os.name == "nt" else "wraith"))
    parser.add_argument("--output", type=Path, default=ROOT / "reports/rag-pilot")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error("--repeats must be 1–100")
    sys.exit(pilot(args.binary, args.output, args.repeats))
