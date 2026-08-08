from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_frontend_sampling_visibility_migration_and_preview_contract():
    node = shutil.which("node")
    assert node, "Node.js is required for the frontend behavior contract test."
    harness = Path(__file__).with_name("sampling_ui_harness.mjs")
    subprocess.run([node, str(harness)], check=True)
