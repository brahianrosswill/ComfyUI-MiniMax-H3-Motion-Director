"""Color-statistics re-anchoring for exported visual Motion Context frames."""

from __future__ import annotations

from typing import Any

import torch


COLOR_REANCHOR_STRENGTH = 0.5
COLOR_REANCHOR_PIPELINE = "color_reanchor_v1"


def apply_color_reanchor(
    frames: torch.Tensor,
    anchor: torch.Tensor | None,
    *,
    strength: float = COLOR_REANCHOR_STRENGTH,
    eps: float = 1e-6,
) -> torch.Tensor:
    """Blend per-frame RGB statistics toward one stable visual anchor."""
    if anchor is None or not isinstance(anchor, torch.Tensor) or int(anchor.numel()) == 0:
        return frames
    if not isinstance(frames, torch.Tensor) or frames.ndim != 4 or int(frames.shape[0]) == 0:
        return frames
    if anchor.ndim == 3:
        anchor = anchor.unsqueeze(0)
    if anchor.ndim != 4 or int(frames.shape[-1]) < 3 or int(anchor.shape[-1]) < 3:
        raise ValueError("Color Re-anchor expects IMAGE tensors shaped [F,H,W,C] with RGB channels.")

    amount = min(1.0, max(0.0, float(strength)))
    if amount <= 0.0:
        return frames

    source_dtype = frames.dtype
    rgb = frames[..., :3].float()
    anchor_rgb = anchor[..., :3].to(device=frames.device, dtype=torch.float32)
    frame_mean = rgb.mean(dim=(1, 2), keepdim=True)
    frame_std = rgb.std(dim=(1, 2), keepdim=True, unbiased=False)
    anchor_mean = anchor_rgb.mean(dim=(0, 1, 2), keepdim=True)
    anchor_std = anchor_rgb.std(dim=(0, 1, 2), keepdim=True, unbiased=False)
    matched = ((rgb - frame_mean) / (frame_std + float(eps))) * anchor_std + anchor_mean
    blended = (rgb * (1.0 - amount) + matched * amount).clamp(0.0, 1.0)

    out = frames.clone()
    out[..., :3] = blended.to(dtype=source_dtype)
    return out


def _picture_one(segment) -> torch.Tensor | None:
    for ref in getattr(segment, "refs", None) or []:
        tensor = getattr(ref, "tensor", None)
        if int(getattr(ref, "index", -1)) == 0 and isinstance(tensor, torch.Tensor):
            if tensor.ndim == 3:
                tensor = tensor.unsqueeze(0)
            if tensor.ndim == 4 and int(tensor.shape[0]) > 0:
                return tensor[:1]
    return None


def _segment_slot(segment) -> int:
    return int(getattr(segment, "timeline_index", getattr(segment, "index", 0)))


def resolve_color_anchor(
    plan,
    segment,
    *,
    source_frames: torch.Tensor | None = None,
    source_bridge_active: bool = False,
) -> torch.Tensor | None:
    """Resolve the stable anchor from already-effective segment media."""
    if source_bridge_active:
        return None
    task_key = str(getattr(segment, "task_key", "")).lower()

    if task_key == "i2v":
        current_slot = _segment_slot(segment)
        anchor = None
        for candidate in getattr(plan, "segments", None) or []:
            if _segment_slot(candidate) > current_slot:
                continue
            if str(getattr(candidate, "task_key", "")).lower() != "i2v":
                continue
            source = getattr(candidate, "source_clip", None)
            if isinstance(source, torch.Tensor) and source.ndim == 4 and int(source.shape[0]) > 0:
                anchor = source[:1]
        return anchor

    if task_key == "r2v":
        return _picture_one(segment)

    if task_key == "rv2v":
        picture = _picture_one(segment)
        if picture is not None:
            return picture

    if task_key in {"v2v", "rv2v"}:
        if isinstance(source_frames, torch.Tensor) and source_frames.ndim == 4:
            if int(source_frames.shape[0]) > 0:
                return source_frames[:1]
    return None


def color_reanchor_cache_settings(enabled: bool) -> dict[str, Any]:
    return {
        "color_reanchor_enabled": bool(enabled),
        "color_reanchor_pipeline": COLOR_REANCHOR_PIPELINE,
    }


__all__ = [
    "COLOR_REANCHOR_PIPELINE",
    "COLOR_REANCHOR_STRENGTH",
    "apply_color_reanchor",
    "color_reanchor_cache_settings",
    "resolve_color_anchor",
]
