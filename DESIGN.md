# MiniMax H3 Motion Director design

## Product boundary

This repository is an independent GPL-3.0 custom node. It does not import or
modify the user's installed AIMixer Director. Its Python node IDs, group socket
type, browser extension name, HTTP routes and progress events use a separate
namespace, so both plugins may load at once.

## Per-segment data flow

1. Director creates the segment's official H3 conditioning and nested AV
   latent through ComfyUI's `MiniMaxH3ImageToVideo` or
   `MiniMaxH3ReferenceToVideo`.
2. Segment 1 samples normally.
3. For Segment N > 1, Motion Director loads Segment N-1's final exported CPU
   IMAGE/AUDIO result from memory or the versioned disk cache.
4. The last H3-valid context run (normally 22 frames) is VAE-encoded as one
   video. Its latent steps become consecutive never-denoised keyframe rows.
5. Existing start anchors are removed. Motion Context owns the opening; an
   explicit FL2V last anchor is retained and moved to the final frame that will
   actually be exported, not a hidden grid-alignment tail.
6. Existing Picture/Video/Audio refs remain in original order. The encoded
   Motion Audio Context is appended as one specially marked audio ref.
7. Sampling runs using either the internal or external official ComfyUI path.
8. The decoded Motion Context head is removed from IMAGE and AUDIO. Both are
   cropped to the requested duration from absolute frame boundaries.
9. Only that final exported result becomes Segment N+1 context.

## PackedLayout patch

The patch delegates complete layout construction to ComfyUI. It changes only
time coordinates after construction:

- a marked keyframe at pixel frame `p` is placed at
  `text_len + final_ref_cursor + FRAME_RESCALE * p`;
- the marked Motion Audio ref's original cursor is found by replaying the exact
  official cursor arithmetic for every preceding ref;
- only rows in that marked audio block are translated;
- its target origin uses the final cursor after all refs, including refs that
  follow it;
- every other coordinate column and every other ref row remains unchanged.

The startup self-test covers stock first/last anchors, interior anchors,
reference cursor compensation and multi-ref audio movement. If an upstream
layout change breaks an assumption, Motion Context refuses to execute.

## Payload patch

ComfyUI currently lets the refs branch replace `cond_video_latents` previously
created by the keyframe branch. The guarded wrapper restores PackedLayout row
order exactly:

```text
Motion/FL2V keyframe video latents
→ existing Picture/Video reference latents
→ existing and Motion audio reference latents
```

The patch checks the installed `MiniMaxH3.extra_conds` contract at startup.

## Exact timeline

For requested output `R` and Motion Context span `C`:

```text
internal request = align_to_H3_grid(R + C)
decode
drop first C frames and matching audio samples
keep exactly R frames and round(R / fps * sample_rate) audio samples
drop any grid-alignment tail
```

For example, 124 requested frames plus a 22-frame context needs an aligned
158-frame H3 generation. The exported result is still exactly 124 frames.

## Selection-run cache

Each cached entry contains final CPU frames, final generated audio, FPS,
dimensions, frame count, segment index, a timeline fingerprint and a sampling /
Motion Context settings fingerprint. Missing, stale, corrupt or mismatched
entries are rejected. Motion Context never silently falls back to one frame.

## Sampling modes

Internal mode clones the incoming patched MODEL with ComfyUI's
`MiniMaxH3SigmaShift`, then uses the Director's steps, sampler name and
scheduler name.

External mode validates that the incoming MODEL is MiniMax H3 with
`ModelSamplingAV`, validates standard `SAMPLER` and `SIGMAS`, and passes them to
ComfyUI's official `sample_custom` path. It never applies another sigma shift.
