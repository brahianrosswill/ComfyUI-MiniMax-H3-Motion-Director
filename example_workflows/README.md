# Example workflows

Drag a JSON file directly onto the ComfyUI canvas. Before queuing, change the UNET,
CLIP, Video VAE, and Audio VAE filenames to the files installed on your machine.
The CLIP loader type must be `minimax`.

## Recommended first checks

1. `minimax_h3_motion_director_t2v.json` — simplest internal-sampling smoke test.
2. `minimax_h3_motion_director_t2v_external.json` — two segments with 22-frame
   video/audio Motion Context and external `SAMPLER` + `SIGMAS`.

The remaining examples cover FL2V, R2V, V2V, and RV2V. Their node type has been
renamed to `MiniMaxH3MotionDirector`; they do not require the original AIMixer
Director node and can coexist with it.

## What a successful two-segment run should report

- `Motion Context: ON`
- segment 2 context source is segment 1's exported result
- `context frames: 22` (or a clearly reported downgrade for a short segment)
- external example reports `sampling source: external`
- final `frame_count` equals the requested visible timeline length; hidden context
  frames are removed after decoding

The workflow report is authoritative. A missing, stale, corrupt, wrong-FPS, or
wrong-size previous-segment cache is rejected instead of silently generating an
unrelated continuation.
