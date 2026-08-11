"""Persistence policy and memory-first access for full decoded segment caches."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import torch


def should_persist_segment_cache(
    plan: Any,
    *,
    source_bridge_active: bool,
) -> bool:
    """Return whether this run will need complete decoded segments later.

    Motion Context has its own small tail caches.  Full RGB segments are only
    useful for rebuilding an all-export selection run or for Source Bridge
    anchors that may be requested by a later Queue.
    """
    selection_enabled = getattr(plan, "run_select_enabled", None)
    if selection_enabled is None:
        # Compatibility for tests/third-party callers that construct a legacy
        # plan-like object without the explicit flag.
        selection_enabled = getattr(plan, "run_indices", None) is not None
    selection_all_export = bool(selection_enabled) and str(
        getattr(plan, "export_mode", "all")
    ) == "all"
    return selection_all_export or bool(source_bridge_active)


def resolve_nominal_segment_frames(
    in_memory: dict[int, torch.Tensor],
    *,
    segment_index: int,
    expected_frames: int,
    disk_loader: Callable[[], torch.Tensor | None],
) -> tuple[torch.Tensor, bool]:
    """Resolve Source Bridge anchors, always preferring this Queue's result."""
    index = int(segment_index)
    frames = in_memory.get(index)
    loaded_from_disk = False
    if frames is None:
        frames = disk_loader()
        loaded_from_disk = True
    if frames is None or int(frames.shape[0]) != int(expected_frames):
        raise ValueError(
            "Source Bridge requires both adjacent generated segments. Run the "
            "complete sequence once or generate the missing adjacent segment first."
        )
    if loaded_from_disk:
        frames = frames.detach().cpu().float()
        in_memory[index] = frames
    return frames, loaded_from_disk


def write_segment_cache_if_required(
    enabled: bool,
    writer: Callable[[], Any],
) -> bool:
    """Execute one best-effort cache writer only when the run policy needs it."""
    if not enabled:
        return False
    writer()
    return True


__all__ = [
    "resolve_nominal_segment_frames",
    "should_persist_segment_cache",
    "write_segment_cache_if_required",
]
