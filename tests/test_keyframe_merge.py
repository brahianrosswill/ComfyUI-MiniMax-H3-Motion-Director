from __future__ import annotations

import importlib

import torch


def test_fl2v_last_anchor_and_refs_survive_motion_merge(plugin_package):
    motion = importlib.import_module(
        f"{plugin_package.__name__}.director.motion_context"
    )
    patches = importlib.import_module(f"{plugin_package.__name__}.patches")
    first = torch.tensor([1.0])
    last = torch.tensor([2.0])
    picture = torch.tensor([3.0])
    user_audio = torch.tensor([4.0])
    conditioning = [
        [
            torch.tensor([0.0]),
            {
                "minimax_frame_count": 158,
                "minimax_keyframes": [
                    {"resolved_frame_index": 0, "latent": first},
                    {"resolved_frame_index": 157, "latent": last},
                ],
                "minimax_refs": [
                    {"kind": "image", "latent": picture},
                    {
                        "kind": "audio",
                        "ref_audio_t": 3,
                        "audio_latent": user_audio,
                    },
                ],
            },
        ]
    ]
    motion_kfs = [
        {"resolved_frame_index": 0, patches.MC_KEY: 0, "latent": torch.tensor([10.0])},
        {"resolved_frame_index": 0, patches.MC_KEY: 5, "latent": torch.tensor([11.0])},
    ]
    motion_audio = {
        "kind": "audio",
        "ref_audio_t": 8,
        "audio_latent": torch.tensor([12.0]),
        patches.MC_AUDIO_KEY: 22.0,
    }
    merged, removed, preserved = motion.merge_motion_conditioning(
        conditioning,
        motion_keyframes=motion_kfs,
        motion_audio_ref=motion_audio,
        generation_frame_count=158,
        visible_last_index=145,
    )
    meta = merged[0][1]
    assert removed == 1
    assert preserved == 1
    assert len(meta["minimax_keyframes"]) == 3
    assert meta["minimax_keyframes"][-1]["latent"] is last
    assert meta["minimax_keyframes"][-1][patches.MC_KEY] == 145
    assert len(meta["minimax_refs"]) == 3
    assert meta["minimax_refs"][0]["latent"] is picture
    assert meta["minimax_refs"][1]["audio_latent"] is user_audio
    assert meta["minimax_refs"][2][patches.MC_AUDIO_KEY] == 22.0


def test_payload_order_is_keyframes_then_existing_refs(plugin_package):
    payload_patch = importlib.import_module(
        f"{plugin_package.__name__}.patches.h3_payload"
    )
    k0, k1, picture, video, audio = [torch.tensor([x]) for x in range(5)]
    payload = {}
    payload_patch.merge_payload_latents(
        payload,
        [{"latent": k0}, {"latent": k1}],
        [
            {"kind": "image", "latent": picture},
            {"kind": "video", "latent": video},
            {"kind": "audio", "audio_latent": audio},
        ],
        frame_count=158,
    )
    assert payload["cond_video_latents"] == [k0, k1, picture, video]
    assert payload["cond_audio_latents"] == [audio]
    assert payload["frame_count"] == 158
