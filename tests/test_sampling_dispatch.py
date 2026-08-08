from __future__ import annotations

import importlib

import torch

import comfy.nested_tensor
import comfy.sample
import latent_preview
from comfy_extras.nodes_minimax_h3 import MiniMaxH3SigmaShift


def _latent():
    video = torch.zeros(1, 24, 2, 1, 1)
    audio = torch.zeros(1, 32, 2, 8)
    return {"samples": comfy.nested_tensor.NestedTensor((video, audio))}


def test_internal_applies_shift_external_never_double_shifts(plugin_package, monkeypatch):
    sampling = importlib.import_module(
        f"{plugin_package.__name__}.director.core_sampling"
    )
    calls = {"shift": 0, "internal": 0, "external": 0}

    class Model:
        pass

    model = Model()
    shifted_model = Model()

    def shift_execute(_model, _video, _audio):
        calls["shift"] += 1
        return (shifted_model,)

    monkeypatch.setattr(MiniMaxH3SigmaShift, "execute", staticmethod(shift_execute))
    monkeypatch.setattr(latent_preview, "prepare_callback", lambda *_a, **_k: None)

    def sample_internal(model_arg, noise, *args, **kwargs):
        calls["internal"] += 1
        assert model_arg is shifted_model
        return noise

    def sample_external(model_arg, noise, *args, **kwargs):
        calls["external"] += 1
        assert model_arg is model
        return noise

    monkeypatch.setattr(comfy.sample, "sample", sample_internal)
    monkeypatch.setattr(comfy.sample, "sample_custom", sample_external)
    monkeypatch.setattr(
        sampling,
        "validate_external_sampling",
        lambda _m, _s, sigmas: (sigmas.detach().float().cpu(), len(sigmas) - 1),
    )

    sampling.sample_single_stage(
        model=model,
        positive=[],
        negative=[],
        latent=_latent(),
        seed=1,
        cfg=1.0,
        steps=2,
        sampler_name="euler",
        scheduler="simple",
        sampling_control="internal",
    )
    assert calls == {"shift": 1, "internal": 1, "external": 0}

    sampling.sample_single_stage(
        model=model,
        positive=[],
        negative=[],
        latent=_latent(),
        seed=1,
        cfg=1.0,
        steps=99,
        sampler_name="ignored",
        scheduler="ignored",
        sampling_control="external",
        external_sampler=object(),
        external_sigmas=torch.tensor([1.0, 0.5, 0.0]),
    )
    assert calls == {"shift": 1, "internal": 1, "external": 1}
