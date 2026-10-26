"""Training a style from the references: captions, the training set, and a LoRA trained in ComfyUI.

A training set lives in data/training/<id>/: set.json, and images/ with each picture cut to one of the
base model's trained sizes and a .txt caption beside it. The trained LoRA goes to models/loras/ea/.

Only pictures with a recorded right to use (own, CC0, CC BY, licensed) and "Use for training" ticked go in.
FLUX 3 Image Klein is not offered: its free licence does not cover fine-tuning.
"""
import os
import shutil

import numpy as np

from . import paths, references
from .models import FAMILIES, HIDREAM_SIZES
from .util import inside, load_rgb, new_id, now_iso, read_json, resize, safe_name, save_png, write_json

ROOT = os.path.join(paths.DATA, 'training')
TRIGGER = 'eaphoto'
BASES = {'hidream': 'HiDream-O1-Image', 'qwen': 'Qwen-Image-Edit-2511'}
QWEN_SIZES = [(1024, 1024), (896, 1152), (1152, 896), (832, 1216), (1216, 832), (768, 1344), (1344, 768)]

CAPTION_MODEL = ('text_encoders', 'gemma4_e4b_it_fp8_scaled.safetensors')
CAPTION_INSTRUCTION = (
    'Describe this photograph in one paragraph of plain English, for an image model that will learn its look. '
    'Say what is in it: the gear, any people, what they wear and do, and whether faces are visible or hidden by fencing masks. '
    'Then the place, the light and where it comes from, the camera\'s height and distance, the depth of field, '
    'the colours, and the photographic qualities such as grain, contrast and sharpness. '
    'Do not mention watermarks, text or brand names. Do not start with "This image" or "The photograph".')


def folder(sid):
    return inside(ROOT, safe_name(sid))


def load(sid):
    s = read_json(os.path.join(folder(sid), 'set.json'))
    if not s:
        raise KeyError('No such training set: ' + str(sid))
    return s


def save(s):
    s['updated'] = now_iso()
    write_json(os.path.join(folder(s['id']), 'set.json'), s)
    return s


def all_sets():
    if not os.path.isdir(ROOT):
        return []
    out = [read_json(os.path.join(ROOT, d, 'set.json')) for d in os.listdir(ROOT)]
    return sorted([s for s in out if s], key=lambda s: s.get('created', ''), reverse=True)


def usable(r):
    return r.get('train') and r.get('rights') in ('own', 'cc0', 'cc-by', 'licensed')


def _fit(rgb, sizes):
    """Centre-crop to the closest trained aspect, then resize to that size."""
    h, w = rgb.shape[:2]
    a = w / h
    tw, th = min(sizes, key=lambda s: abs(np.log((s[0] / s[1]) / a)))
    ta = tw / th
    if a > ta:                       # too wide: crop the sides
        cw = int(round(h * ta)); x0 = (w - cw) // 2
        rgb = rgb[:, x0:x0 + cw]
    else:                            # too tall: crop top and bottom
        ch = int(round(w / ta)); y0 = (h - ch) // 2
        rgb = rgb[y0:y0 + ch]
    return resize(rgb, tw, th)


def default_steps(n):
    return int(min(3000, max(1000, 100 * n)))


def create(name, base, ref_ids=None, trigger=TRIGGER, steps=None, rank=16, learning_rate=1e-4):
    if base not in BASES:
        raise ValueError('Training is offered for HiDream-O1-Image and Qwen-Image-Edit-2511 (FLUX 3\'s free licence does not cover fine-tuning).')
    refs = [r for r in references.all_references() if usable(r) and (not ref_ids or r['id'] in ref_ids)]
    if len(refs) < 5:
        raise ValueError(f'A style needs at least 5 usable pictures (with a recorded right and "Use for training" ticked); there are {len(refs)}.')
    sid = new_id('t')
    d = folder(sid)
    img_dir = os.path.join(d, 'images')
    os.makedirs(img_dir, exist_ok=True)
    sizes = HIDREAM_SIZES if base == 'hidream' else QWEN_SIZES
    items = []
    for i, r in enumerate(refs):
        src = inside(references.ROOT, safe_name(r['id']), r['file'])
        orig = load_rgb(src)
        rgb = _fit(orig, sizes)
        upscale = round((rgb.shape[0] * rgb.shape[1] / (orig.shape[0] * orig.shape[1])) ** 0.5, 2)
        save_png(os.path.join(img_dir, f'{i:03d}.png'), rgb, compress=3)
        cap = (r.get('caption') or '').strip()
        if not cap.lower().startswith(trigger.lower()):
            cap = f'{trigger}, ' + (cap or 'a photograph')
        with open(os.path.join(img_dir, f'{i:03d}.txt'), 'w', encoding='utf-8') as f:
            f.write(cap)
        items.append({'ref': r['id'], 'file': f'{i:03d}.png', 'size': [int(rgb.shape[1]), int(rgb.shape[0])], 'upscaled': upscale,
                      'credit': {'title': r.get('title'), 'creator': r.get('creator'), 'licence': r.get('licence'), 'source': r.get('source')}})
    s = {'id': sid, 'name': name or 'EA style', 'base': base, 'trigger': trigger, 'created': now_iso(), 'items': items,
         'steps': int(steps or default_steps(len(items))), 'rank': int(rank), 'learning_rate': float(learning_rate),
         'state': 'ready', 'lora': None, 'soft': sum(1 for it in items if it['upscaled'] > 1.5)}
    return save(s)


def lora_name(s):
    return 'ea/' + safe_name(s['name'], 'style').lower() + '-' + s['base'] + '-' + s['id'][-5:] + '.safetensors'


def save_lora(sid, lora, steps=None):
    import safetensors.torch
    s = load(sid)
    rel = lora_name(s)
    path = os.path.join(paths.MODELS, 'loras', *rel.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    safetensors.torch.save_file(lora, path)
    s.update(state='done', lora=rel, trained_steps=int(steps or s['steps']), finished=now_iso())
    save(s)
    return {'set': sid, 'lora': rel}


def images_and_texts(sid):
    s = load(sid)
    d = os.path.join(folder(sid), 'images')
    imgs, texts = [], []
    for it in s['items']:
        imgs.append(load_rgb(os.path.join(d, it['file'])))
        with open(os.path.join(d, it['file'][:-4] + '.txt'), 'r', encoding='utf-8') as f:
            texts.append(f.read().strip())
    return imgs, texts


def remove(sid):
    d = folder(sid)
    if os.path.isdir(d):
        shutil.rmtree(d)


# ---------------------------------------------------------------- workflows

def caption_graph(rid, trigger=TRIGGER):
    return {
        '1': {'class_type': 'EARefImage', 'inputs': {'ref': rid}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': CAPTION_MODEL[1], 'type': 'stable_diffusion', 'device': 'default'}},
        '3': {'class_type': 'TextGenerate', 'inputs': {'clip': ['2', 0], 'prompt': CAPTION_INSTRUCTION, 'image': ['1', 0], 'max_length': 320,
                                                       'sampling_mode': 'off', 'thinking': False, 'use_default_template': True, 'mtp': 'off'}},
        '4': {'class_type': 'EASaveCaption', 'inputs': {'ref': rid, 'text': ['3', 0], 'trigger': trigger}},
    }


def train_graph(s, seed=0):
    F = FAMILIES[s['base']]
    g = {}
    if s['base'] == 'hidream':
        g['1'] = {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': F['files']['ckpt'][1]}}
        g['2'] = {'class_type': 'ModelNoiseScale', 'inputs': {'model': ['1', 0], 'noise_scale': 8.0}}
        model, clip, vae, offload = ['2', 0], ['1', 1], ['1', 2], False
    else:
        g['1'] = {'class_type': 'UNETLoader', 'inputs': {'unet_name': F['files']['unet'][1], 'weight_dtype': 'default'}}
        g['10'] = {'class_type': 'CLIPLoader', 'inputs': {'clip_name': F['files']['clip'][1], 'type': 'qwen_image', 'device': 'default'}}
        g['11'] = {'class_type': 'VAELoader', 'inputs': {'vae_name': F['files']['vae'][1]}}
        g['2'] = {'class_type': 'ModelSamplingAuraFlow', 'inputs': {'model': ['1', 0], 'shift': 3.1}}
        model, clip, vae, offload = ['2', 0], ['10', 0], ['11', 0], True      # 41 GB of weights: stream them from memory
    g['3'] = {'class_type': 'EATrainingImages', 'inputs': {'set': s['id']}}
    g['4'] = {'class_type': 'MakeTrainingDataset', 'inputs': {'images': ['3', 0], 'vae': vae, 'clip': clip, 'texts': ['3', 1]}}
    g['5'] = {'class_type': 'ResolutionBucket', 'inputs': {'latents': ['4', 0], 'conditioning': ['4', 1]}}
    g['6'] = {'class_type': 'TrainLoraNode', 'inputs': {
        'model': model, 'latents': ['5', 0], 'positive': ['5', 1], 'batch_size': 1, 'grad_accumulation_steps': 1,
        'steps': int(s['steps']), 'learning_rate': float(s['learning_rate']), 'rank': int(s['rank']), 'optimizer': 'AdamW',
        'loss_function': 'MSE', 'seed': int(seed), 'training_dtype': 'bf16', 'lora_dtype': 'bf16', 'quantized_backward': False,
        'algorithm': 'LoRA', 'gradient_checkpointing': True, 'checkpoint_depth': 1, 'offloading': offload,
        'existing_lora': '[None]', 'bucket_mode': True, 'bypass_mode': False}}
    g['7'] = {'class_type': 'EASaveLoRA', 'inputs': {'lora': ['6', 0], 'set': s['id'], 'steps': ['6', 2]}}
    g['8'] = {'class_type': 'LossGraphNode', 'inputs': {'loss': ['6', 1], 'filename_prefix': 'ea/loss-' + s['id']}}
    return g
