# Portions derived from ComfyUI_MiniMaxH3_Director
# Copyright AIMixer and contributors
# Originally licensed under Apache License 2.0
# Modified for MiniMax H3 Motion Director, 2026-08-09
# This derivative project is distributed under GPL-3.0.
# See NOTICE and LICENSES/Apache-2.0-AIMixer.txt.

"""Per-segment helpers shared by the Director executor."""

from __future__ import annotations

import base64
import io

import torch
from PIL import Image

from ..lib.image_prep import fit_canvas, fit_video_long_edge
from ..lib.video_io import (
    load_timeline_segment,
    logical_frame_count,
    resolve_logical_frame_entry,
)
from .frame_align import pad_or_trim_frames
from .plan import DirectorPlan
from .source_overlap import SOURCE_OVERLAP_TASKS, SourceOverlapWindow


def needs_source_video(task_key: str) -> bool:
    return task_key in {"i2v", "fl2v", "v2v", "rv2v"}


def is_gen_timeline_plan(plan: DirectorPlan) -> bool:
    mode = str((plan.raw or {}).get("timelineMode") or "").lower()
    return mode in ("gen_blank", "gen_image", "prompt_batch", "image_batch", "fl2v")


def _timeline_neighbors(plan: DirectorPlan, seg):
    ordered = sorted(
        list(getattr(plan, "segments", None) or []),
        key=lambda item: int(getattr(item, "timeline_index", item.index)),
    )
    position = next(
        (
            index
            for index, candidate in enumerate(ordered)
            if candidate is seg
            or int(getattr(candidate, "timeline_index", candidate.index))
            == int(getattr(seg, "timeline_index", seg.index))
        ),
        None,
    )
    if position is None:
        return None, None
    previous = ordered[position - 1] if position > 0 else None
    following = ordered[position + 1] if position + 1 < len(ordered) else None
    return previous, following


def _same_overlap_chain(left, right) -> bool:
    return bool(
        left is not None
        and right is not None
        and getattr(left, "task_key", "") in SOURCE_OVERLAP_TASKS
        and getattr(right, "task_key", "") in SOURCE_OVERLAP_TASKS
        and getattr(left, "source_clip", None) is None
        and getattr(right, "source_clip", None) is None
        and int(left.end_frame) == int(right.start_frame)
    )


def _available_contiguous_source_frames(
    plan: DirectorPlan,
    boundary: int,
    requested: int,
    *,
    direction: int,
) -> int:
    requested = max(0, int(requested))
    if requested <= 0:
        return 0
    sv = plan.source_video
    if is_gen_timeline_plan(plan) and sv is not None and int(sv.shape[0]) > 0:
        total = int(sv.shape[0])
        return min(requested, boundary if direction < 0 else max(0, total - boundary))

    total = logical_frame_count(plan.raw)
    if boundary <= 0 and direction < 0:
        return 0
    if boundary >= total and direction > 0:
        return 0
    anchor = boundary - 1 if direction > 0 else boundary
    if anchor < 0 or anchor >= total:
        return 0
    clip_index, source_frame = resolve_logical_frame_entry(plan.raw, anchor)
    actual = 0
    if direction < 0:
        expected = source_frame - 1
        indices = range(boundary - 1, max(-1, boundary - requested - 1), -1)
    else:
        expected = source_frame + 1
        indices = range(boundary, min(total, boundary + requested))
    for logical_index in indices:
        next_clip, next_source = resolve_logical_frame_entry(plan.raw, logical_index)
        if next_clip != clip_index or next_source != expected:
            break
        actual += 1
        expected += direction
    return actual


def effective_source_overlap_window(
    plan: DirectorPlan,
    seg,
    requested_frames: int,
) -> SourceOverlapWindow:
    """Return the safe bidirectional real-source window for one segment."""
    nominal_start = max(0, int(seg.start_frame))
    nominal_end = max(nominal_start, int(seg.end_frame))
    requested = max(0, int(requested_frames))
    if (
        requested <= 0
        or getattr(seg, "task_key", "") not in SOURCE_OVERLAP_TASKS
        or getattr(seg, "source_clip", None) is not None
        or (plan.raw or {}).get("externalGroups", {}).get("active")
    ):
        return SourceOverlapWindow(
            nominal_start, nominal_end, nominal_start, nominal_end, 0, 0
        )

    previous, following = _timeline_neighbors(plan, seg)
    allow_head = _same_overlap_chain(previous, seg)
    allow_tail = _same_overlap_chain(seg, following)
    head_request = requested if allow_head else 0
    tail_request = requested if allow_tail else 0

    # A very short middle segment must leave strictly ordered cut windows.
    if head_request and tail_request:
        per_side_limit = max(0, (nominal_end - nominal_start - 1) // 2)
        head_request = min(head_request, per_side_limit)
        tail_request = min(tail_request, per_side_limit)

    head = _available_contiguous_source_frames(
        plan, nominal_start, head_request, direction=-1
    )
    tail = _available_contiguous_source_frames(
        plan, nominal_end, tail_request, direction=1
    )
    return SourceOverlapWindow(
        source_start=nominal_start - head,
        source_end=nominal_end + tail,
        nominal_start=nominal_start,
        nominal_end=nominal_end,
        head_overlap=head,
        tail_overlap=tail,
    )


def resolve_segment_raw_clip(plan: DirectorPlan, seg) -> torch.Tensor:
    """Prefer in-memory gen canvas / segment clip; fall back to timeline video decode."""
    if seg.source_clip is not None and seg.source_clip.shape[0] > 0:
        return seg.source_clip.clone()

    # Pure t2v (incl. external groups) has no source frames.
    if getattr(seg, "task_key", "") == "t2v":
        return torch.zeros((0, 16, 16, 3), dtype=torch.float32)

    sv = plan.source_video
    if is_gen_timeline_plan(plan) and sv is not None and int(sv.shape[0]) > 0:
        start = max(0, int(seg.start_frame))
        end = min(int(seg.end_frame), int(sv.shape[0]))
        if end > start:
            return sv[start:end].clone()

    if (plan.raw or {}).get("externalGroups", {}).get("active"):
        return torch.zeros((0, 16, 16, 3), dtype=torch.float32)

    return load_timeline_segment(plan.raw, seg.start_frame, seg.end_frame)


def resolve_segment_raw_clip_with_lookahead(
    plan: DirectorPlan,
    seg,
    *,
    end_extra: int = 0,
) -> torch.Tensor:
    """Like ``resolve_segment_raw_clip``, but may pull frames past ``seg.end_frame``.

    Extra frames are conditioning-only (continuity gen length matching); they are
    not kept in the exported segment after trim.
    """
    extra = max(0, int(end_extra))
    if extra <= 0:
        return resolve_segment_raw_clip(plan, seg)

    if seg.source_clip is not None and seg.source_clip.shape[0] > 0:
        # Gen canvases have no timeline lookahead beyond the clip itself.
        return seg.source_clip.clone()

    end = int(seg.end_frame) + extra
    sv = plan.source_video
    if is_gen_timeline_plan(plan) and sv is not None and int(sv.shape[0]) > 0:
        start = max(0, int(seg.start_frame))
        end = min(end, int(sv.shape[0]))
        if end > start:
            return sv[start:end].clone()

    total = logical_frame_count(plan.raw)
    start = max(0, int(seg.start_frame))
    visible_end = min(max(start, int(seg.end_frame)), total)
    end = min(max(visible_end, end), total)

    # Conditioning lookahead may continue only through sequential frames from
    # the same physical source clip. At a file boundary (or an edited source
    # jump), stop and let the dedicated H3 reference helper pad the tail.
    if end > visible_end and visible_end > start:
        clip_index, source_frame = resolve_logical_frame_entry(
            plan.raw, visible_end - 1
        )
        safe_end = visible_end
        expected_source_frame = source_frame + 1
        for logical_index in range(visible_end, end):
            next_clip, next_source_frame = resolve_logical_frame_entry(
                plan.raw, logical_index
            )
            if (
                next_clip != clip_index
                or next_source_frame != expected_source_frame
            ):
                break
            safe_end = logical_index + 1
            expected_source_frame += 1
        end = safe_end

    if end <= start:
        return resolve_segment_raw_clip(plan, seg)
    return load_timeline_segment(plan.raw, start, end)


def resolve_segment_raw_clip_with_source_overlap(
    plan: DirectorPlan,
    seg,
    *,
    window: SourceOverlapWindow | None = None,
    overlap_frames: int | None = None,
    end_extra: int = 0,
) -> torch.Tensor:
    """Load one V2V/RV2V reference window from the original source timeline.

    The returned tensor is ``head + visible + tail + safe lookahead``.
    It never contains the previous segment's generated output. Forward
    lookahead follows the same physical-continuity rule as the existing H3
    reference preparation, while BOF and clip boundaries reduce the overlap.
    """
    if window is None:
        window = effective_source_overlap_window(
            plan, seg, int(overlap_frames or 0)
        )
    if window.head_overlap <= 0 and window.tail_overlap <= 0:
        return resolve_segment_raw_clip_with_lookahead(
            plan, seg, end_extra=end_extra
        )

    extra = max(0, int(end_extra))
    start = int(window.source_start)
    internal_end = int(window.source_end)

    sv = plan.source_video
    if is_gen_timeline_plan(plan) and sv is not None and int(sv.shape[0]) > 0:
        end = min(internal_end + extra, int(sv.shape[0]))
        if end > start:
            return sv[start:end].clone()

    total = logical_frame_count(plan.raw)
    internal_end = min(internal_end, total)
    end = min(internal_end + extra, total)

    if end > internal_end and internal_end > start:
        clip_index, source_frame = resolve_logical_frame_entry(
            plan.raw, internal_end - 1
        )
        safe_end = internal_end
        expected_source_frame = source_frame + 1
        for logical_index in range(internal_end, end):
            next_clip, next_source_frame = resolve_logical_frame_entry(
                plan.raw, logical_index
            )
            if (
                next_clip != clip_index
                or next_source_frame != expected_source_frame
            ):
                break
            safe_end = logical_index + 1
            expected_source_frame += 1
        end = safe_end

    if end <= start:
        return resolve_segment_raw_clip(plan, seg)
    return load_timeline_segment(plan.raw, start, end)


def source_passthrough_chunk(plan: DirectorPlan, seg) -> torch.Tensor:
    """Scaled source frames for skipped v2v segments with no generation cache yet."""
    raw_clip = resolve_segment_raw_clip(plan, seg)
    target_len = raw_clip.shape[0]
    if plan.output_mode == "fixed":
        clip = fit_canvas(raw_clip, plan.width, plan.height)
    else:
        clip = fit_video_long_edge(raw_clip, plan.ref_max_size)
    return pad_or_trim_frames(clip, target_len).cpu().float()


def segment_passthrough_chunk(plan: DirectorPlan, seg) -> torch.Tensor | None:
    """Best-effort fill for skipped segments (gen source clip, then timeline video)."""
    if seg.source_clip is not None and seg.source_clip.shape[0] > 0:
        target_len = max(1, seg.frame_count or int(seg.source_clip.shape[0]))
        clip = seg.source_clip.clone()
        if clip.shape[0] > target_len:
            clip = clip[:target_len]
        return clip.cpu().float()
    if needs_source_video(seg.task_key):
        try:
            return source_passthrough_chunk(plan, seg)
        except Exception:
            return None
    return None


def tensor_frame_to_jpeg_b64(frame: torch.Tensor) -> str:
    arr = (frame.detach().cpu().clamp(0, 1).numpy() * 255).astype("uint8")
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def frames_label(seg) -> str:
    return f"帧 {seg.start_frame}–{seg.end_frame} ({seg.frame_count}f)"
