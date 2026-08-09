# ComfyUI MiniMax H3 Motion Director

This project combines two upstream projects:

- [AIMixer/ComfyUI_MiniMaxH3_Director](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director)
- [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)

It keeps AIMixer Director's multi-segment timeline and reference controls while
integrating a modified H3 Motion Context implementation directly into the
Director. Its purpose is to help MiniMax H3 carry motion and generated audio
from one segment into the next, so longer multi-segment videos feel connected
instead of restarting at every cut.

<img width="629" height="818" alt="螢幕擷取畫面 2026-08-09 090151" src="https://github.com/user-attachments/assets/dbd04567-de62-4aa3-8b7f-bedb0cb8357b" />
<img width="1808" height="958" alt="螢幕擷取畫面 2026-08-09 090211" src="https://github.com/user-attachments/assets/5fd86776-da77-43bf-9864-6e2ce7f74ed2" />
<img width="540" height="107" alt="螢幕擷取畫面 2026-08-09 090221" src="https://github.com/user-attachments/assets/6931c473-6920-4b29-a698-0ea65f4db266" />


This is an independent, substantially modified derivative and is not an
official distribution of either upstream project.

## Features

- T2V, I2V, FL2V, R2V, V2V and RV2V modes
- Multi-segment timeline with per-segment prompts
- Image, video and audio references
- Previous segment to next segment Motion Context continuity
- Generated-audio continuation between segments
- Recommended 22-frame Motion Context
- Full-sequence generation or selected-segment runs
- Exact requested visible video length with matching audio length
- Independent node IDs, allowing AIMixer Director to remain installed

## Current Test Status

Actually tested by the author with real local MiniMax H3 generation:

- T2V
- I2V

Implemented but not yet validated by the author with full real-generation
tests:

- FL2V
- R2V
- V2V
- RV2V

The implemented mode list and the actually tested mode list are intentionally
separate. The four modes above should not yet be read as fully validated.

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
5. Use the Motion Context settings below and queue the workflow.

The Director can generate the full timeline or only selected segments. When a
later segment is selected by itself, its preceding Motion Context must already
exist in the cache.

## Motion Context

Recommended settings:

```text
Enable Motion Context       true
Context Frames              22
Continue Generated Audio    true
```

`22` is the recommended context length. Motion Context is taken from the final
output of the previous segment. Generated Audio continuation is used only when
the timeline is generating audio; it does not run when the timeline uses source
audio or mute output.

## Important Notes

- Do **not** enable the standalone
  [ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)
  in the same ComfyUI environment. Motion Director already contains a modified
  implementation, and both plugins patch the MiniMax H3 runtime.
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
