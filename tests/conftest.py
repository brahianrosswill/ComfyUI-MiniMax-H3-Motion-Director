from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
_comfyui_env = os.environ.get("COMFYUI_ROOT")
if not _comfyui_env:
    raise pytest.UsageError(
        "Set COMFYUI_ROOT to the ComfyUI directory before running pytest."
    )
COMFYUI_ROOT = Path(_comfyui_env).expanduser().resolve()

if not (COMFYUI_ROOT / "comfy").is_dir():
    raise pytest.UsageError(f"COMFYUI_ROOT is invalid: {COMFYUI_ROOT}")
sys.path.insert(0, str(COMFYUI_ROOT))

pytest.importorskip("comfy")

# ComfyUI selects a CUDA device while importing model_management unless its
# CLI state already says CPU. GitHub's runner uses CPU-only PyTorch, so set the
# same supported flag before importing the plugin. Real GPU test environments
# keep their normal device selection.
import torch

if os.environ.get("MINIMAX_H3_FORCE_CPU") == "1" or not torch.cuda.is_available():
    from comfy.cli_args import args as comfy_args

    comfy_args.cpu = True

PACKAGE_NAME = "minimax_h3_motion_director_under_test"
if PACKAGE_NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Motion Director package for tests")
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = package
    spec.loader.exec_module(package)


@pytest.fixture(scope="session")
def plugin_package():
    return sys.modules[PACKAGE_NAME]


@pytest.fixture(scope="session")
def comfyui_root():
    return COMFYUI_ROOT
