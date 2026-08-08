from __future__ import annotations

import importlib
import importlib.util
import inspect

import pytest
import torch

import comfy.model_base
import comfy.model_sampling


def test_director_schema_has_no_manual_sampling_control(plugin_package):
    director_module = importlib.import_module(
        f"{plugin_package.__name__}.nodes.director"
    )
    director = director_module.MiniMaxH3MotionDirector
    schema = director.INPUT_TYPES()
    input_names = {
        name
        for section in ("required", "optional", "hidden")
        for name in schema.get(section, {})
    }
    assert "sampling_control" not in input_names
    assert {"sampler", "sigmas"}.issubset(input_names)
    assert "sampling_control" not in inspect.signature(director.execute).parameters


@pytest.mark.parametrize(
    ("sampler", "sigmas", "expected"),
    [
        (None, None, "internal"),
        (object(), torch.tensor([1.0, 0.0]), "external"),
    ],
)
def test_sampling_mode_is_derived_from_connections(
    plugin_package, sampler, sigmas, expected
):
    sampling = importlib.import_module(
        f"{plugin_package.__name__}.director.core_sampling"
    )
    assert sampling.resolve_sampling_mode(sampler, sigmas) == expected


@pytest.mark.parametrize(
    ("sampler", "sigmas", "connected", "missing"),
    [
        (object(), None, "SAMPLER", "SIGMAS"),
        (None, torch.tensor([1.0, 0.0]), "SIGMAS", "SAMPLER"),
    ],
)
def test_partial_external_sampling_connections_fail_loudly(
    plugin_package, sampler, sigmas, connected, missing
):
    sampling = importlib.import_module(
        f"{plugin_package.__name__}.director.core_sampling"
    )
    with pytest.raises(ValueError) as caught:
        sampling.resolve_sampling_mode(sampler, sigmas)
    message = str(caught.value)
    assert connected in message
    assert missing in message
    assert "Connect both" in message
    assert "disconnect both" in message


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
