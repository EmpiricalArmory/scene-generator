"""The image models the generator can use, what files each needs, and how each likes to be run."""
import os

from . import paths

# Trained frame sizes. HiDream-O1 was trained at about 4 megapixels and loses quality below it.
HIDREAM_SIZES = [(2048, 2048), (2304, 1728), (1728, 2304), (2560, 1440), (1440, 2560), (2496, 1664),
                 (1664, 2496), (3104, 1312), (1312, 3104), (2304, 1792), (1792, 2304)]

FAMILIES = {
    'flux3': {
        'name': 'FLUX 3 Image Klein',
        'maker': 'Black Forest Labs',
        'licence': 'FLUX Kommunity License: images may be used commercially by businesses under US$5M a year in revenue; not for training other models; fine-tuning needs a paid licence.',
        'files': {
            'unet': ('diffusion_models', 'flux3-image-klein-bf16.safetensors'),
            'clip': ('text_encoders', 'qwen3vl_4b_bf16.safetensors'),
            'vae': ('vae', 'flux2-vae.safetensors'),
        },
        'optional': {
            'upsampler': ('text_encoders', 'qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors'),
            'base': ('diffusion_models', 'flux3-image-klein-base-bf16.safetensors'),
        },
        'megapixels': {'final': 4.0, 'draft': 1.0},
        'quality': {'final': {'steps': 16}, 'draft': {'steps': 8}},
        'max_refs': 9,
        'pictures': 10,          # product photos and style references together
        'first_pass': {'closeups': True},
        'note': 'About 4 to 5 minutes a picture on an RTX 4090. Draws from all your photos, close-ups included.',
        'detail_mp': {'final': 4.0, 'draft': 1.5},
    },
    'qwen': {
        'name': 'Qwen-Image-Edit-2511',
        'maker': 'Alibaba Qwen',
        'licence': 'Apache 2.0: free for any use, fine-tuning included.',
        'files': {
            'unet': ('diffusion_models', 'qwen_image_edit_2511_bf16.safetensors'),
            'clip': ('text_encoders', 'qwen_2.5_vl_7b.safetensors'),
            'vae': ('vae', 'qwen_image_vae.safetensors'),
        },
        'optional': {
            'lightning': ('loras', 'Qwen-Image-Edit-2511-Lightning-8steps-V1.0-bf16.safetensors'),
        },
        'megapixels': {'final': 1.6, 'draft': 1.0},
        'quality': {'final': {'steps': 40, 'cfg': 4.0}, 'draft': {'steps': 8, 'cfg': 1.0}},
        'max_refs': 2,
        'pictures': 3,
        'first_pass': {'closeups': False},      # close-ups pull its framing in close and cut the product off
        'note': 'About 16 minutes a picture (it doesn\'t fit in 24 GB, so it streams). Draws from up to 3 whole views; '
                'the close-ups go to the detail pass.',
        'detail_mp': {'final': 2.0, 'draft': 1.2},
    },
    'hidream': {
        'name': 'HiDream-O1-Image',
        'maker': 'HiDream.ai',
        'licence': 'MIT: free for any use, fine-tuning included.',
        'files': {
            'ckpt': ('checkpoints', 'hidream_o1_image_bf16.safetensors'),
        },
        'optional': {},
        'sizes': HIDREAM_SIZES,
        'quality': {'final': {'steps': 50, 'cfg': 5.0}, 'draft': {'steps': 28, 'cfg': 5.0}},
        'max_refs': 4,
        'pictures': 5,
        # given several photos of one product, HiDream-O1 lays them out as a collage of panels: its first pass
        # gets the main photo (and one style reference at most); the close-ups go to the detail passes
        'first_pass': {'views': 1, 'closeups': False, 'refs': 1},
        'note': 'About 8 to 9 minutes a picture. Draws from the main photo only (given more, it lays them out as a '
                'collage); the close-ups go to the detail pass.',
        'detail_mp': {'final': 4.0, 'draft': 3.0},
    },
}

SAM3 = ('checkpoints', 'sam3.1_multiplex_fp16.safetensors')
ANGLES_LORA = ('loras', 'qwen-image-edit-2511-multiple-angles-lora.safetensors')
SEEDVR2 = {'unet': ('diffusion_models', 'seedvr2_7b_int8_convrot.safetensors'),
           'vae': ('vae', 'seedvr2_ema_vae_fp16.safetensors')}

HELPERS = {
    'birefnet': {'label': 'BiRefNet (cut-outs)', 'folder': 'background_removal', 'file': 'birefnet.safetensors',
                 'url': 'https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors',
                 'size': 444473596, 'sha256': '9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154', 'licence': 'MIT'},
    'lucida': {'label': 'Lucida (cut-outs, finer soft edges)', 'folder': 'background_removal', 'file': 'lucida.safetensors',
               'url': 'https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/lucida.safetensors',
               'size': 884878856, 'sha256': 'a43e3dd84cbe84db76bd2015ef8f7034c9503c50d9b56fa2155803b69bd2f408', 'licence': 'MIT'},
    'sam3': {'label': 'SAM 3.1 (select parts by name or by clicking)', 'folder': 'checkpoints', 'file': 'sam3.1_multiplex_fp16.safetensors',
             'url': 'https://huggingface.co/Comfy-Org/sam3.1/resolve/main/checkpoints/sam3.1_multiplex_fp16.safetensors',
             'size': 1745546848, 'sha256': '9ba99c92703c2e8b4f47de2d34a539bb8e18923049e238b780d70dbe6368eb03', 'licence': 'SAM License (commercial use allowed)'},
    'gemma4': {'label': 'Gemma 4 E4B (writes captions for training)', 'folder': 'text_encoders', 'file': 'gemma4_e4b_it_fp8_scaled.safetensors',
               'url': 'https://huggingface.co/Comfy-Org/gemma-4/resolve/main/text_encoders/gemma4_e4b_it_fp8_scaled.safetensors',
               'size': 9057782194, 'sha256': 'bf0b4fa2e41a25684dc9e9b256cd505564f02fed09be3da95ce024e653e2c52b', 'licence': 'Apache 2.0'},
    'angles': {'label': 'Multiple angles for Qwen-Image-Edit-2511 (makes other views of a product from one photo)', 'folder': 'loras',
               'file': 'qwen-image-edit-2511-multiple-angles-lora.safetensors',
               'url': 'https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA/resolve/main/qwen-image-edit-2511-multiple-angles-lora.safetensors',
               'size': 295140688, 'sha256': '42426ded4e25fd22879d9e198b857556445ef4ca56e8da3246d0345155bb6765', 'licence': 'Apache 2.0 (by fal)'},
    'seedvr2': {'label': 'SeedVR2 7B (enlarges the finished picture with real detail)', 'licence': 'Apache 2.0 (by ByteDance Seed)',
                'files': [
                    {'folder': 'diffusion_models', 'file': 'seedvr2_7b_int8_convrot.safetensors',
                     'url': 'https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_7b_int8_convrot.safetensors',
                     'size': 8334897976, 'sha256': '5aa0d25fc9d35e449b659d0c9a5dcb22e2a4fa04032101b95a39da42b32c1be6'},
                    {'folder': 'vae', 'file': 'seedvr2_ema_vae_fp16.safetensors',
                     'url': 'https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/vae/seedvr2_ema_vae_fp16.safetensors',
                     'size': 501324814, 'sha256': '20678548f420d98d26f11442d3528f8b8c94e57ee046ef93dbb7633da8612ca1'},
                ]},
}


def helper_files(h):
    """A helper's files: most have one, some (SeedVR2) more."""
    if h.get('files'):
        return h['files']
    return [{'folder': h['folder'], 'file': h['file'], 'url': h['url'], 'size': h['size'], 'sha256': h['sha256']}]


def _have(folder, name):
    try:
        import folder_paths
        return name in folder_paths.get_filename_list(folder)
    except Exception:
        return os.path.isfile(os.path.join(paths.MODELS, folder, name))


def have_helper(key):
    return all(_have(f['folder'], f['file']) for f in helper_files(HELPERS[key]))


def status():
    out = {}
    for key, f in FAMILIES.items():
        need = {k: _have(*v) for k, v in f['files'].items()}
        opt = {k: _have(*v) for k, v in f.get('optional', {}).items()}
        out[key] = {'name': f['name'], 'maker': f['maker'], 'licence': f['licence'], 'ready': all(need.values()),
                    'files': need, 'optional': opt, 'max_refs': f['max_refs'], 'pictures': f['pictures'],
                    'note': f.get('note', '')}
    out['_helpers'] = {k: {'label': h['label'], 'ready': have_helper(k), 'licence': h['licence'],
                           'size': sum(x['size'] for x in helper_files(h))} for k, h in HELPERS.items()}
    return out
