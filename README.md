# Empirical Armory · scene generator

Puts a real product photo into a generated scene: a place, the light, hands or a masked fencer holding the gear, and the camera's angle and lens. The product is never redrawn. The model makes everything around it, and the photo's own pixels go back on top, so the gear in the picture is the gear you photographed.

It runs on your own computer, with free models, inside [ComfyUI](https://github.com/Comfy-Org/ComfyUI). The page opens in your browser at http://127.0.0.1:8188/ea/.

The results are meant for editing by hand and then for [Tuned by part](https://empiricalarmory.github.io/photo-style-generator/), which prints them in the house inks. The two tools are separate.

## Install (Windows, NVIDIA)

Needs an NVIDIA card with 24 GB (an RTX 4090 or similar), a driver from version 580, and about 130 GB of disk.

1. Put `Install.bat`, `Start.bat`, `Update.bat` and the `setup` folder (from this repository's `setup` folder) in an empty folder, for example `D:\EmpiricalArmory_SceneGenerator`.
2. Double-click `Install.bat`. It downloads and installs everything inside that folder: ComfyUI (portable, with its own Python), this generator, and the models. Nothing is installed elsewhere. If a download stops, run it again to carry on.
3. For FLUX 3 Image Klein, accept its licence on [Hugging Face](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy) and paste a Read token when Install asks. Press Enter to skip it.
4. `Start.bat` starts the generator and opens it in your browser. Leave its window open while you use it.

`Update.bat` replaces the generator with the latest version from here. Your products, references and results stay where they are, in `data`.

## The models

All free to run on your computer. Each has its own licence:

| Model | Licence | For a shop |
|---|---|---|
| [FLUX 3 Image Klein](https://huggingface.co/black-forest-labs/flux-3-image-klein) | FLUX Kommunity License | Images may be used commercially by businesses under US$5M a year in revenue. Its images may not be used to train other models. Fine-tuning needs a paid licence. |
| [Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) | Apache 2.0 | Yes |
| [HiDream-O1-Image](https://huggingface.co/HiDream-ai/HiDream-O1-Image) | MIT | Yes |

## Folder layout

```
ComfyUI_windows_portable\   ComfyUI and its Python
models\                     the model files
nodes\scene-generator\      this repository
data\                       products, references, results, settings
setup\                      installer, model list, logs
```
