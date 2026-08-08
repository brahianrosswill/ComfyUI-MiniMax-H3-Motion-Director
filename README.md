# ComfyUI MiniMax H3 Motion Director

An independent, multi-segment MiniMax H3 Motion Director with real exported Motion
Context, generated-audio continuation, complete H3 reference conditioning,
frame-exact output and standard ComfyUI Advanced Sampling inputs.

This is a separate custom node. It does **not** modify AIMixer Director or
ComfyUI and uses the node ID `MiniMaxH3MotionDirector`, so the old and new
Director can be installed together.

## What it does

- Keeps the AIMixer Timeline, prompt/image/video groups, selection run, preview,
  report, source audio, mute, generated audio and VRAM cleanup workflow.
- Supports `t2v`, `i2v`, `fl2v`, `r2v`, `v2v` and `rv2v`.
- Uses the previous segment's final exported 22 frames as real H3 temporal
  conditioning instead of renaming a single last frame "motion context".
- Optionally carries the final exported generated audio onto the next segment's
  own H3 timeline.
- Preserves Picture, Video and Audio refs while Motion Context is active.
- Preserves an explicit FL2V last frame and removes a conflicting start anchor.
- Returns exactly the requested number of frames and matching audio duration.
- Restores previous exported context for selection runs using a versioned cache.
- Supports internal sampling and external standard `SAMPLER` + `SIGMAS`.

## Requirements

- A current ComfyUI with official MiniMax H3 support.
- MiniMax H3 diffusion model, video VAE, audio VAE and MiniMax CLIP.
- Python packages listed in `requirements.txt` for Director video/audio tools.
- Motion Context uses H3's native 24 fps.

## Installation

Place this repository under ComfyUI's `custom_nodes` folder:

```text
ComfyUI/
└─ custom_nodes/
   └─ ComfyUI-MiniMax-H3-Motion-Director/
```

Install the small Director media dependencies with the same Python that starts
ComfyUI, then restart ComfyUI. On a portable Windows install the command usually
looks like:

```powershell
python\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-MiniMax-H3-Motion-Director\requirements.txt
```

Search for **MiniMax H3 Motion Director**. Seeing the old **MiniMax H3
Director** too is expected.

This repository already contains its guarded, multi-reference derivative of
`ComfyUI-H3-Motion-Context`; do not install that separate plugin for the same
workflow. Both patch the same global H3 layout methods, so Motion Director's
startup self-test deliberately refuses to run if a safe patch order cannot be
proved. AIMixer Director itself is safe to keep installed.

## Recommended Motion Context settings

```text
Enable Motion Context       true
Context Frames              22
Continue Generated Audio    true
```

The audio option only runs when Timeline output audio is `generate`. It is
automatically disabled for `source` and `mute` because that generated audio
trajectory will not be exported.

When Motion Context is enabled, it replaces legacy single-last-frame segment
continuity. Both mechanisms are never applied together.

## Automatic sampling selection

There is no sampling-mode dropdown. Motion Director decides from the two
optional Advanced Sampling sockets:

| `sampler` | `sigmas` | Actual mode |
|---|---|---|
| disconnected | disconnected | internal |
| connected | connected | external |
| connected | disconnected | error |
| disconnected | connected | error |

The Advanced Sampling header shows the read-only result. In internal mode it
shows `Sampling: internal` and uses:

```text
steps          25
sampler_name   res_multistep
scheduler      simple
shift_video    12
shift_audio    3
```

The incoming MODEL keeps all patches. Motion Director applies
`ModelSamplingMiniMaxH3` internally and builds the schedule for every segment.

## External Advanced Sampling

Connect both external sockets:

```text
Load Diffusion Model
        ↓
Turbo LoRA / SageAttention / Sol-Attn / other MODEL patches
        ↓
ModelSamplingMiniMaxH3
        ├──────────────────────────→ Motion Director.model
        │
        └→ BasicScheduler ─ SIGMAS → Motion Director.sigmas

KSamplerSelect ─────────── SAMPLER → Motion Director.sampler
```

`steps` is decided by the node that creates `SIGMAS`. For example, connect an
INT value of 8 to `BasicScheduler.steps` for an 8-step schedule.

External mode uses the MODEL and SIGMAS exactly as connected. It does not apply
Director's internal video/audio shift again. The internal `steps`,
`sampler_name`, `scheduler`, `shift_video` and `shift_audio` widgets are hidden
while both sockets are connected; disconnecting both restores the saved values.
Connecting only one socket is rejected explicitly—there is no silent fallback.
Workflows saved by an older Motion Director release are migrated when loaded:
the obsolete `sampling_control` widget is removed and existing input links keep
their correct target slots.

For the optional Turbo workflow:

```text
MiniMax-H3 Turbo LoRA → ModelSamplingMiniMaxH3 → BasicScheduler(simple, 4/8)
MiniMax-H3 Turbo Sampler → Motion Director.sampler
```

The Turbo plugin is optional and is not installed by this repository.

## Example workflows

Drag a JSON file from `example_workflows` onto the ComfyUI canvas. Start with:

- `minimax_h3_motion_director_t2v.json` for the simplest internal-sampling check;
- `minimax_h3_motion_director_t2v_external.json` for a two-segment,
  22-frame video/audio Motion Context run using external `SAMPLER` + `SIGMAS`.

The external example already follows the required one-shift graph:
`UNET → MiniMaxH3SigmaShift → Director + BasicScheduler`. Replace its four
model filenames with the filenames installed on your machine before queuing.
The other JSON files cover FL2V, R2V, V2V and RV2V.

## Exact duration example

With 124 requested frames and 22 context frames, H3 must generate an aligned
158-frame internal clip. Motion Director removes the first 22 context frames,
keeps exactly 124 frames, removes the remaining grid tail and cuts AUDIO at the
same absolute frame boundaries. This prevents per-segment A/V drift.

## Selection run and cache

Motion Context cache is stored under ComfyUI output:

```text
output/minimax_motion_context_cache/<node-id>/
```

It contains CPU frames/audio from the final exported result, not GPU tensors and
not a hidden raw sampler tail. If Segment 4 is selected, Segment 3 must have a
valid cache made with the same timeline, resolution, FPS, prompts, references,
sampling settings and Motion Context settings. Otherwise execution stops with a
plain error telling you to generate the previous segment or the full sequence.

## Compatibility

| Feature | Status |
|---|---|
| Standard MODEL patches | Preserved; the connected MODEL is sampled directly |
| Standard KSamplerSelect `SAMPLER` | Supported in external mode |
| Standard scheduler `SIGMAS` | Supported in external mode |
| MiniMax H3 Turbo Sampler | Optional standard `SAMPLER`; covered by an installed-plugin probe test |
| Turbo LoRA | MODEL path preserved; requires a matching Turbo workflow/model |
| SageAttention | MODEL path preserved; real-render result depends on the installed patch |
| Sol-Attn | MODEL path preserved; real-render result depends on the installed patch |
| Spectrum | **Unsupported / experimental with Motion Context; disable it** |

No compatibility is claimed solely because a socket connects. Real-render
claims belong in release test results and require the corresponding model and
GPU environment.

## Fail-loud errors

Motion Context refuses to run when it detects any of these conditions:

- PackedLayout or H3 payload startup self-test failure;
- missing/stale/corrupt previous context cache;
- empty or incompatible H3 AV latent;
- invalid H3 temporal grid or insufficient previous frames/audio;
- more than one marked Motion Audio Context ref;
- FL2V/keyframe merge conflict;
- only one of external `SAMPLER` / `SIGMAS` is connected;
- invalid/non-monotonic SIGMAS;
- MODEL is not MiniMax H3 `ModelSamplingAV`;
- external sampler rejects H3's nested AV latent.

There is no silent fallback to a last frame.

## Tests

Run with ComfyUI on `PYTHONPATH`:

```powershell
$env:COMFYUI_ROOT = "D:\path\to\ComfyUI"
$env:PYTHONPATH = $env:COMFYUI_ROOT
python -m pytest -q
```

Tests cover PackedLayout anchors, multi-ref audio coordinates, FL2V last-anchor
merge, payload ordering, exact video/audio duration, exported endpoint chaining,
selection cache invalidation, all six task input modes, internal/external
sampling dispatch, bfloat16 cache identities, example-workflow wiring, optional
Turbo `SAMPLER` type, and real ComfyUI loading beside installed AIMixer Director.

## Source and license

The complete MiniMax H3 Motion Director derivative is distributed under
[GNU GPL version 3](LICENSE). It contains modified GPL-3.0 code from
[ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)
and modified Apache-2.0 code from
[ComfyUI_MiniMaxH3_Director](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director).
The original notices and license texts remain in [NOTICE](NOTICE) and
[LICENSES](LICENSES); the exact researched revisions are recorded in
[SOURCE_VERSIONS.md](SOURCE_VERSIONS.md).

This is an independent, substantially modified derivative. It is not an
official distribution of either upstream project.
