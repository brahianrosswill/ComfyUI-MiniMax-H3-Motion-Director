from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
import torch


def _segment(index: int, start: int, end: int, task_key: str):
    return SimpleNamespace(
        index=index,
        ui_index=None,
        timeline_index=index,
        start_frame=start,
        end_frame=end,
        frame_count=end - start,
        prompt="edit the source motion",
        negative_prompt="",
        task_type=task_key,
        task_key=task_key,
        source_clip=None,
        refs=[],
        ref_audios=[],
        ref_videos=[],
        ref_video_audios=[],
        reference_video_meta={},
        reference_video_start_frame=0,
        material_source_index=None,
        material_inherited=False,
    )


@pytest.mark.parametrize("task_key", ["v2v", "rv2v"])
def test_executor_generates_both_overlap_sides_and_keeps_visible_total(
    monkeypatch, task_key
):
    """Runs only with real ComfyUI modules; all GPU/model work is mocked."""
    try:
        executor = importlib.import_module(
            "_minimax_h3_motion_director_testpkg.director.executor_core"
        )
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"full ComfyUI runtime is unavailable: {exc}")

    segments = [
        _segment(0, 0, 121, task_key),
        _segment(1, 121, 243, task_key),
    ]
    plan = SimpleNamespace(
        frame_rate=24.0,
        total_frames=243,
        width=32,
        height=32,
        ref_max_size=32,
        output_mode="fixed",
        source_width=32,
        source_height=32,
        global_task_type=task_key,
        global_task_key=task_key,
        global_prompt="",
        global_refs=[],
        global_ref_audios=[],
        segments=segments,
        segment_count=2,
        source_video=torch.zeros(243, 32, 32, 3),
        edit_mode="segmented",
        raw={"timelineMode": "gen_blank", "output": {"audioMode": "mute"}},
        source_total_frames=243,
        export_max_frames=0,
        export_mode="all",
        run_indices=None,
        continuity_enabled=False,
        continuity_overlap_frames=0,
        source_overlap_frames=0,
        resolved_source_overlap_ranges={},
    )
    conditioning_lengths: list[int] = []
    reference_lengths: list[int] = []

    def fake_conditioning(**kwargs):
        length = int(kwargs["length"])
        conditioning_lengths.append(length)
        reference_lengths.append(int(kwargs["ref_videos"]["ref_video_0"].shape[0]))
        return [], [], {"requested_length": length}, "mock-v2v"

    def fake_decode(samples, *_args, **_kwargs):
        count = int(samples["requested_length"])
        return torch.zeros(count, 32, 32, 3), {"waveform": torch.zeros(1, 1, 0), "sample_rate": 44100}

    monkeypatch.setattr(executor, "plan_summary", lambda _plan: "mock plan")
    monkeypatch.setattr(executor, "run_minimax_conditioning", fake_conditioning)
    monkeypatch.setattr(executor, "sample_single_stage", lambda **kwargs: kwargs["latent"])
    monkeypatch.setattr(executor, "_decode_av_latent", fake_decode)
    monkeypatch.setattr(executor, "save_segment_cache", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(executor, "save_motion_context_cache", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(executor, "save_source_overlap_cache", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(executor, "motion_context_patch_status", lambda: (True, "ok"))
    monkeypatch.setattr(
        executor,
        "apply_exported_motion_context",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("visual Motion Context must be skipped for V2V/RV2V overlap")
        ),
    )
    monkeypatch.setattr(executor, "cleanup_segment_vram", lambda **_kwargs: None)
    monkeypatch.setattr(executor, "report_director_progress", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(executor, "report_director_finish", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(executor, "report_director_segment_preview", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(executor, "tensor_frame_to_jpeg_b64", lambda _frame: "jpeg")

    model = SimpleNamespace(model=SimpleNamespace(), model_options={})
    combined, outputs, _audios, report = executor.execute_director_plan_core(
        plan,
        node_id="runtime-test",
        model=model,
        vae=object(),
        audio_vae=object(),
        clip=object(),
        motion_context_enabled=True,
        source_overlap_frames=5,
        clear_vram_between_segments=False,
    )

    # Segment 1 base=121+tail5=126 -> 141; Segment 2 base=head5+122=127 -> 141.
    assert conditioning_lengths == [141, 141]
    assert reference_lengths == [141, 141]
    assert [int(tensor.shape[0]) for tensor in outputs] == [121, 122]
    assert int(combined.shape[0]) == 243
    assert "source head overlap = 0 frames" in report
    assert "source tail overlap = 5 frames" in report
    assert "source head overlap = 5 frames" in report
    assert "nominal boundary = 121" in report
    assert "resolved cut = 121" in report
