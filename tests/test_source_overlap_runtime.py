from __future__ import annotations

from types import SimpleNamespace

import torch

from _minimax_h3_motion_director_testpkg.director.frame_align import (
    minimax_align_frame_count,
    prepare_h3_reference_video_clip,
)
from _minimax_h3_motion_director_testpkg.director.segment_runtime import (
    effective_source_overlap_window,
    resolve_segment_raw_clip_with_source_overlap,
)


def _segment(index: int, start: int, end: int, task: str = "v2v"):
    return SimpleNamespace(
        index=index,
        timeline_index=index,
        start_frame=start,
        end_frame=end,
        frame_count=end - start,
        task_key=task,
        source_clip=None,
    )


def _plan(segments, count: int = 30, raw: dict | None = None):
    return SimpleNamespace(
        segments=list(segments),
        source_video=torch.arange(count, dtype=torch.float32).reshape(count, 1, 1, 1).repeat(1, 2, 2, 3),
        raw=raw or {"timelineMode": "gen_blank"},
    )


def test_first_segment_has_only_tail_and_last_has_only_head_overlap():
    segs = [_segment(0, 0, 10), _segment(1, 10, 20)]
    plan = _plan(segs, 20)

    first = effective_source_overlap_window(plan, segs[0], 2)
    last = effective_source_overlap_window(plan, segs[1], 2)

    assert (first.head_overlap, first.tail_overlap) == (0, 2)
    assert (first.source_start, first.source_end) == (0, 12)
    assert (last.head_overlap, last.tail_overlap) == (2, 0)
    assert (last.source_start, last.source_end) == (8, 20)


def test_middle_segment_gets_bidirectional_overlap():
    segs = [_segment(0, 0, 10), _segment(1, 10, 20), _segment(2, 20, 30)]
    window = effective_source_overlap_window(_plan(segs), segs[1], 3)

    assert (window.head_overlap, window.tail_overlap) == (3, 3)
    assert (window.source_start, window.source_end) == (7, 23)


def test_short_middle_segment_clamps_both_sides_so_cut_windows_cannot_cross():
    segs = [_segment(0, 0, 10), _segment(1, 10, 13), _segment(2, 13, 23)]
    window = effective_source_overlap_window(_plan(segs, 23), segs[1], 5)

    assert (window.head_overlap, window.tail_overlap) == (1, 1)


def test_bof_and_eof_are_never_crossed():
    segs = [_segment(0, 0, 3), _segment(1, 3, 6)]
    plan = _plan(segs, 6)

    assert effective_source_overlap_window(plan, segs[0], 5).head_overlap == 0
    assert effective_source_overlap_window(plan, segs[1], 5).tail_overlap == 0
    assert effective_source_overlap_window(plan, segs[1], 5).source_start == 0


def test_overlap_does_not_cross_a_physical_source_file_boundary():
    frame_map = [
        {"clip": 0, "frame": i} for i in range(10)
    ] + [{"clip": 1, "frame": i} for i in range(10)]
    raw = {"video": {"frameMap": frame_map}, "videoClips": [{}, {}]}
    segs = [_segment(0, 0, 10), _segment(1, 10, 20)]
    plan = _plan(segs, 20, raw)
    plan.source_video = torch.zeros((0, 2, 2, 3))

    assert effective_source_overlap_window(plan, segs[0], 5).tail_overlap == 0
    assert effective_source_overlap_window(plan, segs[1], 5).head_overlap == 0


def test_overlap_does_not_cross_an_edited_source_jump():
    frame_map = [
        {"clip": 0, "frame": i} for i in range(10)
    ] + [{"clip": 0, "frame": 20 + i} for i in range(10)]
    raw = {"video": {"frameMap": frame_map}, "videoClips": [{}]}
    segs = [_segment(0, 0, 10), _segment(1, 10, 20)]
    plan = _plan(segs, 20, raw)
    plan.source_video = torch.zeros((0, 2, 2, 3))

    assert effective_source_overlap_window(plan, segs[0], 5).tail_overlap == 0
    assert effective_source_overlap_window(plan, segs[1], 5).head_overlap == 0


def test_v2v_and_rv2v_apply_but_r2v_does_not():
    for task in ("v2v", "rv2v"):
        segs = [_segment(0, 0, 10, task), _segment(1, 10, 20, task)]
        assert effective_source_overlap_window(_plan(segs, 20), segs[1], 2).head_overlap == 2

    r2v = [_segment(0, 0, 10, "r2v"), _segment(1, 10, 20, "r2v")]
    window = effective_source_overlap_window(_plan(r2v, 20), r2v[1], 5)
    assert (window.head_overlap, window.tail_overlap) == (0, 0)


def test_zero_setting_restores_nominal_non_overlap_window():
    segs = [_segment(0, 0, 10), _segment(1, 10, 20)]
    window = effective_source_overlap_window(_plan(segs, 20), segs[1], 0)

    assert (window.source_start, window.source_end) == (10, 20)
    assert (window.head_overlap, window.tail_overlap) == (0, 0)


def test_extended_source_preserves_h3_17k_plus_5_alignment():
    segs = [_segment(0, 0, 50), _segment(1, 50, 172), _segment(2, 172, 200)]
    plan = _plan(segs, 200)
    window = effective_source_overlap_window(plan, segs[1], 5)
    assert window.frame_count == 132

    target = minimax_align_frame_count(window.frame_count)
    raw = resolve_segment_raw_clip_with_source_overlap(
        plan,
        segs[1],
        window=window,
        end_extra=target - window.frame_count,
    )
    prepared, pad_count = prepare_h3_reference_video_clip(raw, target)

    assert target == 141
    assert prepared.shape[0] == 141
    assert prepared.shape[0] % 17 == 5
    assert pad_count == 0
