"""Wraith subprocess adapter for normal and optimized upstream execution."""

import json
from pathlib import Path
import subprocess
import sys


def evaluate(payload, context):
    args = [sys.executable, "-B"]
    if payload["optimized"]:
        args += ["-O"]
    args += [str(Path(__file__).with_name("worker.py"))]
    child = subprocess.run(
        args, input=json.dumps(payload), capture_output=True, text=True, timeout=30
    )
    if child.returncode != 0:
        raise RuntimeError("Upstream worker failed: " + child.stderr[-2000:])
    result = json.loads(child.stdout)
    for event in result.pop("events"):
        context.tool(**event)
    return result
