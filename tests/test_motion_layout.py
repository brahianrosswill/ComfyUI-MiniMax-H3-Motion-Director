from __future__ import annotations

import importlib

import torch
import pytest

import comfy.ldm.minimax.model as mm


def _cond_times(layout):
    return [
        float(layout.position_ids[start, 0])
        for start, _stop, kind in layout.segments
        if kind == "cond"
    ]


def test_first_last_and_interior_keyframe_positions(plugin_package):
    patches = importlib.import_module(f"{plugin_package.__name__}.patches")
    assert patches.motion_context_patch_status()[0]
    text_len, latent_t, frame_count = 7, 7, 22
    indices = [0, 1, 5, frame_count - 1]
    keyframes = [
        {"resolved_frame_index": 0, patches.MC_KEY: index}
        for index in indices
    ]
    layout = mm.PackedLayout(
        text_len, latent_t, 22, 38, 16,
        keyframes=keyframes,
        frame_count=frame_count,
    )
    assert _cond_times(layout) == pytest.approx([
        text_len + mm.FRAME_RESCALE * index for index in indices
    ])


def test_existing_refs_unchanged_and_only_marked_audio_moves(plugin_package):
    patches = importlib.import_module(f"{plugin_package.__name__}.patches")
    text_len, latent_t, frame_count = 7, 7, 22
    keyframes = [
        {"resolved_frame_index": 0, patches.MC_KEY: 0},
        {"resolved_frame_index": 0, patches.MC_KEY: 5},
    ]
    refs = [
        {"kind": "image", "latent_h": 8, "latent_w": 12},
        {
            "kind": "video",
            "latent_t": 2,
            "latent_h": 8,
            "latent_w": 12,
            "ref_audio_t": 0,
        },
        {"kind": "audio", "ref_audio_t": 8},
        {"kind": "audio", "ref_audio_t": 5},
    ]
    baseline = mm.PackedLayout(
        text_len, latent_t, 22, 38, 16,
        keyframes=keyframes,
        refs=refs,
        frame_count=frame_count,
    )
    marked = [dict(ref) for ref in refs]
    marked[2][patches.MC_AUDIO_KEY] = 5.0
    moved = mm.PackedLayout(
        text_len, latent_t, 22, 38, 16,
        keyframes=keyframes,
        refs=marked,
        frame_count=frame_count,
    )
    assert torch.equal(baseline.position_ids[:, 1:], moved.position_ids[:, 1:])
    changed = (baseline.position_ids[:, 0] != moved.position_ids[:, 0]).nonzero().flatten()
    assert int(changed.numel()) == 16  # 8 audio steps x H3's 2 audio rows
    unchanged = torch.ones(len(baseline.position_ids), dtype=torch.bool)
    unchanged[changed] = False
    assert torch.equal(
        baseline.position_ids[unchanged, 0], moved.position_ids[unchanged, 0]
    )


def test_multiple_motion_audio_markers_fail_loudly(plugin_package):
    patches = importlib.import_module(f"{plugin_package.__name__}.patches")
    refs = [
        {"kind": "audio", "ref_audio_t": 4, patches.MC_AUDIO_KEY: 5.0},
        {"kind": "audio", "ref_audio_t": 4, patches.MC_AUDIO_KEY: 5.0},
    ]
    with pytest.raises(RuntimeError, match="exactly one marked"):
        mm.PackedLayout(7, 7, 22, 38, 16, refs=refs, frame_count=22)
