"""Small helpers: JSON files, ids, and reading and writing images as float arrays."""
import json
import os
import re
import tempfile
import time
import uuid

import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 400_000_000


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def new_id(prefix=''):
    return prefix + time.strftime('%y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:5]


def safe_name(s, fallback='item'):
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', str(s or '')).strip('-.')
    return (s or fallback)[:60]


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def inside(base, *parts):
    """Join parts under base, refusing anything that would escape it."""
    full = os.path.normpath(os.path.join(base, *parts))
    base = os.path.normpath(base)
    if full != base and not full.startswith(base + os.sep):
        raise ValueError('path outside its folder')
    return full


# ---------------------------------------------------------------- images as float32 arrays in 0..1

def open_image(path):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    return im


def load_rgb(path):
    im = open_image(path)
    if im.mode in ('I;16', 'I;16B', 'I'):
        a = np.asarray(im, dtype=np.float32) / 65535.0
        return np.repeat(a[..., None], 3, axis=2)
    if im.mode == 'RGBA' or (im.mode == 'P' and 'transparency' in im.info) or im.mode == 'LA':
        im = im.convert('RGBA')
        a = np.asarray(im, dtype=np.float32) / 255.0
        return a[..., :3].copy()
    return np.asarray(im.convert('RGB'), dtype=np.float32) / 255.0


def load_alpha_if_any(path):
    """The photo's own alpha channel, if it has a real one (a cut-out PNG)."""
    im = open_image(path)
    if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
        a = np.asarray(im.convert('RGBA'), dtype=np.float32)[..., 3] / 255.0
        if a.min() < 0.99:
            return a
    return None


def load_gray(path):
    im = open_image(path)
    if im.mode in ('RGBA', 'LA'):
        im = im.convert('RGBA')
        a = np.asarray(im, dtype=np.float32)
        # a mask saved with transparency: use alpha where it varies, else luminance
        if a[..., 3].min() < 255:
            return a[..., 3] / 255.0
    if im.mode in ('I;16', 'I;16B', 'I'):
        return np.asarray(im, dtype=np.float32) / 65535.0
    return np.asarray(im.convert('L'), dtype=np.float32) / 255.0


def to_u8(a):
    return (np.clip(a, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def save_png(path, a, compress=4):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if a.ndim == 2:
        im = Image.fromarray(to_u8(a), 'L')
    elif a.shape[2] == 4:
        im = Image.fromarray(to_u8(a), 'RGBA')
    else:
        im = Image.fromarray(to_u8(a), 'RGB')
    im.save(path, compress_level=compress)
    return path


def save_jpg(path, a, quality=92):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(to_u8(a[..., :3]), 'RGB').save(path, quality=quality, subsampling=0, optimize=True)
    return path


def resize(a, w, h, resample=Image.LANCZOS):
    """Resize a float image (H, W) or (H, W, C) with PIL, per channel in float mode."""
    w, h = int(round(w)), int(round(h))
    if a.shape[1] == w and a.shape[0] == h:
        return a.copy()
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), 'F').resize((w, h), resample), dtype=np.float32)
    return np.stack([np.asarray(Image.fromarray(a[..., c].astype(np.float32), 'F').resize((w, h), resample), dtype=np.float32)
                     for c in range(a.shape[2])], axis=2)


def thumbnail(src, dst, size=480, bg=(230, 223, 207)):
    im = open_image(src)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        base = Image.new('RGB', im.size, bg)
        base.paste(im, mask=im.split()[3])
        im = base
    else:
        im = im.convert('RGB')
    im.thumbnail((size, size), Image.LANCZOS)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.save(dst, quality=86)
    return dst
