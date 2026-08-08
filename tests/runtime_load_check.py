"""Real ComfyUI custom-node loader smoke test; run as a script, not by pytest."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_comfyui_env = os.environ.get("COMFYUI_ROOT")
if not _comfyui_env:
    raise SystemExit("Set COMFYUI_ROOT to the ComfyUI directory first.")
COMFY_ROOT = Path(_comfyui_env).expanduser().resolve()
AIMIXER_ROOT = COMFY_ROOT / "custom_nodes" / "ComfyUI_MiniMaxH3_Director"


async def main() -> None:
    if not (COMFY_ROOT / "nodes.py").is_file():
        raise SystemExit(f"COMFYUI_ROOT is invalid: {COMFY_ROOT}")
    sys.path.insert(0, str(COMFY_ROOT))
    os.chdir(COMFY_ROOT)

    import nodes

    if AIMIXER_ROOT.is_dir():
        loaded = await nodes.load_custom_node(str(AIMIXER_ROOT))
        if not loaded:
            raise RuntimeError("ComfyUI failed to load installed AIMixer Director")

    loaded = await nodes.load_custom_node(str(PROJECT_ROOT))
    if not loaded:
        raise RuntimeError("ComfyUI failed to load MiniMax H3 Motion Director")

    required = {
        "MiniMaxH3MotionDirector",
        "MiniMaxH3MotionDirectorConditioning",
        "MiniMaxH3MotionDirectorPlannerConditioning",
        "MiniMaxH3MotionDirectorGroupImageToVideo",
        "MiniMaxH3MotionDirectorGroupReferenceToVideo",
        "MiniMaxH3MotionDirectorGroupsCombine",
    }
    missing = required.difference(nodes.NODE_CLASS_MAPPINGS)
    if missing:
        raise RuntimeError(f"Motion Director nodes missing after load: {sorted(missing)}")
    if AIMIXER_ROOT.is_dir() and "MiniMaxH3Director" not in nodes.NODE_CLASS_MAPPINGS:
        raise RuntimeError("AIMixer Director disappeared after Motion Director loaded")

    cls = nodes.NODE_CLASS_MAPPINGS["MiniMaxH3MotionDirector"]
    optional = cls.INPUT_TYPES()["optional"]
    if optional["sampler"][0] != "SAMPLER" or optional["sigmas"][0] != "SIGMAS":
        raise RuntimeError("External Advanced Sampling socket types are incorrect")
    print("RUNTIME_LOAD_OK")
    print("MOTION_NODE_COUNT=6")
    print(f"AIMIXER_COEXISTS={AIMIXER_ROOT.is_dir()}")


if __name__ == "__main__":
    asyncio.run(main())
