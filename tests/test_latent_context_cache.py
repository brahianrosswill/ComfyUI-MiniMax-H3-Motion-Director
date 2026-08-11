from __future__ import annotations

from types import SimpleNamespace

import torch

from _minimax_h3_motion_director_testpkg.director import latent_context_cache


def _objects():
    seg = SimpleNamespace(index=0, timeline_index=0)
    plan = SimpleNamespace(frame_rate=24.0)
    latent = {
        "samples": (
            torch.zeros((1, 2, 7, 2, 2)),
            torch.zeros((1, 2, 2, 37)),
        )
    }
    handoff = {
        "context_end_frame": 22,
        "trim_frames": 0,
        "export_frames": 22,
        "sample_frames": 39,
    }
    return seg, plan, latent, handoff


def test_versioned_av_latent_cache_roundtrip(monkeypatch, tmp_path):
    seg, plan, latent, handoff = _objects()
    monkeypatch.setattr(latent_context_cache, "_cache_root", lambda _node: tmp_path)
    monkeypatch.setattr(latent_context_cache, "context_fingerprint", lambda *_a, **_k: {"fp": 1})

    assert latent_context_cache.save_latent_context_cache(
        "node", seg, plan, latent=latent, handoff=handoff, settings={"seed": 1}
    )
    loaded = latent_context_cache.load_latent_context_cache(
        "node", seg, plan, settings={"seed": 1}
    )
    assert loaded is not None
    assert loaded.handoff["context_end_frame"] == 22
    assert loaded.handoff["sample_frames"] == 39
    assert torch.equal(loaded.latent["samples"][0], latent["samples"][0])
    assert loaded.metadata["pipeline"] == latent_context_cache.LATENT_HANDOFF_PIPELINE


def test_old_or_stale_latent_cache_is_not_mistaken_for_current_handoff(monkeypatch, tmp_path):
    seg, plan, _latent, _handoff = _objects()
    monkeypatch.setattr(latent_context_cache, "_cache_root", lambda _node: tmp_path)
    monkeypatch.setattr(latent_context_cache, "context_fingerprint", lambda *_a, **_k: {"fp": 2})
    torch.save(
        {
            "format": "old_pixel_only_cache",
            "version": 0,
            "latent": {"samples": (torch.zeros(1),)},
        },
        tmp_path / "seg_0000.av.pt",
    )
    assert latent_context_cache.load_latent_context_cache(
        "node", seg, plan, settings={"seed": 1}
    ) is None
