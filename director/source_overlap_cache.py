# Portions derived from ComfyUI_MiniMaxH3_Director
# Copyright AIMixer and contributors
# Originally licensed under Apache License 2.0
# Modified for MiniMax H3 Motion Director, 2026-08-10
# This derivative project is distributed under GPL-3.0.
# See NOTICE and LICENSES/Apache-2.0-AIMixer.txt.

"""Versioned extended-generation cache for Source Overlap Best Cut selection runs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import torch

import folder_paths

from .audio_trim import audio_has_samples
from .context_cache import context_fingerprint, tensor_fingerprint
from .frame_align import H3_SOURCE_OVERLAP_PIPELINE
from .segment_cache import _write_via_temp
from .source_overlap import SourceOverlapGeneration

log = logging.getLogger("ComfyUI-MiniMax-H3-Motion-Director.source_overlap_cache")

CACHE_VERSION = 2
CACHE_FORMAT = "minimax_h3_source_overlap_extended_v2"


class SourceOverlapCacheError(RuntimeError):
    pass


def source_overlap_cache_fingerprint(seg, plan, settings: dict[str, Any]) -> dict[str, Any]:
    """Reuse the complete timeline/media/settings identity and add the v2 marker."""
    return {
        "cache_version": CACHE_VERSION,
        "format": CACHE_FORMAT,
        "source_overlap_pipeline": H3_SOURCE_OVERLAP_PIPELINE,
        "source_video": tensor_fingerprint(getattr(plan, "source_video", None)),
        "generation_identity": context_fingerprint(seg, plan, settings),
    }


def _cache_root(node_id: str | None) -> Path:
    if not node_id:
        raise SourceOverlapCacheError(
            "Motion Director: the node has no unique_id, so Source Overlap "
            "extended cache cannot be used for selection runs."
        )
    root = (
        Path(folder_paths.get_output_directory())
        / "minimax_source_overlap_cache"
        / str(node_id)
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_error(slot: int, detail: str) -> SourceOverlapCacheError:
    return SourceOverlapCacheError(
        "V2V/RV2V Best Cut requires the adjacent segment's extended Source "
        "Overlap cache. Run the full sequence once to build it. "
        f"Segment {int(slot) + 1} cache detail: {detail}"
    )


def save_source_overlap_cache(
    node_id: str | None,
    seg,
    plan,
    *,
    generation: SourceOverlapGeneration,
    settings: dict[str, Any],
) -> bool:
    try:
        root = _cache_root(node_id)
        slot = int(getattr(seg, "timeline_index", seg.index))
        dest = root / ("seg_%04d.pt" % slot)
        metadata = {
            "fps": float(generation.fps),
            "frame_count": int(generation.frames.shape[0]),
            "width": int(generation.frames.shape[2]),
            "height": int(generation.frames.shape[1]),
            "segment_index": int(generation.segment_index),
            "source_start": int(generation.source_start),
            "source_end": int(generation.source_end),
            "nominal_start": int(generation.nominal_start),
            "nominal_end": int(generation.nominal_end),
            "head_overlap": int(generation.head_overlap),
            "tail_overlap": int(generation.tail_overlap),
            "fingerprint": source_overlap_cache_fingerprint(seg, plan, settings),
        }
        payload: dict[str, Any] = {
            "format": CACHE_FORMAT,
            "version": CACHE_VERSION,
            "metadata": metadata,
            "frames": generation.frames.detach().cpu().float().contiguous(),
        }
        if audio_has_samples(generation.audio):
            payload["audio_waveform"] = (
                generation.audio["waveform"].detach().cpu().contiguous()
            )
            payload["audio_sample_rate"] = int(generation.audio["sample_rate"])
        _write_via_temp(dest, lambda path: torch.save(payload, path))
        return True
    except Exception as exc:
        log.warning(
            "Source Overlap extended cache write failed for segment %d: %s",
            int(getattr(seg, "timeline_index", seg.index)) + 1,
            exc,
        )
        return False


def load_source_overlap_cache(
    node_id: str | None,
    seg,
    plan,
    *,
    settings: dict[str, Any],
    strict: bool = False,
) -> SourceOverlapGeneration | None:
    try:
        root = _cache_root(node_id)
        slot = int(getattr(seg, "timeline_index", seg.index))
        path = root / ("seg_%04d.pt" % slot)
        if not path.is_file():
            raise _cache_error(slot, "cache file is missing")
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(payload, dict):
            raise _cache_error(slot, "cache payload is not a dictionary")
        if (
            payload.get("format") != CACHE_FORMAT
            or int(payload.get("version", -1)) != CACHE_VERSION
        ):
            raise _cache_error(slot, "cache version/format is unsupported")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise _cache_error(slot, "metadata is missing")
        expected = source_overlap_cache_fingerprint(seg, plan, settings)
        if metadata.get("fingerprint") != expected:
            raise _cache_error(slot, "timeline or generation settings changed")
        frames = payload.get("frames")
        if not isinstance(frames, torch.Tensor) or frames.ndim != 4:
            raise _cache_error(slot, "extended frame tensor is corrupt")
        checks = {
            "frame_count": int(frames.shape[0]),
            "width": int(frames.shape[2]),
            "height": int(frames.shape[1]),
            "segment_index": slot,
        }
        for key, value in checks.items():
            if int(metadata.get(key, -1)) != value:
                raise _cache_error(slot, f"{key} does not match cached data")
        if abs(float(metadata.get("fps", 0.0)) - float(plan.frame_rate)) > 1e-9:
            raise _cache_error(slot, "FPS changed")
        audio = None
        waveform = payload.get("audio_waveform")
        if isinstance(waveform, torch.Tensor) and waveform.numel() > 0:
            sample_rate = int(payload.get("audio_sample_rate") or 0)
            if waveform.ndim != 3 or sample_rate <= 0:
                raise _cache_error(slot, "cached audio is corrupt")
            audio = {"waveform": waveform, "sample_rate": sample_rate}
        try:
            return SourceOverlapGeneration(
                frames=frames.float(),
                audio=audio,
                source_start=int(metadata["source_start"]),
                source_end=int(metadata["source_end"]),
                nominal_start=int(metadata["nominal_start"]),
                nominal_end=int(metadata["nominal_end"]),
                head_overlap=int(metadata["head_overlap"]),
                tail_overlap=int(metadata["tail_overlap"]),
                fps=float(metadata["fps"]),
                segment_index=int(metadata["segment_index"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _cache_error(slot, f"extended mapping is corrupt: {exc}") from exc
    except SourceOverlapCacheError:
        if strict:
            raise
        return None
    except Exception as exc:
        if strict:
            slot = int(getattr(seg, "timeline_index", seg.index))
            raise _cache_error(slot, f"cache read failed: {exc}") from exc
        log.warning("Source Overlap extended cache read failed: %s", exc)
        return None


__all__ = [
    "CACHE_FORMAT",
    "CACHE_VERSION",
    "SourceOverlapCacheError",
    "load_source_overlap_cache",
    "save_source_overlap_cache",
    "source_overlap_cache_fingerprint",
]
