# Portions derived from ComfyUI_MiniMaxH3_Director
# Copyright AIMixer and contributors
# Originally licensed under Apache License 2.0
# Modified for MiniMax H3 Motion Director, 2026-08-10
# This derivative project is distributed under GPL-3.0.
# See NOTICE and LICENSES/Apache-2.0-AIMixer.txt.

"""Bidirectional generated Source Overlap and deterministic Best Cut stitching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
import torch.nn.functional as F

from .audio_trim import audio_has_samples


SOURCE_OVERLAP_TASKS = frozenset({"v2v", "rv2v"})
BEST_CUT_SCORE_EPSILON = 1e-6


@dataclass(frozen=True)
class SourceOverlapWindow:
    """Real source-time window used by one internal H3 generation."""

    source_start: int
    source_end: int
    nominal_start: int
    nominal_end: int
    head_overlap: int
    tail_overlap: int

    @property
    def frame_count(self) -> int:
        return int(self.source_end) - int(self.source_start)


@dataclass
class SourceOverlapGeneration:
    """Decoded extended output with a one-to-one original source-time mapping."""

    frames: torch.Tensor
    audio: dict[str, Any] | None
    source_start: int
    source_end: int
    nominal_start: int
    nominal_end: int
    head_overlap: int
    tail_overlap: int
    fps: float
    segment_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.frames, torch.Tensor) or self.frames.ndim != 4:
            raise ValueError("Source Overlap frames must be an IMAGE tensor [N,H,W,C].")
        if int(self.source_end) <= int(self.source_start):
            raise ValueError("Source Overlap source interval must contain at least one frame.")
        mapped = int(self.source_end) - int(self.source_start)
        if int(self.frames.shape[0]) != mapped:
            raise ValueError(
                "Source Overlap generated frame count does not match its source-time "
                f"interval ({int(self.frames.shape[0])} != {mapped})."
            )
        if not (
            int(self.source_start)
            <= int(self.nominal_start)
            < int(self.nominal_end)
            <= int(self.source_end)
        ):
            raise ValueError("Source Overlap nominal interval is outside its generated window.")
        if int(self.head_overlap) != int(self.nominal_start) - int(self.source_start):
            raise ValueError("Source Overlap head metadata does not match source-time mapping.")
        if int(self.tail_overlap) != int(self.source_end) - int(self.nominal_end):
            raise ValueError("Source Overlap tail metadata does not match source-time mapping.")
        if float(self.fps) <= 0:
            raise ValueError("Source Overlap FPS must be positive.")


@dataclass(frozen=True)
class ResolvedSourceOverlapBoundary:
    left_segment_index: int
    right_segment_index: int
    nominal_boundary: int
    resolved_cut: int
    common_start: int
    common_end: int
    score: float

    @property
    def cut_offset(self) -> int:
        return int(self.resolved_cut) - int(self.nominal_boundary)


@dataclass
class SourceOverlapContribution:
    segment_index: int
    source_start: int
    source_end: int
    frames: torch.Tensor
    audio: dict[str, Any] | None

    @property
    def frame_count(self) -> int:
        return int(self.source_end) - int(self.source_start)


@dataclass
class SourceOverlapAssembly:
    contributions: list[SourceOverlapContribution]
    boundaries: list[ResolvedSourceOverlapBoundary]

    @property
    def frames(self) -> torch.Tensor:
        if not self.contributions:
            raise ValueError("Source Overlap assembly has no contributions.")
        return torch.cat([item.frames for item in self.contributions], dim=0)

    @property
    def frame_count(self) -> int:
        return sum(item.frame_count for item in self.contributions)


def bidirectional_source_overlap_enabled(task_key: str, overlap_frames: int) -> bool:
    return str(task_key) in SOURCE_OVERLAP_TASKS and int(overlap_frames) > 0


def should_apply_visual_motion_context(
    motion_enabled: bool,
    task_key: str,
    timeline_slot: int,
    source_overlap_frames: int,
    explicit_i2v_reset: bool,
) -> bool:
    """Keep visual MC independent from V2V/RV2V Source Overlap v2."""
    if not motion_enabled or int(timeline_slot) <= 0 or explicit_i2v_reset:
        return False
    return not bidirectional_source_overlap_enabled(task_key, source_overlap_frames)


def _resize_frame_for_score(frame: torch.Tensor, *, max_side: int = 128) -> torch.Tensor:
    if not isinstance(frame, torch.Tensor) or frame.ndim != 3:
        raise ValueError("Best Cut expects an RGB frame [H,W,C].")
    rgb = frame[..., :3].detach().float().permute(2, 0, 1).unsqueeze(0)
    height, width = int(rgb.shape[-2]), int(rgb.shape[-1])
    longest = max(height, width)
    if longest > max(1, int(max_side)):
        scale = float(max_side) / float(longest)
        target_h = max(1, int(round(height * scale)))
        target_w = max(1, int(round(width * scale)))
        rgb = F.interpolate(
            rgb,
            size=(target_h, target_w),
            mode="bilinear",
            align_corners=False,
        )
    return rgb


def seam_score(left_frame: torch.Tensor, right_frame: torch.Tensor) -> float:
    """Mean absolute RGB difference after proportional downscale to <=128px."""
    left = _resize_frame_for_score(left_frame)
    right = _resize_frame_for_score(right_frame)
    if left.shape[-2:] != right.shape[-2:]:
        right = F.interpolate(
            right,
            size=left.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )
    return float(torch.mean(torch.abs(left - right)).item())


def _candidate_cuts(
    left: SourceOverlapGeneration,
    right: SourceOverlapGeneration,
    *,
    minimum_cut: int | None = None,
) -> tuple[int, int, list[int]]:
    common_start = max(int(left.source_start), int(right.source_start))
    common_end = min(int(left.source_end), int(right.source_end))
    if common_end <= common_start:
        raise ValueError(
            "V2V/RV2V Source Overlap generations have no common generated "
            "source-time interval. Run the full sequence with continuous source video."
        )

    # c is a boundary between source-time frames c-1 and c.  Search boundary
    # positions spanning the closed extent of the common generated interval,
    # while requiring both actual seam frames to exist in their generations.
    first = max(common_start, int(left.source_start) + 1, int(right.source_start))
    last = min(common_end, int(left.source_end), int(right.source_end) - 1)
    if minimum_cut is not None:
        first = max(first, int(minimum_cut))
    cuts = list(range(first, last + 1))
    if not cuts:
        raise ValueError(
            "V2V/RV2V Source Overlap common region is too short for a safe Best Cut."
        )
    return common_start, common_end, cuts


def find_best_cut(
    left: SourceOverlapGeneration,
    right: SourceOverlapGeneration,
    nominal_boundary: int,
    *,
    minimum_cut: int | None = None,
) -> ResolvedSourceOverlapBoundary:
    """Choose c minimizing mean(abs(left[c-1] - right[c]))."""
    common_start, common_end, candidates = _candidate_cuts(
        left, right, minimum_cut=minimum_cut
    )
    nominal = int(nominal_boundary)
    best_cut: int | None = None
    best_score: float | None = None
    for cut in candidates:
        left_frame = left.frames[cut - 1 - int(left.source_start)]
        right_frame = right.frames[cut - int(right.source_start)]
        score = seam_score(left_frame, right_frame)
        if best_score is None or score < best_score - BEST_CUT_SCORE_EPSILON:
            best_cut, best_score = cut, score
            continue
        if abs(score - best_score) <= BEST_CUT_SCORE_EPSILON:
            current_key = (abs(cut - nominal), cut)
            best_key = (abs(int(best_cut) - nominal), int(best_cut))
            if current_key < best_key:
                best_cut, best_score = cut, score

    assert best_cut is not None and best_score is not None
    return ResolvedSourceOverlapBoundary(
        left_segment_index=int(left.segment_index),
        right_segment_index=int(right.segment_index),
        nominal_boundary=nominal,
        resolved_cut=best_cut,
        common_start=common_start,
        common_end=common_end,
        score=best_score,
    )


def _global_audio_boundary(frame: int, fps: float, sample_rate: int) -> int:
    return int(round(int(frame) / float(fps) * int(sample_rate)))


def _slice_audio(
    generation: SourceOverlapGeneration,
    source_start: int,
    source_end: int,
) -> dict[str, Any] | None:
    audio = generation.audio
    if not audio_has_samples(audio):
        return None
    waveform = audio["waveform"]
    if waveform.ndim != 3:
        raise ValueError("Source Overlap AUDIO waveform must be [batch, channels, samples].")
    sample_rate = int(audio.get("sample_rate") or 0)
    if sample_rate <= 0:
        raise ValueError("Source Overlap AUDIO sample rate must be positive.")
    base = _global_audio_boundary(generation.source_start, generation.fps, sample_rate)
    start = _global_audio_boundary(source_start, generation.fps, sample_rate) - base
    stop = _global_audio_boundary(source_end, generation.fps, sample_rate) - base
    if start < 0 or stop <= start:
        raise ValueError("Source Overlap audio cut is outside its source-time interval.")
    have = int(waveform.shape[-1])
    if stop > have:
        missing = stop - have
        tolerance = max(1, int(round(sample_rate / 40.0)))
        if missing > tolerance:
            raise ValueError(
                "Source Overlap generated audio is too short for the resolved video cut."
            )
        pad = torch.zeros(
            *waveform.shape[:-1],
            missing,
            dtype=waveform.dtype,
            device=waveform.device,
        )
        waveform = torch.cat((waveform, pad), dim=-1)
    return {
        "waveform": waveform[..., start:stop].contiguous(),
        "sample_rate": sample_rate,
        "source_overlap_resolved": True,
        "source_start": int(source_start),
        "source_end": int(source_end),
        "frame_count": int(source_end) - int(source_start),
        "fps": float(generation.fps),
    }


def _slice_contribution(
    generation: SourceOverlapGeneration,
    source_start: int,
    source_end: int,
) -> SourceOverlapContribution:
    if not (
        int(generation.source_start)
        <= int(source_start)
        < int(source_end)
        <= int(generation.source_end)
    ):
        raise ValueError("Resolved Source Overlap contribution exceeds generated coverage.")
    start = int(source_start) - int(generation.source_start)
    end = int(source_end) - int(generation.source_start)
    frames = generation.frames[start:end]
    if int(frames.shape[0]) != int(source_end) - int(source_start):
        raise RuntimeError("Source Overlap contribution lost source-time frames.")
    return SourceOverlapContribution(
        segment_index=int(generation.segment_index),
        source_start=int(source_start),
        source_end=int(source_end),
        frames=frames,
        audio=_slice_audio(generation, int(source_start), int(source_end)),
    )


def assemble_source_overlap_generations(
    generations: list[SourceOverlapGeneration],
) -> SourceOverlapAssembly:
    """Resolve all adjacent cuts, then assign every source-time frame exactly once."""
    if not generations:
        raise ValueError("Source Overlap assembly requires at least one generation.")
    ordered = sorted(
        generations,
        key=lambda item: (int(item.nominal_start), int(item.segment_index)),
    )
    for left, right in zip(ordered, ordered[1:]):
        if int(left.nominal_end) != int(right.nominal_start):
            raise ValueError(
                "V2V/RV2V Best Cut requires adjacent nominal source-time segments "
                "without gaps or duplicates."
            )

    sample_rates = {
        int(item.audio.get("sample_rate") or 0)
        for item in ordered
        if audio_has_samples(item.audio)
    }
    if len(sample_rates) > 1:
        raise ValueError(
            "V2V/RV2V Source Overlap generated audio sample rates differ; "
            "refusing to desynchronize Best Cut audio."
        )

    boundaries: list[ResolvedSourceOverlapBoundary] = []
    previous_cut: int | None = None
    for left, right in zip(ordered, ordered[1:]):
        boundary = find_best_cut(
            left,
            right,
            nominal_boundary=int(left.nominal_end),
            minimum_cut=None if previous_cut is None else previous_cut + 1,
        )
        boundaries.append(boundary)
        previous_cut = int(boundary.resolved_cut)

    starts = [int(ordered[0].nominal_start)] + [
        int(boundary.resolved_cut) for boundary in boundaries
    ]
    ends = [int(boundary.resolved_cut) for boundary in boundaries] + [
        int(ordered[-1].nominal_end)
    ]
    contributions = [
        _slice_contribution(generation, start, end)
        for generation, start, end in zip(ordered, starts, ends)
    ]

    for left, right in zip(contributions, contributions[1:]):
        if int(left.source_end) != int(right.source_start):
            raise RuntimeError("Source Overlap assembly produced a gap or duplicate frame.")
    expected = int(ordered[-1].nominal_end) - int(ordered[0].nominal_start)
    actual = sum(item.frame_count for item in contributions)
    if actual != expected:
        raise RuntimeError(
            f"Source Overlap output duration changed ({actual} != {expected} frames)."
        )
    return SourceOverlapAssembly(contributions=contributions, boundaries=boundaries)


__all__ = [
    "BEST_CUT_SCORE_EPSILON",
    "SOURCE_OVERLAP_TASKS",
    "ResolvedSourceOverlapBoundary",
    "SourceOverlapAssembly",
    "SourceOverlapContribution",
    "SourceOverlapGeneration",
    "SourceOverlapWindow",
    "assemble_source_overlap_generations",
    "bidirectional_source_overlap_enabled",
    "find_best_cut",
    "seam_score",
    "should_apply_visual_motion_context",
]
