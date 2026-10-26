# Empirical Armory · scene generator

Puts a real product photo into a generated scene: a place, the light, hands or a masked fencer holding the gear, and the camera's angle and lens. For gear that is held or set down, the product is never redrawn: the model makes everything around it, and the photo's own pixels go back on top, so the gear in the picture is the gear you photographed. Gear that is worn (gloves on hands, a mask on a head) has to change shape, so the model draws it from your photo instead, and the page says so.

It runs on your own computer, with free models, inside [ComfyUI](https://github.com/Comfy-Org/ComfyUI). The page opens in your browser at http://127.0.0.1:8188/ea/.

The results are meant for editing by hand and then for [Tuned by part](https://empiricalarmory.github.io/photo-style-generator/), which prints them in the house inks. Each picture comes with a parts map (`<name>-parts.png`, the product in Product red) that Tuned by part pairs with it. The two tools are separate.

## Install (Windows, NVIDIA)

Needs an NVIDIA card with 24 GB (an RTX 4090 or similar), a driver from version 580, 64 GB of memory, and about 140 GB of disk.

1. Put `Install.bat`, `Start.bat`, `Update.bat` and the `setup` folder (all from this repository's `setup` folder) in an empty folder, for example `D:\EmpiricalArmory_SceneGenerator`.
2. Double-click `Install.bat`. It downloads and installs everything inside that folder: ComfyUI (portable, with its own Python), this generator, and the models. Nothing is installed anywhere else. If a download stops, run it again to carry on; every file is checked against its checksum.
3. For FLUX 3 Image Klein, accept its licence on [Hugging Face](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy) and paste a Read token when Install asks. Press Enter to skip it.
4. `Start.bat` starts the generator and opens it in your browser. Leave its window open while you use it.

`Update.bat` replaces the generator with the latest version from here. Your products, references and results stay where they are, in `data`.

## Using it

- **Make.** Add a product photo, on a plain backdrop if you can. It is cut out automatically (BiRefNet), and "Check the cut-out" lets you fix the edges with a brush or lasso. For swords and trainers the handle is marked as the part hands may cover; change it with "Where hands may go". Pick a starting scene, then the place, light, people, pose and camera; drag, scroll and shift-drag the product in the frame. Choose a model and Generate.
- **Results.** Every picture, with the model's own picture before the product went back on, the parts map, and how it was made. "Use these settings" brings a picture's settings, seed included, back to Make.
- **Compare models.** The same product, scenes and seeds through each model, side by side.
- **References.** Photographs whose look your scenes should follow. Find openly licensed ones (Openverse: CC0, public domain, CC BY, CC BY-SA), or add your own, and record each one's creator, licence and right to use. Pick some as style references in Make.
- **Train a style.** From references you may use, with captions (written by Gemma 4, then read through by you), a LoRA is trained for HiDream-O1-Image or Qwen-Image-Edit-2511 with ComfyUI's own trainer. Pick it in Make, under Model.
- **Models.** What is installed, the helpers (cut-out, captions, segmentation), your Hugging Face token, and a restart button.

## The models

All free to run on your computer. Each has its own licence:

| Model | Licence | For a shop |
|---|---|---|
| [FLUX 3 Image Klein](https://huggingface.co/black-forest-labs/flux-3-image-klein) | FLUX Kommunity License | Images may be used commercially by businesses under US$5M a year in revenue. Its images may not be used to train other models. Fine-tuning needs a paid licence, so it isn't offered for training here. |
| [Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) | Apache 2.0 | Yes, training included |
| [HiDream-O1-Image](https://huggingface.co/HiDream-ai/HiDream-O1-Image) | MIT | Yes, training included |
| [BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet), [Lucida](https://huggingface.co/egeorcun/lucida) | MIT | Cut-outs |
| [Gemma 4 E4B](https://huggingface.co/google/gemma-4-e4b-it) | Apache 2.0 | Captions |
| [SAM 3.1](https://huggingface.co/facebook/sam3.1) | SAM License | Selecting parts |

Training pictures need a right to use: your own photographs, public domain or CC0, Creative Commons with credit, or a licence. Pictures marked "Unknown" are never used for training.

## How it works

For gear that is held or set down:

1. The product is placed on a frame at the model's preferred size, on a plain backdrop (`canvas.png`), with a mask of where the model may draw (`draw.png`): everywhere except the product, plus the parts hands may cover.
2. The model sees that picture as its reference, with the prompt, and draws only where the mask allows; the product's area is held to its own pixels at every step (ComfyUI's latent noise mask with differential diffusion).
3. EA Finish scales the model's picture to the output size and pastes the product from the full-resolution photo, with its edges cleaned of the old backdrop. "Exact detail, scene's light" instead keeps the photo's detail under the model's broader light and colour.

## Folder layout

```
ComfyUI_windows_portable\   ComfyUI and its Python
models\                     the model files
nodes\scene-generator\      this repository
data\products\              product photos, cut-outs, previews
data\results\               the pictures, one folder per day
data\references\            reference photographs with their credits
data\training\              training sets
data\secrets\               the Hugging Face token, on this computer only
setup\                      installer, model list, logs
```

## Code

- `__init__.py`: the ComfyUI extension's entry.
- `ea_scene/api.py`, `page.py`: the API under `/ea/api/` and the page under `/ea/`.
- `ea_scene/products.py`, `imaging.py`: cut-outs, edges, previews.
- `ea_scene/composite.py`: placement, the model's inputs, pasting back, parts maps.
- `ea_scene/scene.py`: scene settings and prompts.
- `ea_scene/workflows.py`, `nodes.py`, `jobs.py`: the ComfyUI workflows, the generator's nodes, and the jobs and results.
- `ea_scene/references.py`, `training.py`, `downloads.py`: references, training, model downloads.
- `web/`: the page (plain HTML, CSS and JavaScript modules).

The sample photo `web/samples/brescia-spadona.jpg` is "The Brescia Spadona 05" by Albion Europe ApS, [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/), from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:The_Brescia_Spadona_05.jpg), reduced in size.
