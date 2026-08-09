from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch

from _minimax_h3_motion_director_testpkg.director.audio_export import (
    _merge_generated_segment_audios,
)


def test_merged_audio_preserves_the_resolved_global_cut_boundary():
    plan = SimpleNamespace(
        segments=[
            SimpleNamespace(frame_count=10, start_frame=0, end_frame=10),
            SimpleNamespace(frame_count=10, start_frame=10, end_frame=20),
        ]
    )
    left = {
        "waveform": torch.zeros(1, 1, 120),
        "sample_rate": 100,
        "source_overlap_resolved": True,
        "source_start": 0,
        "source_end": 12,
        "frame_count": 12,
    }
    right = {
        "waveform": torch.ones(1, 1, 80),
        "sample_rate": 100,
        "source_overlap_resolved": True,
        "source_start": 12,
        "source_end": 20,
        "frame_count": 8,
    }

    merged = _merge_generated_segment_audios(
        plan, [left, right], total_frames=20, fps=10.0
    )

    waveform = merged["waveform"]
    assert waveform.shape[-1] == 200
    assert torch.count_nonzero(waveform[..., :120]).item() == 0
    assert torch.all(waveform[..., 120:] == 1)


def test_merged_resolved_audio_rejects_sample_rate_mismatch():
    plan = SimpleNamespace(segments=[])
    left = {
        "waveform": torch.zeros(1, 1, 100),
        "sample_rate": 100,
        "source_overlap_resolved": True,
        "source_start": 0,
        "source_end": 10,
        "frame_count": 10,
    }
    right = {
        "waveform": torch.zeros(1, 1, 200),
        "sample_rate": 200,
        "source_overlap_resolved": True,
        "source_start": 10,
        "source_end": 20,
        "frame_count": 10,
    }

    with pytest.raises(ValueError, match="sample rates differ"):
        _merge_generated_segment_audios(
            plan, [left, right], total_frames=20, fps=10.0
        )
