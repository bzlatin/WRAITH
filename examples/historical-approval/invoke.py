"""Load the selected application snapshot; source paths are supplied by the runner."""

import importlib.util
import os
from pathlib import Path


async def evaluate(payload, context):
    source = Path(os.environ["WRAITH_APPROVAL_APP"]) / "approval_agent.py"
    spec = importlib.util.spec_from_file_location("approval_application", source)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return await app.evaluate(payload, context)
