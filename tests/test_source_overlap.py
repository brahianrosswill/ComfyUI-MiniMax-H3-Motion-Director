from __future__ import annotations

import torch

from _minimax_h3_motion_director_testpkg.director.source_overlap import (
    SourceOverlapGeneration,
    assemble_source_overlap_generations,
    find_best_cut,
    should_apply_visual_motion_context,
)


def _frames(count: int, value: float = 0.0) -> torch.Tensor:
    return torch.full((count, 8, 12, 3), float(value), dtype=torch.float32)


def _generation(
    source_start: int,
    source_end: int,
    nominal_start: int,
    nominal_end: int,
    segment_index: int,
    *,
    value: float = 0.0,
    audio: dict | None = None,
    fps: float = 10.0,
) -> SourceOverlapGeneration:
    return SourceOverlapGeneration(
        frames=_frames(source_end - source_start, value),
        audio=audio,
        source_start=source_start,
        source_end=source_end,
        nominal_start=nominal_start,
        nominal_end=nominal_end,
        head_overlap=nominal_start - source_start,
        tail_overlap=source_end - nominal_end,
        fps=fps,
        segment_index=segment_index,
    )


def _force_cut(left: SourceOverlapGeneration, right: SourceOverlapGeneration, cut: int) -> None:
    left.frames[:] = 0.0
    right.frames[:] = 1.0
    right.frames[cut - right.source_start] = 0.0


def test_best_cut_uses_the_most_similar_generated_seam_pair():
    left = _generation(0, 12, 0, 10, 0)
    right = _generation(8, 20, 10, 20, 1, value=1.0)
    _force_cut(left, right, 11)

    boundary = find_best_cut(left, right, nominal_boundary=10)

    assert boundary.common_start == 8
    assert boundary.common_end == 12
    assert boundary.resolved_cut == 11
    assert boundary.score == 0.0


def test_best_cut_tie_prefers_the_nominal_boundary():
    left = _generation(0, 13, 0, 10, 0)
    right = _generation(7, 20, 10, 20, 1)

    boundary = find_best_cut(left, right, nominal_boundary=10)

    assert boundary.resolved_cut == 10


def test_nominal_cut_keeps_total_frame_count():
    left = _generation(0, 12, 0, 10, 0)
    right = _generation(8, 20, 10, 20, 1)
    _force_cut(left, right, 10)

    result = assemble_source_overlap_generations([left, right])

    assert [item.frame_count for item in result.contributions] == [10, 10]
    assert result.frame_count == 20


def test_positive_cut_offset_moves_ownership_without_changing_duration():
    left = _generation(0, 13, 0, 10, 0)
    right = _generation(7, 20, 10, 20, 1)
    _force_cut(left, right, 12)

    result = assemble_source_overlap_generations([left, right])

    assert result.boundaries[0].resolved_cut == 12
    assert result.boundaries[0].cut_offset == 2
    assert [item.frame_count for item in result.contributions] == [12, 8]
    assert result.frame_count == 20


def test_negative_cut_offset_moves_ownership_without_changing_duration():
    left = _generation(0, 13, 0, 10, 0)
    right = _generation(7, 20, 10, 20, 1)
    _force_cut(left, right, 8)

    result = assemble_source_overlap_generations([left, right])

    assert result.boundaries[0].resolved_cut == 8
    assert result.boundaries[0].cut_offset == -2
    assert [item.frame_count for item in result.contributions] == [8, 12]
    assert result.frame_count == 20


def test_three_segments_cover_each_source_time_exactly_once():
    generations = [
        _generation(0, 13, 0, 10, 0),
        _generation(7, 23, 10, 20, 1),
        _generation(17, 30, 20, 30, 2),
    ]
    for gen in generations:
        for source_time in range(gen.source_start, gen.source_end):
            gen.frames[source_time - gen.source_start] = source_time / 100.0

    result = assemble_source_overlap_generations(generations)
    encoded = result.frames[:, 0, 0, 0]

    assert [b.resolved_cut for b in result.boundaries] == [10, 20]
    assert result.frame_count == 30
    assert torch.allclose(encoded, torch.arange(30, dtype=torch.float32) / 100.0)
    assert [item.source_start for item in result.contributions] == [0, 10, 20]
    assert [item.source_end for item in result.contributions] == [10, 20, 30]


def test_audio_uses_the_same_positive_resolved_cut():
    sample_rate = 100
    left_audio = {
        "waveform": torch.arange(130, dtype=torch.float32).reshape(1, 1, -1),
        "sample_rate": sample_rate,
    }
    right_audio = {
        "waveform": torch.arange(130, dtype=torch.float32).reshape(1, 1, -1),
        "sample_rate": sample_rate,
    }
    left = _generation(0, 13, 0, 10, 0, audio=left_audio)
    right = _generation(7, 20, 10, 20, 1, audio=right_audio)
    _force_cut(left, right, 12)

    result = assemble_source_overlap_generations([left, right])

    left_wave = result.contributions[0].audio["waveform"]
    right_wave = result.contributions[1].audio["waveform"]
    assert left_wave.shape[-1] == 120
    assert right_wave.shape[-1] == 80
    # source time 12 maps to local sample 50 in a generation starting at 7.
    assert right_wave[0, 0, 0].item() == 50.0
    assert left_wave.shape[-1] + right_wave.shape[-1] == 200


def test_generated_audio_sample_rate_mismatch_fails_loud():
    left = _generation(
        0, 12, 0, 10, 0,
        audio={"waveform": torch.zeros(1, 1, 120), "sample_rate": 100},
    )
    right = _generation(
        8, 20, 10, 20, 1,
        audio={"waveform": torch.zeros(1, 1, 120), "sample_rate": 200},
    )

    try:
        assemble_source_overlap_generations([left, right])
    except ValueError as exc:
        assert "sample rate" in str(exc).lower()
    else:
        raise AssertionError("sample-rate mismatch must not be silently resampled")


def test_visual_motion_context_is_skipped_only_for_video_edit_overlap():
    assert not should_apply_visual_motion_context(True, "v2v", 1, 5, False)
    assert not should_apply_visual_motion_context(True, "rv2v", 1, 5, False)
    assert should_apply_visual_motion_context(True, "r2v", 1, 5, False)
    assert should_apply_visual_motion_context(True, "v2v", 1, 0, False)
    assert not should_apply_visual_motion_context(False, "v2v", 1, 5, False)
