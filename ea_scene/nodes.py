"""ComfyUI nodes used by the generator's workflows.

EA Job Image / EA Job Mask   read what the generator prepared for a job (the product's photos, the
                             product on its frame, where the model may draw, style references).
EA Qwen Edit Encode          Qwen-Image-Edit's prompt encoder, with the first picture's reference kept
                             at its own size when the picture is the one being changed.
EA Detail Crop / Paste       the detail pass: the area around the product, enlarged for redrawing, and
                             the redrawn product blended back into the (enlarged) picture.
EA Finish                    saves the picture, the parts map and how it was made ("Exact photo": with the
                             photo's own detail put back on top).
EA Product Cut-out           finds the product in one of its photos and saves the cut-out.
EA Product Picture / Add View   a product's photo on a plain backdrop, and a model-made view kept with it.
"""
import json
import math
import os
import time

import numpy as np
import torch

import comfy.utils
import node_helpers

from . import imaging, jobs, products, references, training
from .util import load_gray, load_rgb, read_json, resize


def _image_tensor(a):
    return torch.from_numpy(np.ascontiguousarray(a[..., :3], dtype=np.float32))[None]


def _mask_tensor(a):
    return torch.from_numpy(np.ascontiguousarray(a, dtype=np.float32))[None]


def _first_mask(mask, h, w):
    """A MASK input as one (h, w) array in 0..1."""
    m = mask.detach().float().cpu().numpy()
    while m.ndim > 2:
        m = m[0]
    if m.shape != (h, w):
        m = resize(m, w, h, resample=2)
    return np.clip(m, 0, 1)


def _span(a, b, n):
    """Shift [a, b) inside [0, n) without changing its length, if it fits."""
    if b - a >= n:
        return 0, n
    if a < 0:
        b, a = b - a, 0
    if b > n:
        a, b = a - (b - n), n
    return int(math.floor(max(0, a))), int(math.ceil(min(n, b)))


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


class EADetailCrop:
    """The area around the product (where `mask` is), with a margin, no narrower than 1 : max_aspect,
    enlarged to about `megapixels` (at most 3 times) for the model to redraw; and the product's mask in it,
    grown a little and softened, for where the redraw may change things. `sizes` (a JSON list of [w, h]): for a
    model that draws only at certain sizes, the crop takes the nearest of them, with more of the picture around
    the product if needed."""
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('IMAGE', 'MASK', 'STRING')
    RETURN_NAMES = ('crop', 'crop_mask', 'info')
    FUNCTION = 'crop'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',), 'mask': ('MASK',),
                             'megapixels': ('FLOAT', {'default': 2.0, 'min': 0.25, 'max': 8.0, 'step': 0.05})},
                'optional': {'margin': ('FLOAT', {'default': 0.1, 'min': 0.0, 'max': 1.0, 'step': 0.01}),
                             'max_aspect': ('FLOAT', {'default': 2.0, 'min': 1.0, 'max': 4.0, 'step': 0.1}),
                             'sizes': ('STRING', {'default': ''})}}

    @staticmethod
    def _fixed_size(box, W, H, sizes):
        """A box around `box` with one of `sizes`' shapes, needing at most 3 times enlargement and inside the
        picture: the tightest, among shapes near the product's own; else the whole picture, at the size nearest
        its shape."""
        x0, y0, x1, y1 = box
        cw, ch = x1 - x0, y1 - y0
        best = None
        for w, h in sizes:
            bw = max(cw, ch * w / h, w / 3.0)
            bh = bw * h / w
            score = bw * bh * (1 + abs(math.log((w / h) / (cw / ch))))
            if bw <= W + 0.5 and bh <= H + 0.5 and (best is None or score < best[0]):
                best = (score, bw, bh, w, h)
        if best is None:
            w, h = min(sizes, key=lambda s: abs(math.log((s[0] / s[1]) / (W / H))))
            return (0, 0, W, H), (int(w), int(h))
        _, bw, bh, w, h = best
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        nx0, nx1 = _span(cx - bw / 2, cx + bw / 2, W)
        ny0, ny1 = _span(cy - bh / 2, cy + bh / 2, H)
        return (nx0, ny0, nx1, ny1), (int(w), int(h))

    def crop(self, image, mask, megapixels, margin=0.1, max_aspect=2.0, sizes=''):
        img = image[0].detach().float().cpu().numpy()[..., :3]
        H, W = img.shape[:2]
        m = _first_mask(mask, H, W) > 0.5
        found = bool(m.sum() > 0.0003 * H * W)
        fixed = [tuple(int(v) for v in s) for s in json.loads(sizes)] if sizes else []
        ps = 512.0
        if found:
            ys, xs = np.nonzero(m)
            x0, x1, y0, y1 = float(xs.min()), float(xs.max() + 1), float(ys.min()), float(ys.max() + 1)
            ps = max(x1 - x0, y1 - y0)
            pad = margin * ps + 16
            x0, x1, y0, y1 = x0 - pad, x1 + pad, y0 - pad, y1 + pad
            bw, bh = x1 - x0, y1 - y0
            if bw > bh * max_aspect:
                grow = (bw / max_aspect - bh) / 2
                y0, y1 = y0 - grow, y1 + grow
            elif bh > bw * max_aspect:
                grow = (bh / max_aspect - bw) / 2
                x0, x1 = x0 - grow, x1 + grow
            if fixed:
                (x0, y0, x1, y1), (tw, th) = self._fixed_size((x0, y0, x1, y1), W, H, fixed)
            x0, x1 = _span(x0, x1, W)
            y0, y1 = _span(y0, y1, H)
        else:
            x0, y0, x1, y1 = 0, 0, min(W, 512), min(H, 512)
        cw, ch = x1 - x0, y1 - y0
        if not (found and fixed):
            k = min(3.0, max(1.0, math.sqrt(megapixels * 1024 * 1024 / (cw * ch)))) if found else 1.0
            tw, th = max(64, int(round(cw * k / 32)) * 32), max(64, int(round(ch * k / 32)) * 32)
        crop = np.clip(resize(img[y0:y1, x0:x1], tw, th), 0, 1)
        if found:
            mm = m[y0:y1, x0:x1]
            mm = imaging.dilate(mm, max(3, int(0.018 * ps)))
            mm = imaging.feather(mm.astype(np.float32), max(1.5, 0.007 * ps))
            mm = np.clip(resize(mm, tw, th, resample=2), 0, 1)
        else:
            mm = np.zeros((th, tw), np.float32)
        info = {'found': found, 'box': [int(x0), int(y0), int(x1), int(y1)], 'frame': [int(W), int(H)], 'size': [int(tw), int(th)]}
        return (_image_tensor(crop), _mask_tensor(mm), json.dumps(info))


class EADetailPaste:
    """The picture at width x height (resized if it isn't), with the redrawn product blended back in; and a
    log of the passes so far (what each looked for, whether it was found, and where), kept with the result."""
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('IMAGE', 'STRING')
    RETURN_NAMES = ('image', 'log')
    FUNCTION = 'paste'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'base': ('IMAGE',), 'refined': ('IMAGE',), 'crop_mask': ('MASK',), 'info': ('STRING', {'forceInput': True}),
                             'width': ('INT', {'default': 2048, 'min': 64, 'max': 16384}),
                             'height': ('INT', {'default': 2048, 'min': 64, 'max': 16384})},
                'optional': {'keep_colour': ('FLOAT', {'default': 1.0, 'min': 0.0, 'max': 1.0, 'step': 0.05,
                                                       'tooltip': 'How much of the picture\'s own colour the redrawn area keeps '
                                                                  '(its light, shade and detail stay as redrawn).'}),
                             'label': ('STRING', {'default': ''}),
                             'log': ('STRING', {'forceInput': True})}}

    def paste(self, base, refined, crop_mask, info, width, height, keep_colour=1.0, label='', log=None):
        out = base[0].detach().float().cpu().numpy()[..., :3]
        if out.shape[:2] != (height, width):
            out = np.clip(resize(out, width, height), 0, 1)
        else:
            out = out.copy()
        meta = json.loads(info)
        try:
            entries = json.loads(log) if log else []
        except ValueError:
            entries = []
        entries.append({'pass': label, 'found': bool(meta.get('found')), 'box': meta.get('box'), 'size': meta.get('size'),
                        'frame': meta.get('frame'), 'keep_colour': float(keep_colour)})
        if not meta.get('found'):
            return (_image_tensor(out), json.dumps(entries))
        x0, y0, x1, y1 = meta['box']
        FW, FH = meta['frame']
        fx, fy = width / FW, height / FH
        X0, Y0 = int(round(x0 * fx)), int(round(y0 * fy))
        X1, Y1 = min(width, int(round(x1 * fx))), min(height, int(round(y1 * fy)))
        bw, bh = X1 - X0, Y1 - Y0
        r = np.clip(resize(refined[0].detach().float().cpu().numpy()[..., :3], bw, bh), 0, 1)
        mk = _first_mask(crop_mask, bh, bw)[..., None]
        region = out[Y0:Y1, X0:X1]
        if keep_colour > 0:
            r = imaging.keep_colour(region, r, sigma=max(3.0, 0.01 * max(bw, bh)), amount=float(keep_colour))
        out[Y0:Y1, X0:X1] = region * (1 - mk) + r * mk
        return (_image_tensor(out), json.dumps(entries))


class EAFinish:
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ()
    FUNCTION = 'finish'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'images': ('IMAGE',), 'job': ('STRING', {'default': ''}),
                             'variation': ('INT', {'default': 0, 'min': 0, 'max': 1000})},
                'optional': {'raw': ('IMAGE',), 'mask': ('MASK',), 'passes': ('STRING', {'forceInput': True})}}

    def finish(self, images, job, variation=0, raw=None, mask=None, passes=None):
        arr = images.detach().float().cpu().numpy()
        raws = None if raw is None else raw.detach().float().cpu().numpy()
        masks = None
        if mask is not None:
            masks = mask.detach().float().cpu().numpy()
            if masks.ndim == 2:
                masks = masks[None]
        results = []
        for i in range(arr.shape[0]):
            r = raws[min(i, raws.shape[0] - 1)][..., :3] if raws is not None else None
            m = masks[min(i, masks.shape[0] - 1)] if masks is not None and masks.shape[0] else None
            results.append(jobs.finish(job, arr[i][..., :3], index=variation + i, raw=r, mask=m, passes=passes))
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
                'optional': {'mask': ('MASK',), 'view': ('STRING', {'default': ''})}}

    @classmethod
    def IS_CHANGED(cls, product, method, mask=None, view=''):
        return time.time()

    def cut(self, product, method, mask=None, view=''):
        m = None if mask is None else mask.detach().float().cpu().numpy()
        if m is not None and m.ndim == 3:
            m = m.max(axis=0)
        if view:
            info = products.cut_out_view(product, view, method, mask=m)
        else:
            info = products.cut_out(product, method, mask=m)
        return {'ui': {'ea_product': [info]}}


class EAProductPicture:
    """A product's photo on a plain backdrop, cropped to it ('main' or one of its other photos)."""
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'product': ('STRING', {'default': ''}), 'view': ('STRING', {'default': 'main'})}}

    @classmethod
    def _path(cls, product, view):
        if not view or view == 'main':
            return products.main_reference(product)
        return os.path.join(products.view_folder(product, view), 'ref.png')

    @classmethod
    def IS_CHANGED(cls, product, view):
        p = cls._path(product, view)
        return os.path.getmtime(p) if os.path.isfile(p) else time.time()

    def load(self, product, view):
        return (_image_tensor(load_rgb(self._path(product, view))),)


class EAAddView:
    """Keeps a picture a model made of the product as one of its photos, marked as made by a model."""
    CATEGORY = 'Empirical Armory'
    RETURN_TYPES = ()
    FUNCTION = 'add'
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'images': ('IMAGE',), 'product': ('STRING', {'default': ''}),
                             'label': ('STRING', {'default': ''}), 'source': ('STRING', {'default': 'main'})}}

    def add(self, images, product, label, source):
        arr = images.detach().float().cpu().numpy()
        views = [products.add_view_array(product, arr[i][..., :3], label=label, source=source) for i in range(arr.shape[0])]
        return {'ui': {'ea_view': views}}


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
    'EADetailCrop': EADetailCrop,
    'EADetailPaste': EADetailPaste,
    'EAFinish': EAFinish,
    'EAProductCutout': EAProductCutout,
    'EAProductPicture': EAProductPicture,
    'EAAddView': EAAddView,
    'EARefImage': EARefImage,
    'EASaveCaption': EASaveCaption,
    'EATrainingImages': EATrainingImages,
    'EASaveLoRA': EASaveLoRA,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    'EAJobImage': 'EA Job Image',
    'EAJobMask': 'EA Job Mask',
    'EAQwenEditEncode': 'EA Qwen Edit Encode',
    'EADetailCrop': 'EA Detail Crop',
    'EADetailPaste': 'EA Detail Paste',
    'EAFinish': 'EA Finish',
    'EAProductCutout': 'EA Product Cut-out',
    'EAProductPicture': 'EA Product Picture',
    'EAAddView': 'EA Add View',
    'EARefImage': 'EA Reference Picture',
    'EASaveCaption': 'EA Save Caption',
    'EATrainingImages': 'EA Training Set',
    'EASaveLoRA': 'EA Save Trained Style',
}
