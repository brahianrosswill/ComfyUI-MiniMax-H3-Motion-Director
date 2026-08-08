from __future__ import annotations

import importlib
import importlib.util

import pytest
import torch

import comfy.model_base
import comfy.model_sampling


def test_standard_external_sampler_and_sigmas_validation(plugin_package, monkeypatch):
    sampling = importlib.import_module(
        f"{plugin_package.__name__}.director.core_sampling"
    )

    class DummyMiniMaxH3:
        pass

    monkeypatch.setattr(comfy.model_base, "MiniMaxH3", DummyMiniMaxH3)
    model_sampling = comfy.model_sampling.ModelSamplingAV()
    model_sampling.set_parameters(shift=12.0, audio_shift=3.0)

    class Model:
        model = DummyMiniMaxH3()

        def get_model_object(self, name):
            assert name == "model_sampling"
            return model_sampling

    sigmas = torch.tensor([1.0, 0.5, 0.0])
    checked, steps = sampling.validate_external_sampling(Model(), object(), sigmas)
    assert steps == 2
    assert torch.equal(checked, sigmas)

    with pytest.raises(ValueError, match="SAMPLER connection"):
        sampling.validate_external_sampling(Model(), None, sigmas)
    with pytest.raises(ValueError, match="at least two values"):
        sampling.validate_external_sampling(Model(), object(), torch.tensor([1.0]))


def test_installed_turbo_declares_standard_sampler_type(comfyui_root):
    path = comfyui_root / "custom_nodes" / "ComfyUI-MiniMax-H3-Turbo" / "__init__.py"
    if not path.is_file():
        pytest.skip("ComfyUI-MiniMax-H3-Turbo is not installed")
    spec = importlib.util.spec_from_file_location("motion_director_turbo_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = module.NODE_CLASS_MAPPINGS["MiniMaxH3TurboSampler"]
    assert cls.RETURN_TYPES == ("SAMPLER",)
