# Researched source versions

The implementation was built against the following source revisions on
2026-08-09 (Asia/Taipei):

| Source | Commit | Role |
|---|---|---|
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) installed copy | `dd79c643a95402136a75a28f6187d843bcf457ed` | User's active API/runtime |
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) remote HEAD | `00d02f2854892ee5b9808bc2f6348b972017886a` | Latest-source comparison |
| [AIMixer Director](https://github.com/AIMixer/ComfyUI_MiniMaxH3_Director) | `ab5f3b17ff343e84ff5010f998d30a2e930bd32d` | Timeline, planning, groups and executor base |
| [H3 Motion Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) | `15fc6a7bf7b78efb27f33d7eef3818e7ed0e118a` | Interior anchors and audio timeline research base |
| Installed MiniMax H3 Turbo | `55fee864dd7b2976b1c4ce3c3d5f7968f181409f` | Optional external SAMPLER compatibility probe |
| Installed Spectrum MiniMax H3 | `34ddd48814df5588ad25d4f4cfd751aa4ea6bb69` | Explicitly unsupported with Motion Context |
| Installed Sol-Attn | `0e334dc981cfe3b0ed926ee13ad43f64914b7f5b` | MODEL patch preservation review |

The installed and remote ComfyUI copies had no differences in the inspected
MiniMax H3 and Advanced Sampling files:

- `comfy_extras/nodes_minimax_h3.py`
- `comfy_extras/nodes_custom_sampler.py`
- `comfy/model_base.py`
- `comfy/model_sampling.py`
- `comfy/sample.py`
- `comfy/samplers.py`
- `comfy/ldm/minimax/model.py`
