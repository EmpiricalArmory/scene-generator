"""The image models the generator can use, what files each needs, and how each likes to be run."""
import os

from . import paths
from .util import read_json

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
    },
}

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
}


def _have(folder, name):
    try:
        import folder_paths
        return name in folder_paths.get_filename_list(folder)
    except Exception:
        return os.path.isfile(os.path.join(paths.MODELS, folder, name))


def status():
    out = {}
    for key, f in FAMILIES.items():
        need = {k: _have(*v) for k, v in f['files'].items()}
        opt = {k: _have(*v) for k, v in f.get('optional', {}).items()}
        out[key] = {'name': f['name'], 'maker': f['maker'], 'licence': f['licence'], 'ready': all(need.values()),
                    'files': need, 'optional': opt, 'max_refs': f['max_refs']}
    out['_helpers'] = {k: {'label': h['label'], 'ready': _have(h['folder'], h['file']), 'licence': h['licence']} for k, h in HELPERS.items()}
    return out
