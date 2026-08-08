"""Exported-frame MiniMax H3 Motion/Audio Context conditioning."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import torch

from ..patches import MC_AUDIO_KEY, MC_KEY, motion_context_patch_status

log = logging.getLogger("ComfyUI-MiniMax-H3-Motion-Director.motion_context")

FPS = 24.0
AUDIO_LATENT_HZ = 40.0
FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
VIDEO_CONTEXT_GRID = (39, 22, 5, 1)


@dataclass(frozen=True)
class MotionContextInfo:
    context_frames: int
    conditioning_blocks: int
    audio_steps: int
    audio_seconds: float
    removed_start_anchors: int
    preserved_last_anchors: int


def pixel_frames_for_latent_steps(latent_t: int) -> int:
    return sum(FRAME_PER_TOKEN[i % len(FRAME_PER_TOKEN)] for i in range(int(latent_t)))


def latent_step_offsets(latent_t: int) -> list[int]:
    out: list[int] = []
    cursor = 0
    for i in range(int(latent_t)):
        out.append(cursor)
        cursor += FRAME_PER_TOKEN[i % len(FRAME_PER_TOKEN)]
    return out


def select_context_span(requested: int, available: int) -> int:
    n = min(max(1, int(requested)), max(0, int(available)))
    for run in VIDEO_CONTEXT_GRID:
        if run <= n:
            return run
    raise ValueError("Motion Director: previous segment has no frames for Motion Context.")


def _resize_frames(images: torch.Tensor, width: int, height: int) -> torch.Tensor:
    import comfy.utils

    # Avoid a no-op Lanczos pass.  Besides wasting time, some backends slightly
    # change even constant edge pixels when source and target sizes are equal;
    # Motion Context should encode the exact exported endpoint in that case.
    if int(images.shape[1]) == int(height) and int(images.shape[2]) == int(width):
        return images[..., :3].contiguous()
    samples = images[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(
        samples, int(width), int(height), "lanczos", "disabled"
    )
    return samples.movedim(1, -1)


def _latent_video_stream(latent: dict[str, Any]) -> torch.Tensor:
    samples = latent.get("samples") if isinstance(latent, dict) else None
    if samples is None:
        raise ValueError("Motion Director: H3 conditioning returned no latent samples.")
    if hasattr(samples, "unbind"):
        streams = list(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        streams = list(samples)
    else:
        raise ValueError(
            "Motion Director: expected a MiniMax H3 nested video/audio latent, got %r."
            % type(samples)
        )
    if not streams:
        raise ValueError("Motion Director: H3 AV latent contains no video stream.")
    video = streams[0]
    if video.ndim == 4:
        video = video.unsqueeze(0)
    if video.ndim != 5:
        raise ValueError(
            "Motion Director: H3 video latent must be [B,C,T,H,W], got %s."
            % (tuple(video.shape),)
        )
    return video


def _encode_video_context(
    vae,
    frames: torch.Tensor,
    *,
    width: int,
    height: int,
    span: int,
) -> tuple[list[dict[str, Any]], int]:
    if int(frames.shape[0]) < span:
        raise ValueError(
            "Motion Director: previous segment has %d frames; %d context frames are required."
            % (int(frames.shape[0]), span)
        )
    tail = _resize_frames(frames[-span:], width, height)
    try:
        encoded = vae.encode(tail)
    except torch.cuda.OutOfMemoryError as exc:
        raise RuntimeError(
            "Motion Director ran out of VRAM while encoding Motion Context. "
            "Context rows increase memory use; reduce output resolution or enable "
            "clear_vram_between_segments. Context was not silently reduced."
        ) from exc
    if not isinstance(encoded, torch.Tensor) or encoded.ndim != 5:
        raise ValueError(
            "Motion Director: video VAE returned %r for Motion Context; expected "
            "[B,C,T,H,W]." % (getattr(encoded, "shape", type(encoded)),)
        )
    latent_t = int(encoded.shape[2])
    covered = pixel_frames_for_latent_steps(latent_t)
    if covered != span:
        raise RuntimeError(
            "Motion Director: %d exported frames encoded to %d H3 steps covering "
            "%d frames. The H3 VAE temporal grid changed; Motion Context is disabled."
            % (span, latent_t, covered)
        )
    keyframes = []
    for step, pixel_index in enumerate(latent_step_offsets(latent_t)):
        keyframes.append(
            {
                "resolved_frame_index": 0,
                MC_KEY: int(pixel_index),
                "latent": encoded[:, :, step : step + 1],
            }
        )
    return keyframes, latent_t


def _encode_audio_context(
    audio_vae,
    audio: dict[str, Any],
    *,
    span: int,
) -> tuple[dict[str, Any], int]:
    try:
        import torchaudio
    except ImportError as exc:  # pragma: no cover - shipped with ComfyUI
        raise RuntimeError("Motion Director: torchaudio is required for audio context.") from exc

    waveform = audio.get("waveform") if isinstance(audio, dict) else None
    if not isinstance(waveform, torch.Tensor) or waveform.numel() <= 0:
        raise ValueError(
            "Motion Director: Continue Generated Audio is enabled, but the previous "
            "segment has no exported generated audio."
        )
    sr = int(audio.get("sample_rate") or 0)
    vae_sr = int(getattr(audio_vae, "audio_sample_rate", 32000))
    if sr <= 0:
        raise ValueError("Motion Director: previous audio has an invalid sample rate.")
    if sr != vae_sr:
        waveform = torchaudio.functional.resample(waveform, sr, vae_sr)
    wanted = int(round(span / FPS * vae_sr))
    have = int(waveform.shape[-1])
    if have < wanted:
        raise ValueError(
            "Motion Director: previous exported audio is %.3fs, shorter than the "
            "%.3fs Motion Context window."
            % (have / vae_sr, span / FPS)
        )
    tail = waveform[:1, ..., have - wanted :]
    try:
        encoded = audio_vae.encode(tail.movedim(1, -1))
    except torch.cuda.OutOfMemoryError as exc:
        raise RuntimeError(
            "Motion Director ran out of VRAM while encoding Motion Audio Context. "
            "Generated audio continuation was not silently disabled."
        ) from exc
    if not isinstance(encoded, torch.Tensor) or encoded.ndim != 4:
        raise ValueError(
            "Motion Director: audio VAE returned an unexpected Motion Audio latent."
        )
    steps = int(encoded.shape[-1])
    if steps <= 0:
        raise ValueError("Motion Director: Motion Audio Context encoded to zero steps.")
    return {
        "kind": "audio",
        "ref_audio_t": steps,
        "audio_latent": encoded,
        MC_AUDIO_KEY: float(span),
    }, steps


def _merge_one_metadata(
    metadata: dict[str, Any],
    *,
    motion_keyframes: list[dict[str, Any]],
    motion_audio_ref: dict[str, Any] | None,
    generation_frame_count: int,
    visible_last_index: int,
) -> tuple[dict[str, Any], int, int]:
    out = dict(metadata)
    existing_keyframes = list(out.get("minimax_keyframes") or [])
    existing_refs = list(out.get("minimax_refs") or [])
    if any(kf.get(MC_KEY) is not None for kf in existing_keyframes):
        raise ValueError("Motion Director: conditioning already contains Motion Context keyframes.")
    if any(ref.get(MC_AUDIO_KEY) is not None for ref in existing_refs):
        raise ValueError("Motion Director: conditioning already contains Motion Audio Context.")

    kept: list[dict[str, Any]] = []
    removed_start = 0
    preserved_last = 0
    old_frame_count = int(
        out.get("minimax_frame_count") or generation_frame_count
    )
    for keyframe in existing_keyframes:
        resolved = int(keyframe.get("resolved_frame_index", 0))
        if resolved == 0:
            removed_start += 1
            continue
        merged = dict(keyframe)
        if resolved == old_frame_count - 1:
            merged[MC_KEY] = int(visible_last_index)
            preserved_last += 1
        else:
            merged[MC_KEY] = resolved
        # Stock PackedLayout accepts frame 0; the guarded layout patch applies
        # the real interior/end coordinate from MC_KEY after construction.
        merged["resolved_frame_index"] = 0
        kept.append(merged)

    out["minimax_keyframes"] = [dict(kf) for kf in motion_keyframes] + kept
    out["minimax_frame_count"] = int(generation_frame_count)
    if motion_audio_ref is not None:
        out["minimax_refs"] = existing_refs + [dict(motion_audio_ref)]
    elif existing_refs:
        out["minimax_refs"] = existing_refs
    return out, removed_start, preserved_last


def merge_motion_conditioning(
    conditioning,
    *,
    motion_keyframes: list[dict[str, Any]],
    motion_audio_ref: dict[str, Any] | None,
    generation_frame_count: int,
    visible_last_index: int,
) -> tuple[list, int, int]:
    if not isinstance(conditioning, (list, tuple)) or not conditioning:
        raise ValueError("Motion Director: positive conditioning is empty.")
    merged_conditioning = []
    removed_total = 0
    preserved_total = 0
    for entry in conditioning:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            raise ValueError("Motion Director: unsupported CONDITIONING structure.")
        metadata, removed, preserved = _merge_one_metadata(
            entry[1],
            motion_keyframes=motion_keyframes,
            motion_audio_ref=motion_audio_ref,
            generation_frame_count=generation_frame_count,
            visible_last_index=visible_last_index,
        )
        new_entry = list(entry)
        new_entry[1] = metadata
        merged_conditioning.append(new_entry)
        removed_total += removed
        preserved_total += preserved
    return merged_conditioning, removed_total, preserved_total


def apply_exported_motion_context(
    conditioning,
    *,
    video_vae,
    audio_vae,
    latent: dict[str, Any],
    context_frames: torch.Tensor,
    context_audio: dict[str, Any] | None,
    context_span: int,
    target_frame_count: int,
    generation_frame_count: int,
    audio_enabled: bool,
    fps: float,
) -> tuple[list, MotionContextInfo]:
    ready, reason = motion_context_patch_status()
    if not ready:
        raise RuntimeError(
            "Motion Director: Motion Context cannot run because the startup "
            "compatibility self-test failed: %s" % reason
        )
    if abs(float(fps) - FPS) > 1e-6:
        raise ValueError(
            "Motion Director: Motion Context requires H3's native 24 fps; got %s."
            % fps
        )

    video = _latent_video_stream(latent)
    width = int(video.shape[-1]) * 16
    height = int(video.shape[-2]) * 16
    actual_generation_frames = pixel_frames_for_latent_steps(int(video.shape[2]))
    if actual_generation_frames != int(generation_frame_count):
        raise RuntimeError(
            "Motion Director: H3 latent covers %d frames but the generation plan "
            "expects %d. Refusing misaligned Motion Context."
            % (actual_generation_frames, generation_frame_count)
        )
    visible_last = int(context_span) + int(target_frame_count) - 1
    if visible_last >= int(generation_frame_count):
        raise ValueError(
            "Motion Director: requested output end is outside the aligned H3 timeline."
        )

    motion_keyframes, block_count = _encode_video_context(
        video_vae,
        context_frames,
        width=width,
        height=height,
        span=int(context_span),
    )
    motion_audio_ref = None
    audio_steps = 0
    if audio_enabled:
        if audio_vae is None:
            raise ValueError("Motion Director: Motion Audio Context requires audio_vae.")
        motion_audio_ref, audio_steps = _encode_audio_context(
            audio_vae, context_audio, span=int(context_span)
        )

    merged, removed, preserved = merge_motion_conditioning(
        conditioning,
        motion_keyframes=motion_keyframes,
        motion_audio_ref=motion_audio_ref,
        generation_frame_count=int(generation_frame_count),
        visible_last_index=visible_last,
    )
    info = MotionContextInfo(
        context_frames=int(context_span),
        conditioning_blocks=block_count,
        audio_steps=audio_steps,
        audio_seconds=audio_steps / AUDIO_LATENT_HZ if audio_steps else 0.0,
        removed_start_anchors=removed,
        preserved_last_anchors=preserved,
    )
    return merged, info


__all__ = [
    "MotionContextInfo",
    "apply_exported_motion_context",
    "latent_step_offsets",
    "merge_motion_conditioning",
    "pixel_frames_for_latent_steps",
    "select_context_span",
]
