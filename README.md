# ComfyUI MiniMax H3 Motion Director

This project combines two upstream projects:

- [AIMixer/ComfyUI_MiniMaxH3_Director](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director)
- [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)

It keeps AIMixer Director's multi-segment timeline and reference controls while
integrating a modified H3 Motion Context implementation directly into the
Director. Its purpose is to help MiniMax H3 carry motion and generated audio
from one segment into the next, so longer multi-segment videos feel connected
instead of restarting at every cut.

This is an independent, substantially modified derivative and is not an
official distribution of either upstream project.

## Features

- T2V, I2V, FL2V, R2V, V2V and RV2V modes
- Multi-segment timeline with per-segment prompts
- Image, video and audio references
- Task-aware continuity: Motion Context for generated-continuation tasks and
  Source Bridge for source-video editing tasks
- H3-native five-frame Source Bridge for V2V/RV2V segment boundaries
- Native H3 reference + keyframe-anchor coexistence
- Original V2V/RV2V frames are conditioning only; final Bridge pixels are regenerated
- Motion Context generated-audio continuation between segments
- 22-frame Motion Context baseline for generated-continuation tasks
- Full-sequence generation or selected-segment runs
- Exact requested visible video length with matching audio length
- Independent node IDs, allowing AIMixer Director to remain installed

## Current Test Status

Actually tested by the author with real local MiniMax H3 generation:

- T2V
- I2V
- RV2V basic generation and continuity A/B comparisons

Implemented but not yet validated by the author with full real-generation
tests:

- FL2V
- R2V
- V2V

Source Bridge v1 has automated unit and ComfyUI runtime tests, but has **not**
yet received real GPU seam-quality validation. Its status is experimental. The
implemented mode list and the actually tested mode list are intentionally
separate; automated tests prove code behavior, not visual seam quality.

Current local RV2V continuity observations from the pre-Bridge A/B tests:

- Motion Context OFF preserves source motion most strongly, but leaves a hard seam.
- Motion Context 1 is the best current overall A/B baseline: a smoother seam,
  with some source-motion fidelity loss.
- Motion Context 5 produced a more visible motion-timing shift.
- Motion Context 22 produced the most stable seam in that clip, but interfered
  clearly with the current `<Video 1>` motion and is not the RV2V default.
- The removed RGB Best Cut prototype improved fidelity in places, but still showed
  visible seams and motion repetition.
- Source Bridge is the new experimental direction and still needs real GPU validation.

## Demo Results

Below are three real A/B generation comparisons produced locally with this
node. The letters only identify the two videos in each pair; they do **not**
identify which Motion Context setting was enabled.

Use the pairs to observe cross-segment motion, subject/scene and camera
continuity, and the practical difference produced by the compared settings.

| Test | A | B |
|---|---|---|
| T2V test 1 | [View video A](demo/t2v_test_1_a.mp4) | [View video B](demo/t2v_test_1_b.mp4) |
| T2V test 2 | [View video A](demo/t2v_test_2_a.mp4) | [View video B](demo/t2v_test_2_b.mp4) |
| I2V test 1 | [View video A](demo/i2v_test_1_a.mp4) | [View video B](demo/i2v_test_1_b.mp4) |

Actual local test conditions:

- 8 sampling steps
- No Turbo LoRA
- 24 fps
- Real MiniMax H3 generation
- A/B comparison

> **Demo quality note:** These examples were not generated with best-quality
> settings. They use only 8 sampling steps because full-step A/B testing is
> prohibitively slow on the available hardware. Visible blur, smearing,
> ghosting, motion trails and unstable fine details are expected under these
> test settings. They should not be interpreted as the maximum quality of
> Motion Director or MiniMax H3.

The current local test setup could not use the MiniMax-H3 Turbo LoRA because of
a known Turbo/pruned-model conditioning issue. When Motion or Audio Context
adds conditioning, the current setup can trigger this error:

```text
The size of tensor a (3) must match the size of tensor b (2)
at non-singleton dimension 0
```

The published demos therefore use 8 steps without Turbo LoRA. This describes
the current test environment and known Turbo issue; it does not mean Motion
Director can never work with a future compatible Turbo setup.

## Requirements

- A current ComfyUI version with official MiniMax H3 support
- A MiniMax H3 diffusion model
- MiniMax H3 video VAE and audio VAE
- MiniMax-compatible CLIP/text encoder
- The media packages listed in `requirements.txt`

## Installation

Clone or place this repository inside ComfyUI's `custom_nodes` folder:

```text
ComfyUI/
└─ custom_nodes/
   └─ ComfyUI-MiniMax-H3-Motion-Director/
```

Install the dependencies using the same Python environment that starts
ComfyUI, then restart ComfyUI:

```bash
python -m pip install -r ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-Motion-Director/requirements.txt
```

For a standard portable Windows installation:

```powershell
python\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-MiniMax-H3-Motion-Director\requirements.txt
```

After restarting, search for **MiniMax H3 Motion Director** in the node menu.

## Usage

1. Load and connect the MiniMax H3 model, video VAE, audio VAE and CLIP.
2. Add **MiniMax H3 Motion Director** and choose the required task mode.
3. Enter the prompt and build one or more segments in the Director timeline.
4. Add the images, videos or audio required by the selected task mode.
5. Choose the task-aware continuity setting below and queue the workflow.

The Director can generate the full timeline or only selected segments. When a
later segment is selected by itself, the continuity data it needs must already
exist in cache. Motion Context needs the preceding exported context cache;
Source Bridge needs both adjacent nominal generated-segment caches.

## Task-Aware Continuity

| Task | Recommended continuity | Starting setting | Reason |
|---|---|---|---|
| T2V | Motion Context | 22 frames baseline | The next segment has no complete source-video motion, so it needs the previous generated state. |
| I2V | Motion Context | 22 frames baseline | Continue generated state after the first image; an explicit new image resets it. |
| FL2V | Motion Context / explicit anchors | 22-frame chaining baseline | Use when generated motion should continue across anchored segments. |
| R2V | Motion Context | 22 frames baseline | References control identity/material while MC supplies cross-segment temporal state. |
| V2V | Source Bridge | Bridge ON (fixed 5-frame H3 bridge) | The current `<Video 1>` should have the highest motion authority. Visual Motion Context is automatically disabled while Bridge is on. |
| RV2V | Source Bridge | Bridge ON (fixed 5-frame H3 bridge) | `<Video 1>` controls motion while Picture refs control subject/appearance. Visual Motion Context is automatically disabled while Bridge is on. |

Use Motion Context when the next segment should continue the **previously
generated result**. Use Source Bridge when V2V/RV2V should remain driven by the
**current original source video**. `22` is a generated-continuation baseline;
it is not a global recommendation for V2V/RV2V.

The outer node groups these settings under **Cross-Segment Continuity** and
shows a read-only `Active` line. That line updates immediately when the task,
segment count, language or continuity toggles change. The controls follow
these task-aware UI rules:

- With one segment, Motion Context, Context Frames, Continue Generated Audio
  and Source Bridge are disabled because there is no cross-segment boundary.
  Their stored values are preserved for later multi-segment use.
- With multiple T2V/I2V/FL2V/R2V segments, Motion Context is available and
  Source Bridge is disabled because those tasks do not use an original-video
  boundary Bridge.
- With multiple V2V/RV2V segments and Source Bridge ON, the fixed five-frame
  Bridge controls visual continuity. Motion Context and its dependent controls
  are shown disabled without clearing the saved Motion Context toggle.
- With Source Bridge OFF, V2V/RV2V may use Motion Context as an experimental
  fallback.
- Context Frames and Continue Generated Audio are enabled only while Motion
  Context is active. Continue Generated Audio is additionally available only
  when the output audio mode is **Generate audio**.

## Motion Context

Generated-continuation baseline for T2V/I2V/FL2V/R2V:

```text
Motion Context              true
Context Frames              22
Continue Generated Audio    true
```

`22` is the baseline context length for these tasks. Motion Context is taken from the final
output of the previous segment. Generated Audio continuation is used only when
the timeline is generating audio; it does not run when the timeline uses source
audio or mute output.

For I2V with Motion Context enabled, Segment 1 needs an initial image; later
segments may leave the image slot empty to continue from the preceding Motion
Context. Adding an image to a later segment starts a new I2V anchor and skips
the incoming motion/audio context for that segment. For R2V, Segment 1 needs a
reference bundle; later empty groups inherit the most recent complete explicit
bundle (images, videos and audio) without merging slots. The same rules apply
to connected external I2V/R2V groups. With Motion Context disabled, every
segment keeps the original independent-media validation and behavior. Export
mode changes only output packaging and does not affect these inheritance rules.

## Source Bridge (V2V/RV2V)

Recommended starting point:

```text
Source Bridge               ON
H3 Bridge                   fixed 5 frames
```

The backend field remains `source_overlap_frames` so existing workflows keep
loading. The UI presents it as an OFF/ON toggle while the serialized backend
value remains the original integer: `0` for OFF and `5` for ON. Any legacy
non-zero value loads as ON and is normalized to `5` on the next save.

For a boundary at source frame `B`, the Director keeps both normal segment
generations at their nominal lengths. It then performs one extra five-frame H3
generation:

```text
Original source conditioning: B-2, B-1, B, B+1, B+2
Generated first anchor:       left segment at B-2
Generated last anchor:        right segment at B+2
Final replacement frames:     regenerated B-1, B, B+1
```

The five original frames enter `<Video 1>` only as conditioning. Original
source pixels are never copied into final output. The normal left/right audio
cut remains unchanged in Source Bridge v1; there is no Bridge audio or
crossfade. Total video frame count, FPS and timeline duration remain unchanged.
Source Bridge v1 improves visual continuity only. **Continue Generated Audio
belongs to the Motion Context path. Source Bridge does not currently carry
Motion Context generated-audio continuation.**

If the five source frames cross a physical file boundary, an edited timeline
jump, BOF/EOF, or an RV2V Picture/Audio reference-set change, that boundary is
reported and keeps its nominal hard cut. Source frames are never padded for a
Bridge. A selected-segment run also refuses to fabricate a Bridge when an
adjacent generated cache is missing; generate the complete sequence once or
generate the missing adjacent segment first.

Even if the Motion Context toggle remains enabled, V2V/RV2V with Source Bridge
ON skips visual Motion Context. The UI disables the Motion Context controls in
that state but preserves their saved values. Turning Source Bridge OFF restores
the existing experimental Motion Context fallback.

## Important Notes

- Do **not** enable the standalone
  [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)
  in the same ComfyUI environment. Motion Director already contains a modified
  implementation, and both plugins patch the MiniMax H3 runtime.
- There is no runtime dependency on the standalone Niko repository. Installing
  both at the same time is not recommended.
- [AIMixer/ComfyUI_MiniMaxH3_Director](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director)
  may remain installed. Its node IDs are separate and the two Directors can
  coexist.
- Motion Context uses MiniMax H3's native 24 fps timeline.
- A selected later segment needs a valid cached context from its preceding
  segment. If the cache is missing or no longer valid, generate the previous
  segment or the complete sequence first.
- Audio Context continues generated audio only. It does not continue source or
  muted audio.

## License

MiniMax H3 Motion Director is distributed as a complete derivative work under
the [GNU General Public License version 3](LICENSE).

It includes modified Apache-2.0 code from AIMixer's
`ComfyUI_MiniMaxH3_Director` and modified GPL-3.0 code from NikoDemon80's
`ComfyUI-H3-Motion-Context`. Original attribution and license texts are retained
in [NOTICE](NOTICE) and [LICENSES](LICENSES).
