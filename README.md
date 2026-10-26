# Empirical Armory · scene generator

Draws a real product into a generated scene: a place, the light, hands or a masked fencer holding the gear, and the camera's angle and lens. The model is given your photos of the product and draws it at the angle, size and grip the scene needs, in the scene's own light; a detail pass then redraws the product against your photos so that its cross, grip, pommel or stitching match. For pictures that must show the real thing (a blade's flex, say), "Exact photo" keeps your photo as taken and builds the scene around it.

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

- **Make.** Add a product photo, on a plain backdrop if you can, and under "Photos of it" more photos of its other sides and close-ups. Each is cut out automatically (BiRefNet); "Check the cut-out" fixes the main photo's edges with a brush or lasso. "What it's made of" tells the model how the product takes light. With one photo only, "Make other angles…" has Qwen-Image-Edit-2511 turn it to new views; these are marked as model-made, so check them before you keep them. Pick a starting scene, then the place, light, people, pose and camera. Choose a model and Generate.
- **Picture.** "Drawn into the scene" (the default) lets the model choose the product's angle and size; the detail pass then redraws the product against its photos, and for a sword a closer look at the hilt follows. Tick "Use the frame as a rough guide" to say roughly where it goes, by dragging it in the frame. "Exact photo" puts your photo in exactly where you drag it, and "Relight the photo to the scene" lets the scene's light fall on it. "Enlarge with SeedVR2" gives the finished picture real detail at the output size.
- **Results.** Every picture, with the model's first pass (before the detail or relight pass), the parts map, and how it was made. "Use these settings" brings a picture's settings, seed included, back to Make.
- **Compare models.** The same product, scenes and seeds through each model, side by side.
- **References.** Photographs whose look your scenes should follow. Find openly licensed ones (Openverse: CC0, public domain, CC BY, CC BY-SA), or add your own, and record each one's creator, licence and right to use. Pick some as style references in Make.
- **Train a style.** From references you may use, with captions (written by Gemma 4, then read through by you), a LoRA is trained for HiDream-O1-Image or Qwen-Image-Edit-2511 with ComfyUI's own trainer. Pick it in Make, under Model.
- **Models.** What is installed, the helpers (cut-outs, captions, finding the product, other angles, enlarging), your Hugging Face token, and a restart button.

## The models

All free to run on your computer. Each has its own licence:

| Model | Licence | For a shop |
|---|---|---|
| [FLUX 3 Image Klein](https://huggingface.co/black-forest-labs/flux-3-image-klein) | FLUX Kommunity License | Images may be used commercially by businesses under US$5M a year in revenue. Its images may not be used to train other models. Fine-tuning needs a paid licence, so it isn't offered for training here. |
| [Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) | Apache 2.0 | Yes, training included |
| [HiDream-O1-Image](https://huggingface.co/HiDream-ai/HiDream-O1-Image) | MIT | Yes, training included |
| [BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet), [Lucida](https://huggingface.co/egeorcun/lucida) | MIT | Cut-outs |
| [Gemma 4 E4B](https://huggingface.co/google/gemma-4-e4b-it) | Apache 2.0 | Captions |
| [SAM 3.1](https://huggingface.co/facebook/sam3.1) | SAM License | Finding the product in a picture (detail pass, parts map) |
| [Multiple angles LoRA](https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA) for Qwen-Image-Edit-2511, by fal | Apache 2.0 | New views of a product from one photo |
| [SeedVR2 7B](https://huggingface.co/Comfy-Org/SeedVR2), by ByteDance Seed | Apache 2.0 | Enlarging the finished picture |

Training pictures need a right to use: your own photographs, public domain or CC0, Creative Commons with credit, or a licence. Pictures marked "Unknown" are never used for training.

## How it works

This follows the usual way of putting a real product into generated photographs with open models: reference photos of the product, generation from those references, then a detail pass against them.

**Drawn into the scene** (the default):

1. Each photo of the product is cut out and put on a plain light grey backdrop, cropped to the product (`ref.png`). A photo that cuts the product off is taken as a close-up (each photo's Whole or Close-up can be changed). The model is given these as its first pictures, whole views first (up to 3 with Qwen-Image-Edit-2511 and 10 with FLUX 3; HiDream-O1-Image gets the main photo only, because given several photos of one product it lays them out as a collage), then any style references, with a prompt that names them in order: "the longsword shown in the first three pictures, held upright in one hand…", "the first picture shows the whole longsword; the second and third pictures are close-ups of its details", what it is made of, and that it must be exactly that product, its shape and proportions as in the whole views, seen at the angle and size the photograph needs and lit by its light.
2. The model draws the whole picture from an empty start. If the frame is used as a guide, the prompt says roughly where the product goes; FLUX 3 also gets its own layout box.
3. The detail pass. SAM 3 finds the product in the picture by name ("sword", "glove:2"). The area around it is cut out with a margin, enlarged to about 2 to 4 megapixels, and redrawn at part strength (0.55 by default) with the product's photos beside it, only within the product and a little around it (latent noise mask with differential diffusion). The redrawn area is blended back into the picture at the output size, enlarged by SeedVR2 if chosen; it keeps the picture's own colour, so only its light, shade, edges and texture come from the redraw (a redraw can drift in colour: a black grip turning green). For a sword, SAM 3 then finds the hilt in that picture, and it is cut out at up to three times its size and redrawn once more (0.1 stronger) with the close-ups beside it: the cross, the grip's wrap and ring, the pommel's facets.
4. SAM 3 finds the product once more in the finished picture, and its mask, snapped to the edges, becomes the parts map. What each detail pass found, and where, is kept in the picture's `.json`.

**Exact photo:**

1. The product is placed on a frame at the model's preferred size, on a plain backdrop (`canvas.png`), with a mask of where the model may draw (`draw.png`): everywhere except the product, plus the parts hands may cover. The model draws the scene around it while the product's area is held to its own pixels at every step.
2. The relight pass (if ticked) redraws the picture at part strength: fully over the product, strongly in a ring around it for contact shadows, lightly elsewhere (`harmonize.png`), with the product's photo beside it.
3. EA Finish scales the picture to the output size and puts the photo's fine detail back over the product from the full-resolution photo: its pixels as they are, or, after the relight pass, its detail under the relit light and colour.

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
- `ea_scene/products.py`, `imaging.py`: products and their photos, cut-outs, edges, previews.
- `ea_scene/composite.py`: placement, the model's inputs for an exact photo, putting it back, parts maps.
- `ea_scene/scene.py`: scene settings and prompts (natural, exact, detail pass, relight, angles).
- `ea_scene/workflows.py`, `nodes.py`, `jobs.py`: the ComfyUI workflows (one kit per model, shared by every pass), the generator's nodes (including the detail pass's crop and paste), and the jobs and results.
- `ea_scene/references.py`, `training.py`, `downloads.py`: references, training, model downloads.
- `web/`: the page (plain HTML, CSS and JavaScript modules).

The sample photo `web/samples/brescia-spadona.jpg` is "The Brescia Spadona 05" by Albion Europe ApS, [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/), from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:The_Brescia_Spadona_05.jpg), reduced in size.
