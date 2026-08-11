"""Versioned exported Motion Context cache for selection runs."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

import folder_paths

from ..lib.tensor_fingerprint import tensor_fingerprint
from .audio_trim import audio_has_samples
from .segment_cache import _write_via_temp

log = logging.getLogger("ComfyUI-MiniMax-H3-Motion-Director.context_cache")

CACHE_VERSION = 1
CACHE_FORMAT = "minimax_h3_motion_director_exported_context_v1"


class MotionContextCacheError(RuntimeError):
    pass


@dataclass(frozen=True)
class CachedMotionContext:
    frames: torch.Tensor
    audio: dict[str, Any] | None
    metadata: dict[str, Any]


def _sha_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json_identity(value: Any, depth: int = 0):
    if depth > 8:
        return {"type": f"{type(value).__module__}.{type(value).__qualname__}"}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, torch.Tensor):
        return tensor_fingerprint(value)
    if isinstance(value, dict):
        return {
            str(key): _json_identity(item, depth + 1)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_identity(item, depth + 1) for item in value]
    return {"type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _audio_identity(item) -> dict[str, Any]:
    audio = getattr(item, "audio", None)
    wave = audio.get("waveform") if isinstance(audio, dict) else None
    return {
        "index": int(getattr(item, "index", -1)),
        "file": str(getattr(item, "audio_file", "") or ""),
        "sample_rate": int(audio.get("sample_rate") or 0) if isinstance(audio, dict) else 0,
        "waveform": tensor_fingerprint(wave),
    }


def _image_identity(item) -> dict[str, Any]:
    return {
        "index": int(getattr(item, "index", -1)),
        "tensor": tensor_fingerprint(getattr(item, "tensor", None)),
    }


def _video_identity(item) -> dict[str, Any]:
    return {
        "index": int(getattr(item, "index", -1)),
        "file": str(getattr(item, "video_file", "") or ""),
        "meta": _json_identity(dict(getattr(item, "meta", None) or {})),
        "tensor": tensor_fingerprint(getattr(item, "tensor", None)),
    }


def _timeline_identity(plan) -> dict[str, Any]:
    raw = getattr(plan, "raw", None) or {}
    source = raw.get("video") or {}
    clips = []
    for clip in raw.get("videoClips") or raw.get("video_clips") or []:
        clips.append(
            {
                "file": clip.get("videoFile") or clip.get("fileName") or "",
                "start": clip.get("startFrame") or clip.get("start_frame") or 0,
                "end": clip.get("endFrame") or clip.get("end_frame") or 0,
                "offset": clip.get("sourceStartFrame") or clip.get("source_start_frame") or 0,
            }
        )
    segments = []
    for s in getattr(plan, "segments", None) or []:
        timeline_index = int(getattr(s, "timeline_index", s.index))
        segments.append(
            {
                "index": timeline_index,
                "start": int(s.start_frame),
                "end": int(s.end_frame),
                "prompt": str(s.prompt),
                "negative": str(s.negative_prompt),
                "task": str(s.task_key),
                "reference_video": _json_identity(dict(s.reference_video_meta or {})),
                "reference_video_start": int(s.reference_video_start_frame),
                "source_clip": tensor_fingerprint(s.source_clip),
                "refs": [_image_identity(x) for x in s.refs or []],
                "audios": [_audio_identity(x) for x in s.ref_audios or []],
                "videos": [_video_identity(x) for x in s.ref_videos or []],
                "video_audios": [_audio_identity(x) for x in s.ref_video_audios or []],
            }
        )
    return {
        "timeline_version": raw.get("version"),
        "edit_mode": getattr(plan, "edit_mode", ""),
        "total_frames": int(getattr(plan, "total_frames", 0)),
        "fps": float(getattr(plan, "frame_rate", 0.0)),
        "width": int(getattr(plan, "width", 0)),
        "height": int(getattr(plan, "height", 0)),
        "output_mode": str(getattr(plan, "output_mode", "")),
        "source": {
            "file": source.get("videoFile") or source.get("fileName") or "",
            "subfolder": source.get("subfolder") or "",
            "type": source.get("type") or "",
            "frame_map": _json_identity(
                source.get("frameMap") or source.get("frame_map") or []
            ),
        },
        "clips": clips,
        "segments": segments,
    }


def context_fingerprint(seg, plan, settings: dict[str, Any]) -> dict[str, Any]:
    timeline = _timeline_identity(plan)
    slot = int(getattr(seg, "timeline_index", seg.index))
    segment_data = next(
        (item for item in timeline["segments"] if int(item["index"]) == slot),
        None,
    )
    if segment_data is None:
        raise MotionContextCacheError(
            "Motion Director: segment %d is missing from the current timeline identity."
            % (slot + 1)
        )
    return {
        "cache_version": CACHE_VERSION,
        "format": CACHE_FORMAT,
        "timeline_sha256": _sha_json(timeline),
        "timeline": timeline,
        "segment_index": slot,
        "segment_identity": _sha_json(segment_data),
        "settings": settings,
        "settings_sha256": _sha_json(settings),
    }


def _cache_root(node_id: str | None) -> Path:
    if not node_id:
        raise MotionContextCacheError(
            "Motion Director: the node has no unique_id, so Motion Context cache "
            "cannot be used for selection runs."
        )
    root = (
        Path(folder_paths.get_output_directory())
        / "minimax_motion_context_cache"
        / str(node_id)
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_motion_context_cache(
    node_id: str | None,
    seg,
    plan,
    *,
    frames: torch.Tensor,
    audio: dict[str, Any] | None,
    settings: dict[str, Any],
) -> bool:
    """Persist only exported CPU frames/audio. Returns False on I/O failure."""
    try:
        root = _cache_root(node_id)
        slot = int(getattr(seg, "timeline_index", seg.index))
        dest = root / ("seg_%04d.pt" % slot)
        metadata = {
            "fps": float(plan.frame_rate),
            "frame_count": int(frames.shape[0]),
            "width": int(frames.shape[2]),
            "height": int(frames.shape[1]),
            "segment_index": slot,
            "fingerprint": context_fingerprint(seg, plan, settings),
        }
        payload: dict[str, Any] = {
            "format": CACHE_FORMAT,
            "version": CACHE_VERSION,
            "metadata": metadata,
            "frames": frames.detach().cpu().float().contiguous(),
        }
        if audio_has_samples(audio):
            payload["audio_waveform"] = audio["waveform"].detach().cpu().contiguous()
            payload["audio_sample_rate"] = int(audio["sample_rate"])
        _write_via_temp(dest, lambda path: torch.save(payload, path))
        return True
    except Exception as exc:
        log.warning(
            "Motion Context cache write failed for segment %d: %s",
            int(getattr(seg, "timeline_index", seg.index)) + 1,
            exc,
        )
        return False


def _cache_error(seg_index: int, detail: str) -> MotionContextCacheError:
    return MotionContextCacheError(
        "Segment %d requires a valid generated result from Segment %d for "
        "Motion Context. Generate the previous segment first or run the complete "
        "sequence. Cache detail: %s"
        % (seg_index + 2, seg_index + 1, detail)
    )


def load_motion_context_cache(
    node_id: str | None,
    seg,
    plan,
    *,
    settings: dict[str, Any],
    strict: bool = False,
) -> CachedMotionContext | None:
    """Load a previous segment's exported endpoint and reject every stale field."""
    try:
        root = _cache_root(node_id)
        slot = int(getattr(seg, "timeline_index", seg.index))
        path = root / ("seg_%04d.pt" % slot)
        if not path.is_file():
            raise _cache_error(slot, "cache file is missing")
        payload = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(payload, dict):
            raise _cache_error(slot, "cache payload is not a dictionary")
        if payload.get("format") != CACHE_FORMAT or int(payload.get("version", -1)) != CACHE_VERSION:
            raise _cache_error(slot, "cache version/format is unsupported")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise _cache_error(slot, "metadata is missing")
        expected = context_fingerprint(seg, plan, settings)
        if metadata.get("fingerprint") != expected:
            raise _cache_error(slot, "timeline or generation settings changed")
        frames = payload.get("frames")
        if not isinstance(frames, torch.Tensor) or frames.ndim != 4 or int(frames.shape[0]) <= 0:
            raise _cache_error(slot, "exported frame tensor is corrupt")
        checks = {
            "frame_count": int(frames.shape[0]),
            "width": int(frames.shape[2]),
            "height": int(frames.shape[1]),
            "segment_index": slot,
        }
        for key, value in checks.items():
            if int(metadata.get(key, -1)) != value:
                raise _cache_error(slot, "%s does not match cached data" % key)
        if abs(float(metadata.get("fps", 0.0)) - float(plan.frame_rate)) > 1e-9:
            raise _cache_error(slot, "FPS changed")
        audio = None
        wave = payload.get("audio_waveform")
        if isinstance(wave, torch.Tensor) and wave.numel() > 0:
            sr = int(payload.get("audio_sample_rate") or 0)
            if wave.ndim != 3 or sr <= 0:
                raise _cache_error(slot, "cached audio is corrupt")
            audio = {"waveform": wave, "sample_rate": sr}
        return CachedMotionContext(frames=frames.float(), audio=audio, metadata=metadata)
    except MotionContextCacheError:
        if strict:
            raise
        return None
    except Exception as exc:
        if strict:
            slot = int(getattr(seg, "timeline_index", seg.index))
            raise _cache_error(slot, "cache read failed: %s" % exc) from exc
        log.warning("Motion Context cache read failed: %s", exc)
        return None


__all__ = [
    "CACHE_VERSION",
    "CachedMotionContext",
    "MotionContextCacheError",
    "context_fingerprint",
    "load_motion_context_cache",
    "save_motion_context_cache",
    "tensor_fingerprint",
]
