from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


KNOWN_AIMIXER_NODE_IDS = {
    "MiniMaxH3Director",
    "ComfyMiniMaxH3Director",
    "MiniMaxH3DirectorConditioning",
    "MiniMaxH3DirectorPlannerConditioning",
    "MiniMaxH3DirectorGroupImageToVideo",
    "MiniMaxH3DirectorGroupReferenceToVideo",
    "MiniMaxH3DirectorGroupsCombine",
}


def test_node_ids_are_disjoint_from_aimixer(plugin_package):
    ours = set(plugin_package.NODE_CLASS_MAPPINGS)
    assert ours
    assert ours.isdisjoint(KNOWN_AIMIXER_NODE_IDS)
    assert ours == {
        "MiniMaxH3MotionDirector",
        "MiniMaxH3MotionDirectorConditioning",
        "MiniMaxH3MotionDirectorPlannerConditioning",
        "MiniMaxH3MotionDirectorGroupImageToVideo",
        "MiniMaxH3MotionDirectorGroupReferenceToVideo",
        "MiniMaxH3MotionDirectorGroupsCombine",
    }


def test_runtime_modules_do_not_reuse_aimixer_routes_or_events():
    root = Path(__file__).resolve().parents[1]
    runtime_files = [root / "__init__.py"]
    runtime_files += list((root / "director").glob("*.py"))
    runtime_files += list((root / "nodes").glob("*.py"))
    runtime_files += list((root / "web" / "js").glob("*.js"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)

    assert "/minimax/director" not in combined
    assert "minimax_director_" not in combined
    assert '"MMX_DIR_GROUP"' not in combined
    assert "mmx_director_ui_locale" not in combined
    assert "_minimaxDirectorLayoutPatch" not in combined


def test_loads_beside_installed_aimixer(plugin_package, comfyui_root):
    original_root = comfyui_root / "custom_nodes" / "ComfyUI_MiniMaxH3_Director"
    init_file = original_root / "__init__.py"
    if not init_file.is_file():
        pytest.skip("AIMixer Director is not installed in this test environment")

    module_name = "aimixer_minimax_h3_director_coexistence_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        init_file,
        submodule_search_locations=[str(original_root)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        assert set(module.NODE_CLASS_MAPPINGS).isdisjoint(
            set(plugin_package.NODE_CLASS_MAPPINGS)
        )
    finally:
        for name in list(sys.modules):
            if name == module_name or name.startswith(module_name + "."):
                sys.modules.pop(name, None)
