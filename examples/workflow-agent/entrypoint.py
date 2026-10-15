"""One adapter; each checkout selects its own actual upstream application source."""

import json
import os
from pathlib import Path
import subprocess
import sys


def evaluate(payload, context):
    fixture = Path(__file__).resolve().parent
    source = Path.cwd().resolve()
    env = dict(
        os.environ,
        WRAITH_APP_SOURCE=str(source),
        PYTHONPATH=os.pathsep.join(
            map(str, [fixture / "offline", source / "src", fixture])
        ),
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        HF_TOKEN="offline-fixture",
        OPENAI_API_KEY="offline-fixture",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONOPTIMIZE="0",
    )
    command = [
        sys.executable,
        "-B",
        *(["-O"] if payload["optimized"] else []),
        str(fixture / "worker.py"),
    ]
    child = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )
    if child.returncode:
        raise RuntimeError("Upstream worker failed: " + child.stderr[-2000:])
    result = json.loads(child.stdout)
    for event in result.pop("events"):
        context.tool(**event)
    return result
