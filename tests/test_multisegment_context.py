from __future__ import annotations

import importlib

import torch

import comfy.nested_tensor


class RecordingVideoVAE:
    def __init__(self):
        self.inputs = []

    def encode(self, images):
        self.inputs.append(images.detach().clone())
        # 22 H3 pixel frames encode to 7 latent steps.
        return torch.zeros(1, 24, 7, images.shape[1] // 16, images.shape[2] // 16)


def _target_latent():
    # 47 video steps cover 158 frames; 264 audio steps cover the aligned AV span.
    video = torch.zeros(1, 24, 47, 1, 1)
    audio = torch.zeros(1, 32, 2, 264)
    return {"samples": comfy.nested_tensor.NestedTensor((video, audio))}


def test_each_segment_uses_previous_exported_endpoint(plugin_package):
    motion = importlib.import_module(
        f"{plugin_package.__name__}.director.motion_context"
    )
    vae = RecordingVideoVAE()
    conditioning = [[torch.tensor([0.0]), {}]]

    # ComfyUI IMAGE tensors are normalized to [0, 1].  Use distinct valid
    # values so the VAE input identifies the exact exported tail.
    exported_1 = torch.linspace(0.0, 0.49, 124).view(124, 1, 1, 1).expand(124, 16, 16, 3)
    motion.apply_exported_motion_context(
        conditioning,
        video_vae=vae,
        audio_vae=None,
        latent=_target_latent(),
        context_frames=exported_1,
        context_audio=None,
        context_span=22,
        target_frame_count=124,
        generation_frame_count=158,
        audio_enabled=False,
        fps=24.0,
    )
    assert torch.equal(vae.inputs[-1][:, 0, 0, 0], exported_1[-22:, 0, 0, 0])

    # Segment 3 must use Segment 2's final exported frames, never any hidden
    # over-generated tail from Segment 1's raw sampler latent.
    exported_2 = torch.linspace(0.5, 0.99, 124).view(124, 1, 1, 1).expand(124, 16, 16, 3)
    motion.apply_exported_motion_context(
        conditioning,
        video_vae=vae,
        audio_vae=None,
        latent=_target_latent(),
        context_frames=exported_2,
        context_audio=None,
        context_span=22,
        target_frame_count=124,
        generation_frame_count=158,
        audio_enabled=False,
        fps=24.0,
    )
    assert torch.equal(vae.inputs[-1][:, 0, 0, 0], exported_2[-22:, 0, 0, 0])
