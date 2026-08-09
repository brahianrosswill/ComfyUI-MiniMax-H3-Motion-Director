from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

from _minimax_h3_motion_director_testpkg.director.frame_align import (
    H3_SOURCE_OVERLAP_PIPELINE,
)
from _minimax_h3_motion_director_testpkg.director.source_overlap import (
    SourceOverlapGeneration,
)
from _minimax_h3_motion_director_testpkg.director import source_overlap_cache


def _segment():
    return SimpleNamespace(
        index=0,
        timeline_index=0,
        start_frame=0,
        end_frame=10,
        prompt="test",
        negative_prompt="",
        task_key="v2v",
        reference_video_meta={},
        reference_video_start_frame=0,
        source_clip=None,
        refs=[],
        ref_audios=[],
        ref_videos=[],
        ref_video_audios=[],
    )


def _plan(seg):
    return SimpleNamespace(
        frame_rate=10.0,
        total_frames=10,
        width=12,
        height=8,
        output_mode="fixed",
        edit_mode="segmented",
        source_overlap_frames=2,
        source_video=torch.zeros(10, 8, 12, 3),
        segments=[seg],
        raw={"version": 1, "timelineMode": "gen_blank"},
    )


def _generation():
    return SourceOverlapGeneration(
        frames=torch.zeros(12, 8, 12, 3),
        audio={"waveform": torch.zeros(1, 1, 120), "sample_rate": 100},
        source_start=0,
        source_end=12,
        nominal_start=0,
        nominal_end=10,
        head_overlap=0,
        tail_overlap=2,
        fps=10.0,
        segment_index=0,
    )


def test_v1_pipeline_marker_is_invalidated():
    assert H3_SOURCE_OVERLAP_PIPELINE == "v2v_rv2v_bidirectional_best_cut_v2"


def test_extended_cache_round_trip_and_v1_payload_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(source_overlap_cache, "_cache_root", lambda _node_id: tmp_path)
    seg = _segment()
    plan = _plan(seg)
    settings = {"seed": 7, "source_overlap_pipeline": H3_SOURCE_OVERLAP_PIPELINE}

    assert source_overlap_cache.save_source_overlap_cache(
        "node", seg, plan, generation=_generation(), settings=settings
    )
    loaded = source_overlap_cache.load_source_overlap_cache(
        "node", seg, plan, settings=settings, strict=True
    )
    assert loaded.source_start == 0
    assert loaded.source_end == 12
    assert loaded.frames.shape[0] == 12
    assert loaded.audio["waveform"].shape[-1] == 120

    path = tmp_path / "seg_0000.pt"
    payload = torch.load(path, map_location="cpu", weights_only=True)
    payload["format"] = "minimax_h3_source_overlap_extended_v1"
    payload["version"] = 1
    torch.save(payload, path)

    with pytest.raises(source_overlap_cache.SourceOverlapCacheError):
        source_overlap_cache.load_source_overlap_cache(
            "node", seg, plan, settings=settings, strict=True
        )


def test_selection_run_missing_adjacent_extended_cache_fails_loud(tmp_path, monkeypatch):
    monkeypatch.setattr(source_overlap_cache, "_cache_root", lambda _node_id: tmp_path)
    seg = _segment()

    with pytest.raises(source_overlap_cache.SourceOverlapCacheError) as caught:
        source_overlap_cache.load_source_overlap_cache(
            "node",
            seg,
            _plan(seg),
            settings={"seed": 7},
            strict=True,
        )

    message = str(caught.value)
    assert "adjacent segment's extended Source Overlap cache" in message
    assert "Run the full sequence once to build it" in message
