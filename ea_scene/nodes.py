"""ComfyUI nodes used by the generator's workflows.

EA Job Image / EA Job Mask   read what the generator prepared for a job (the product on its frame,
                             where the model may draw, style references).
EA Qwen Edit Encode          Qwen-Image-Edit's prompt encoder, with the first picture's reference kept
                             at the frame's own size so the edit lines up with the product.
EA Finish                    puts the product's own pixels back on the generated picture and saves it.
EA Product Cut-out           finds the product in its photo and saves the cut-out.
"""
import math
import os
import time

import numpy as np
import torch

import comfy.utils
import node_helpers

from . import jobs, paths, products, references, training
from .util import load_gray, load_rgb, read_json


def _image_tensor(a):
    return torch.from_numpy(np.ascontiguousarray(a[..., :3], dtype=np.float32))[None]


class EAJobImage:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'job': ('STRING', {'default': ''}), 'name': ('STRING', {'default': 'canvas'})}}

    @classmethod
    def IS_CHANGED(cls, job, name):
        p = jobs.file_path(job, name + '.png')
        return os.path.getmtime(p) if os.path.isfile(p) else time.time()

    def load(self, job, name):
        return (_image_tensor(load_rgb(jobs.file_path(job, name + '.png'))),)


class EAJobMask:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('MASK',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'job': ('STRING', {'default': ''}), 'name': ('STRING', {'default': 'draw'})}}

    @classmethod
    def IS_CHANGED(cls, job, name):
        p = jobs.file_path(job, name + '.png')
        return os.path.getmtime(p) if os.path.isfile(p) else time.time()

    def load(self, job, name):
        m = load_gray(jobs.file_path(job, name + '.png'))
        return (torch.from_numpy(np.ascontiguousarray(m, dtype=np.float32))[None],)


class EAQwenEditEncode:
    """TextEncodeQwenImageEditPlus with the first picture's reference latent at `ref_megapixels`
    (0 keeps the picture's own size) instead of always about 1 megapixel."""
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('CONDITIONING',)
    FUNCTION = 'encode'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'clip': ('CLIP',), 'prompt': ('STRING', {'multiline': True}),
                             'ref_megapixels': ('FLOAT', {'default': 0.0, 'min': 0.0, 'max': 16.0, 'step': 0.01})},
                'optional': {'vae': ('VAE',), 'image1': ('IMAGE',), 'image2': ('IMAGE',), 'image3': ('IMAGE',)}}

    def encode(self, clip, prompt, ref_megapixels, vae=None, image1=None, image2=None, image3=None):
        ref_latents = []
        images_vl = []
        llama_template = ("<|im_start|>system\nDescribe the key features of the input image (color, shape, size, texture, objects, background), "
                          "then explain how the user's text instruction should alter or modify the image. Generate a new image that meets the "
                          "user's requirements while maintaining consistency with the original input where appropriate.<|im_end|>\n"
                          "<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n")
        image_prompt = ''
        for i, image in enumerate([image1, image2, image3]):
            if image is None:
                continue
            samples = image.movedim(-1, 1)
            h, w = samples.shape[2], samples.shape[3]
            scale = math.sqrt(384 * 384 / (w * h))
            s = comfy.utils.common_upscale(samples, round(w * scale), round(h * scale), 'area', 'disabled')
            images_vl.append(s.movedim(1, -1))
            if vae is not None:
                mp = ref_megapixels if (i == 0 and ref_megapixels > 0) else (0 if i == 0 else 1.0)
                if mp > 0:
                    scale = math.sqrt(mp * 1024 * 1024 / (w * h))
                    tw, th = round(w * scale / 16.0) * 16, round(h * scale / 16.0) * 16
                else:
                    tw, th = round(w / 16.0) * 16, round(h / 16.0) * 16
                s = comfy.utils.common_upscale(samples, tw, th, 'area', 'disabled')
                ref_latents.append(vae.encode(s.movedim(1, -1)[:, :, :, :3]))
            image_prompt += 'Picture {}: <|vision_start|><|image_pad|><|vision_end|>'.format(i + 1)
        tokens = clip.tokenize(image_prompt + prompt, images=images_vl, llama_template=llama_template)
        conditioning = clip.encode_from_tokens_scheduled(tokens)
        if ref_latents:
            conditioning = node_helpers.conditioning_set_values(conditioning, {'reference_latents': ref_latents}, append=True)
        return (conditioning,)


class EAFinish:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ()
    FUNCTION = 'finish'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'images': ('IMAGE',), 'job': ('STRING', {'default': ''}),
                             'variation': ('INT', {'default': 0, 'min': 0, 'max': 1000})}}

    def finish(self, images, job, variation=0):
        arr = images.detach().float().cpu().numpy()
        results = [jobs.finish(job, arr[i], index=variation + i) for i in range(arr.shape[0])]
        return {'ui': {'ea_results': results}}


class EAProductCutout:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ()
    FUNCTION = 'cut'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'product': ('STRING', {'default': ''}),
                             'method': (['auto', 'model', 'white backdrop'],)},
                'optional': {'mask': ('MASK',)}}

    @classmethod
    def IS_CHANGED(cls, product, method, mask=None):
        return time.time()

    def cut(self, product, method, mask=None):
        m = None if mask is None else mask.detach().float().cpu().numpy()
        if m is not None and m.ndim == 3:
            m = m.max(axis=0)
        info = products.cut_out(product, method, mask=m)
        return {'ui': {'ea_product': [info]}}


class EARefImage:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'ref': ('STRING', {'default': ''})}}

    def load(self, ref):
        r = read_json(os.path.join(references.folder(ref), 'reference.json'))
        rgb = load_rgb(os.path.join(references.folder(ref), r['file']))
        h, w = rgb.shape[:2]
        s = min(1.0, (1.5 * 1024 * 1024 / (h * w)) ** 0.5)
        if s < 1:
            from .util import resize
            rgb = resize(rgb, w * s, h * s)
        return (_image_tensor(rgb),)


class EASaveCaption:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ()
    FUNCTION = 'save'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'ref': ('STRING', {'default': ''}), 'text': ('STRING', {'forceInput': True}),
                             'trigger': ('STRING', {'default': training.TRIGGER})}}

    def save(self, ref, text, trigger):
        cap = ' '.join(str(text).split())
        if trigger and not cap.lower().startswith(trigger.lower()):
            cap = f'{trigger}, {cap}'
        references.update(ref, {'caption': cap})
        return {'ui': {'ea_caption': [{'ref': ref, 'caption': cap}]}}


class EATrainingImages:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('images', 'texts')
    OUTPUT_IS_LIST = (True, True)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'set': ('STRING', {'default': ''})}}

    def load(self, set):
        imgs, texts = training.images_and_texts(set)
        return ([_image_tensor(i) for i in imgs], texts)


class EASaveLoRA:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ()
    FUNCTION = 'save'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'lora': ('LORA_MODEL',), 'set': ('STRING', {'default': ''})},
                'optional': {'steps': ('INT', {'forceInput': True})}}

    def save(self, lora, set, steps=None):
        return {'ui': {'ea_training': [training.save_lora(set, lora, steps)]}}


NODE_CLASS_MAPPINGS = {
    'EAJobImage': EAJobImage,
    'EAJobMask': EAJobMask,
    'EAQwenEditEncode': EAQwenEditEncode,
    'EAFinish': EAFinish,
    'EAProductCutout': EAProductCutout,
    'EARefImage': EARefImage,
    'EASaveCaption': EASaveCaption,
    'EATrainingImages': EATrainingImages,
    'EASaveLoRA': EASaveLoRA,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    'EAJobImage': 'EA Job Image',
    'EAJobMask': 'EA Job Mask',
    'EAQwenEditEncode': 'EA Qwen Edit Encode',
    'EAFinish': 'EA Finish (product pasted back)',
    'EAProductCutout': 'EA Product Cut-out',
    'EARefImage': 'EA Reference Picture',
    'EASaveCaption': 'EA Save Caption',
    'EATrainingImages': 'EA Training Set',
    'EASaveLoRA': 'EA Save Trained Style',
}
