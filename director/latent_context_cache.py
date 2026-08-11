"""Versioned AV-latent Motion Context handoff cache."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

import folder_paths

from .context_cache import context_fingerprint
from .segment_cache import _write_via_temp

log = logging.getLogger("ComfyUI-MiniMax-H3-Motion-Director.latent_context_cache")

LATENT_CACHE_VERSION = 1
LATENT_CACHE_FORMAT = "minimax_h3_motion_director_av_latent_handoff_v1"
LATENT_HANDOFF_PIPELINE = "motion_context_latent_handoff_v1"


@dataclass(frozen=True)
class CachedLatentContext:
    latent: dict[str, Any]
    handoff: dict[str, Any]
    metadata: dict[str, Any]


def _cache_root(node_id: str | None) -> Path | None:
    if not node_id:
        return None
    try:
        root = (
            Path(folder_paths.get_output_directory())
            / "minimax_motion_context_cache"
            / str(node_id)
        )
        root.mkdir(parents=True, exist_ok=True)
        return root
    except OSError as exc:
        log.warning("AV latent cache directory unavailable: %s", exc)
        return None


def av_latent_to_cpu(latent: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError("Motion Director: sampled AV latent is missing 'samples'.")
    samples = latent["samples"]
    if hasattr(samples, "unbind"):
        parts = tuple(part.detach().cpu().contiguous() for part in samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = tuple(
            part.detach().cpu().contiguous() if isinstance(part, torch.Tensor) else part
            for part in samples
        )
    elif isinstance(samples, torch.Tensor):
        parts = samples.detach().cpu().contiguous()
    else:
        raise ValueError("Motion Director: unsupported AV latent samples container.")
    out: dict[str, Any] = {"samples": parts}
    for key, value in latent.items():
        if key == "samples":
            continue
        out[key] = value.detach().cpu().contiguous() if isinstance(value, torch.Tensor) else value
    return out


def _settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {**dict(settings or {}), "latent_handoff_pipeline": LATENT_HANDOFF_PIPELINE}


def save_latent_context_cache(
    node_id: str | None,
    seg,
    plan,
    *,
    latent: dict[str, Any],
    handoff: dict[str, Any],
    settings: dict[str, Any],
) -> bool:
    root = _cache_root(node_id)
    if root is None:
        return False
    try:
        slot = int(getattr(seg, "timeline_index", seg.index))
        required = {"context_end_frame", "trim_frames", "export_frames", "sample_frames"}
        if not required.issubset(handoff):
            raise ValueError("AV latent handoff metadata is incomplete.")
        metadata = {
            "pipeline": LATENT_HANDOFF_PIPELINE,
            "segment_index": slot,
            "fps": float(plan.frame_rate),
            "fingerprint": context_fingerprint(seg, plan, _settings(settings)),
        }
        payload = {
            "format": LATENT_CACHE_FORMAT,
            "version": LATENT_CACHE_VERSION,
            "metadata": metadata,
            "handoff": {key: int(handoff[key]) for key in required},
            "latent": av_latent_to_cpu(latent),
        }
        destination = root / ("seg_%04d.av.pt" % slot)
        _write_via_temp(destination, lambda path: torch.save(payload, path))
        return True
    except Exception as exc:
        log.warning(
            "Motion Context AV latent cache write failed for segment %d: %s",
            int(getattr(seg, "timeline_index", seg.index)) + 1,
            exc,
        )
        return False


def load_latent_context_cache(
    node_id: str | None,
    seg,
    plan,
    *,
    settings: dict[str, Any],
) -> CachedLatentContext | None:
    root = _cache_root(node_id)
    if root is None:
        return None
    try:
        slot = int(getattr(seg, "timeline_index", seg.index))
        path = root / ("seg_%04d.av.pt" % slot)
        if not path.is_file():
            return None
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(payload, dict):
            return None
        if payload.get("format") != LATENT_CACHE_FORMAT:
            return None
        if int(payload.get("version", -1)) != LATENT_CACHE_VERSION:
            return None
        metadata = payload.get("metadata")
        handoff = payload.get("handoff")
        latent = payload.get("latent")
        if not isinstance(metadata, dict) or not isinstance(handoff, dict):
            return None
        if metadata.get("pipeline") != LATENT_HANDOFF_PIPELINE:
            return None
        if metadata.get("fingerprint") != context_fingerprint(seg, plan, _settings(settings)):
            return None
        if int(metadata.get("segment_index", -1)) != slot:
            return None
        if abs(float(metadata.get("fps", 0.0)) - float(plan.frame_rate)) > 1e-9:
            return None
        if not isinstance(latent, dict) or "samples" not in latent:
            return None
        required = {"context_end_frame", "trim_frames", "export_frames", "sample_frames"}
        if not required.issubset(handoff):
            return None
        return CachedLatentContext(latent=latent, handoff=handoff, metadata=metadata)
    except Exception as exc:
        log.warning("Motion Context AV latent cache read failed: %s", exc)
        return None


__all__ = [
    "CachedLatentContext",
    "LATENT_CACHE_FORMAT",
    "LATENT_CACHE_VERSION",
    "LATENT_HANDOFF_PIPELINE",
    "av_latent_to_cpu",
    "load_latent_context_cache",
    "save_latent_context_cache",
]
