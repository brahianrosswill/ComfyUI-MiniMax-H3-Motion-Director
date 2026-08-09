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


def needs_source_video(task_key: str) -> bool:
    return task_key in {"i2v", "fl2v", "v2v", "rv2v"}


def is_gen_timeline_plan(plan: DirectorPlan) -> bool:
    mode = str((plan.raw or {}).get("timelineMode") or "").lower()
    return mode in ("gen_blank", "gen_image", "prompt_batch", "image_batch", "fl2v")


def effective_source_overlap_frames(
    plan: DirectorPlan,
    seg,
    requested_frames: int,
) -> int:
    """Return the original-source prefix available to this V2V/RV2V segment.

    Source Overlap is intentionally unavailable for the first timeline slot,
    other task families, and per-segment generated ``source_clip`` inputs. For
    edited timelines it also stops at a physical source discontinuity instead
    of borrowing frames from an unrelated clip.
    """
    requested = max(0, int(requested_frames))
    if (
        requested <= 0
        or getattr(seg, "task_key", "") not in {"v2v", "rv2v"}
        or int(getattr(seg, "timeline_index", 0)) <= 0
        or getattr(seg, "source_clip", None) is not None
    ):
        return 0

    visible_start = max(0, int(seg.start_frame))
    if visible_start <= 0:
        return 0

    sv = plan.source_video
    if is_gen_timeline_plan(plan) and sv is not None and int(sv.shape[0]) > 0:
        if visible_start >= int(sv.shape[0]):
            return 0
        return min(requested, visible_start)

    if (plan.raw or {}).get("externalGroups", {}).get("active"):
        return 0

    total = logical_frame_count(plan.raw)
    if visible_start >= total:
        return 0

    available = min(requested, visible_start)
    clip_index, source_frame = resolve_logical_frame_entry(plan.raw, visible_start)
    actual = 0
    expected_source_frame = source_frame - 1
    for logical_index in range(visible_start - 1, visible_start - available - 1, -1):
        previous_clip, previous_source_frame = resolve_logical_frame_entry(
            plan.raw, logical_index
        )
        if (
            previous_clip != clip_index
            or previous_source_frame != expected_source_frame
        ):
            break
        actual += 1
        expected_source_frame -= 1
    return actual


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
    overlap_frames: int,
    end_extra: int = 0,
) -> torch.Tensor:
    """Load one V2V/RV2V reference window from the original source timeline.

    The returned tensor is ``source overlap + visible source + safe lookahead``.
    It never contains the previous segment's generated output. Forward
    lookahead follows the same physical-continuity rule as the existing H3
    reference preparation, while BOF and clip boundaries reduce the overlap.
    """
    overlap = effective_source_overlap_frames(plan, seg, overlap_frames)
    if overlap <= 0:
        return resolve_segment_raw_clip_with_lookahead(
            plan, seg, end_extra=end_extra
        )

    extra = max(0, int(end_extra))
    visible_start = max(0, int(seg.start_frame))
    start = visible_start - overlap
    visible_end = max(visible_start, int(seg.end_frame))

    sv = plan.source_video
    if is_gen_timeline_plan(plan) and sv is not None and int(sv.shape[0]) > 0:
        end = min(visible_end + extra, int(sv.shape[0]))
        if end > start:
            return sv[start:end].clone()

    total = logical_frame_count(plan.raw)
    visible_end = min(visible_end, total)
    end = min(visible_end + extra, total)

    if end > visible_end and visible_end > visible_start:
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
