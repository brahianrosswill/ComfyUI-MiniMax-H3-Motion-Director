from __future__ import annotations

import importlib
from types import SimpleNamespace

import torch


def test_exact_124_frame_and_audio_duration(plugin_package):
    trim = importlib.import_module(f"{plugin_package.__name__}.director.audio_trim")
    fps = 24.0
    sr = 32000
    images = torch.rand(158, 8, 8, 3)
    # Slightly longer than picture, like an H3 40 Hz audio-grid decode.
    waveform = torch.rand(1, 2, round(158 / fps * sr) + 200)
    out_images, out_audio = trim.trim_segment_av(
        images,
        {"waveform": waveform, "sample_rate": sr},
        head_frames=22,
        target_frames=124,
        fps=fps,
    )
    assert int(out_images.shape[0]) == 124
    assert int(out_audio["waveform"].shape[-1]) == round(124 / fps * sr)
    assert int(out_audio["waveform"].shape[-1]) / sr == round(124 / fps * sr) / sr


def test_multisegment_audio_rounding_does_not_accumulate(plugin_package):
    audio_export = importlib.import_module(
        f"{plugin_package.__name__}.director.audio_export"
    )
    fps = 24.0
    sr = 32000
    frames_per_segment = 5
    per_segment_samples = round(frames_per_segment / fps * sr)
    plan = SimpleNamespace(
        segments=[SimpleNamespace(frame_count=frames_per_segment) for _ in range(3)]
    )
    audios = [
        {
            "waveform": torch.ones(1, 2, per_segment_samples),
            "sample_rate": sr,
        }
        for _ in range(3)
    ]
    merged = audio_export._merge_generated_segment_audios(
        plan,
        audios,
        total_frames=frames_per_segment * 3,
        fps=fps,
    )
    assert int(merged["waveform"].shape[-1]) == round(15 / fps * sr)
