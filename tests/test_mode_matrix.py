from __future__ import annotations

import importlib
from types import SimpleNamespace

import torch


def _seg(task):
    return SimpleNamespace(
        index=0,
        task_key=task,
        refs=[],
        ref_videos=[],
        ref_audios=[],
        ref_video_audios=[],
        reference_video_meta={},
        frame_count=124,
    )


def test_t2v_i2v_fl2v_r2v_v2v_rv2v_input_construction(plugin_package):
    executor = importlib.import_module(
        f"{plugin_package.__name__}.director.executor_core"
    )
    frame = torch.rand(1, 16, 16, 3)
    clip = torch.rand(124, 16, 16, 3)
    plan = SimpleNamespace(total_frames=124, raw={}, width=16, height=16)

    out = executor._build_minimax_inputs(
        plan, _seg("t2v"), clip_frames=None, ctx_w=16, ctx_h=16, prev_tail=None
    )
    assert out == (None, None, None, None, None, None)

    out = executor._build_minimax_inputs(
        plan, _seg("i2v"), clip_frames=clip, ctx_w=16, ctx_h=16, prev_tail=frame
    )
    assert torch.equal(out[0], frame)

    out = executor._build_minimax_inputs(
        plan, _seg("fl2v"), clip_frames=clip, ctx_w=16, ctx_h=16, prev_tail=None
    )
    assert torch.equal(out[0], clip[:1])
    assert torch.equal(out[1], clip[-1:])

    r2v = _seg("r2v")
    r2v.refs = [SimpleNamespace(index=0, tensor=frame)]
    r2v.ref_videos = [SimpleNamespace(index=0, tensor=clip, video_file="", meta={})]
    r2v.ref_audios = [
        SimpleNamespace(
            index=0,
            audio={"waveform": torch.rand(1, 1, 100), "sample_rate": 32000},
            audio_file="",
        )
    ]
    out = executor._build_minimax_inputs(
        plan, r2v, clip_frames=None, ctx_w=16, ctx_h=16, prev_tail=None
    )
    assert out[2] and out[3] and out[4]

    out = executor._build_minimax_inputs(
        plan, _seg("v2v"), clip_frames=clip, ctx_w=16, ctx_h=16, prev_tail=None
    )
    assert out[3] and torch.equal(out[3]["ref_video_0"], clip)

    rv2v = _seg("rv2v")
    rv2v.refs = [SimpleNamespace(index=0, tensor=frame)]
    out = executor._build_minimax_inputs(
        plan, rv2v, clip_frames=clip, ctx_w=16, ctx_h=16, prev_tail=None
    )
    assert out[2] and out[3]
