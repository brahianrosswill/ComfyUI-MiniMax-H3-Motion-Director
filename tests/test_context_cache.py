from __future__ import annotations

import importlib
import json
from types import SimpleNamespace

import pytest
import torch


def _segment(index=0, prompt="run forward"):
    return SimpleNamespace(
        index=index,
        start_frame=index * 124,
        end_frame=(index + 1) * 124,
        prompt=prompt,
        negative_prompt="",
        task_key="t2v",
        reference_video_meta={},
        reference_video_start_frame=0,
        source_clip=None,
        refs=[],
        ref_audios=[],
        ref_videos=[],
        ref_video_audios=[],
    )


def _plan(segments):
    return SimpleNamespace(
        raw={"version": 4, "video": {}, "videoClips": []},
        edit_mode="global",
        total_frames=sum(s.end_frame - s.start_frame for s in segments),
        frame_rate=24.0,
        width=16,
        height=16,
        output_mode="fixed",
        segments=segments,
    )


def test_selection_run_restores_exported_context_and_rejects_stale(plugin_package, tmp_path, monkeypatch):
    cache = importlib.import_module(
        f"{plugin_package.__name__}.director.context_cache"
    )
    monkeypatch.setattr(cache.folder_paths, "get_output_directory", lambda: str(tmp_path))
    segs = [_segment(0), _segment(1, "continue running")]
    plan = _plan(segs)
    settings = {"sampling_mode": "internal", "seed": 7, "context_length": 22}
    frames = torch.rand(124, 16, 16, 3)
    audio = {"waveform": torch.rand(1, 2, round(124 / 24 * 32000)), "sample_rate": 32000}
    assert cache.save_motion_context_cache(
        "node-1", segs[0], plan,
        frames=frames,
        audio=audio,
        settings=settings,
    )
    loaded = cache.load_motion_context_cache(
        "node-1", segs[0], plan, settings=settings, strict=True
    )
    assert torch.equal(loaded.frames, frames)
    assert torch.equal(loaded.audio["waveform"], audio["waveform"])

    segs[0].prompt = "changed prompt"
    with pytest.raises(cache.MotionContextCacheError, match="timeline or generation settings changed"):
        cache.load_motion_context_cache(
            "node-1", segs[0], plan, settings=settings, strict=True
        )


def test_external_group_selection_keeps_previous_segment_identity(plugin_package):
    groups_module = importlib.import_module(
        f"{plugin_package.__name__}.director.external_groups"
    )
    groups = [
        {
            "family": "i2v",
            "kind": "t2v",
            "prompt": f"segment {index}",
            "duration_sec": 1.0,
            "first_frame": None,
            "last_frame": None,
        }
        for index in range(3)
    ]
    timeline = json.dumps(
        {
            "version": 4,
            "runSelectEnabled": True,
            "runSelection": [2],
            "frameRate": 24,
            "output": {
                "mode": "fixed",
                "width": 16,
                "height": 16,
                "exportMode": "segments",
            },
            "global": {"prompt": ""},
        }
    )
    plan = groups_module.build_plan_from_external_groups(
        groups,
        family="i2v",
        timeline_data=timeline,
        task_type="t2v",
        global_prompt="",
        total_frames=66,
        frame_rate=24,
        width=16,
        height=16,
        ref_max_size=16,
    )
    assert len(plan.segments) == 3
    assert [segment.timeline_index for segment in plan.segments] == [0, 1, 2]
    assert plan.run_indices == frozenset({2})


def test_tensor_fingerprint_supports_bfloat16(plugin_package):
    cache = importlib.import_module(
        f"{plugin_package.__name__}.director.context_cache"
    )
    result = cache.tensor_fingerprint(torch.arange(16, dtype=torch.bfloat16))
    assert result["dtype"] == "torch.bfloat16"
    assert len(result["probe_sha256"]) == 64
