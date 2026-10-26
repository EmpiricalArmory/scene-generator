"""Product photos and their cut-outs.

Each product lives in data/products/<id>/:
    photo.<ext>     the photo as it came, never changed
    product.json    name, what it is, the cut-out's facts
    mask.png        where the product is (0..255), snapped to the photo's edges
    fg.png          the product's colours with the backdrop taken out of soft edges
    cover.png       optional: parts that hands may cover (the grip of a sword, say)
    thumb.jpg       the cut-out on the cream, for lists
"""
import os
import shutil

import numpy as np

from . import composite, imaging, paths
from .util import (inside, load_alpha_if_any, load_gray, load_rgb, new_id, now_iso, read_json, resize,
                   safe_name, save_jpg, save_png, write_json)

ROOT = os.path.join(paths.DATA, 'products')
CREAM = np.array([230, 223, 207], np.float32) / 255

KINDS = {
    'instrument': 'a sword or trainer',
    'gloves': 'gloves',
    'mask': 'a fencing mask',
    'jacket': 'a jacket',
    'other': 'other gear',
}


def folder(pid):
    return inside(ROOT, safe_name(pid))


def file(pid, name):
    return inside(folder(pid), name)


def load(pid):
    p = read_json(file(pid, 'product.json'))
    if not p:
        raise KeyError('No such product: ' + str(pid))
    return p


def save(p):
    p['updated'] = now_iso()
    write_json(file(p['id'], 'product.json'), p)
    return p


def all_products():
    if not os.path.isdir(ROOT):
        return []
    out = []
    for d in sorted(os.listdir(ROOT)):
        p = read_json(os.path.join(ROOT, d, 'product.json'))
        if p:
            out.append(p)
    out.sort(key=lambda p: p.get('created', ''), reverse=True)
    return out


def create(src_path, name, kind='other', noun='', credit=None, original_name=''):
    pid = new_id('p')
    d = folder(pid)
    os.makedirs(d, exist_ok=True)
    ext = os.path.splitext(original_name or src_path)[1].lower() or '.jpg'
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff'):
        ext = '.jpg'
    photo = 'photo' + ext
    shutil.copyfile(src_path, os.path.join(d, photo))
    rgb = load_rgb(os.path.join(d, photo))
    p = {
        'id': pid, 'name': name or os.path.splitext(original_name or 'Product')[0], 'kind': kind if kind in KINDS else 'other',
        'noun': noun or '', 'photo': photo, 'size': [int(rgb.shape[1]), int(rgb.shape[0])],
        'created': now_iso(), 'cutout': None, 'cover': False, 'credit': credit or None,
    }
    save(p)
    return p


def remove(pid):
    d = folder(pid)
    if os.path.isdir(d):
        shutil.rmtree(d)


# ---------------------------------------------------------------- the cut-out

_BG_MODEL = {}


def _bg_model_file(prefer=None):
    import folder_paths
    files = folder_paths.get_filename_list('background_removal')
    for want in ([prefer] if prefer else []) + ['birefnet.safetensors', 'lucida.safetensors']:
        if want in files:
            return want
    return files[0] if files else None


def model_mask(rgb, model_name=None):
    """Foreground probability from a background-removal model (BiRefNet or Lucida), or None."""
    import torch
    import folder_paths
    from comfy.bg_removal_model import load as load_bg
    name = _bg_model_file(model_name)
    if not name:
        return None
    if name not in _BG_MODEL:
        _BG_MODEL.clear()
        _BG_MODEL[name] = load_bg(folder_paths.get_full_path_or_raise('background_removal', name))
    m = _BG_MODEL[name]
    h, w = rgb.shape[:2]
    # the model looks at 1024 x 1024; give it a copy no bigger than 2048 on the long side to resize from
    s = min(1.0, 2048 / max(h, w))
    small = resize(rgb, w * s, h * s) if s < 1 else rgb
    with torch.no_grad():
        out = m.encode_image(torch.from_numpy(np.ascontiguousarray(small, np.float32))[None])
    prob = out[0].float().cpu().numpy()
    if prob.shape != (h, w):
        prob = resize(prob, w, h, resample=3)    # bicubic up to the photo's size
    return np.clip(prob, 0, 1)


def cut_out(pid, method='auto', mask=None):
    """Find the product in its photo and save mask.png, fg.png and thumb.jpg.

    method: 'auto' (the photo's own transparency if it has one, else the model, else the backdrop method),
    'model', 'white backdrop', or 'mask' (a mask drawn or uploaded by hand)."""
    p = load(pid)
    src = file(pid, p['photo'])
    rgb = load_rgb(src)
    h, w = rgb.shape[:2]
    used = None
    coarse = None
    if mask is not None:
        coarse = mask if mask.shape == (h, w) else resize(mask.astype(np.float32), w, h, resample=2)
        used = 'mask'
    if coarse is None and method == 'auto':
        own = load_alpha_if_any(src)
        if own is not None:
            coarse, used = own, 'own transparency'
    if coarse is None and method in ('auto', 'model'):
        try:
            coarse = model_mask(rgb)
            used = 'model' if coarse is not None else None
        except Exception as e:  # a missing or broken model falls back to the backdrop method
            print('[EA] cut-out model failed:', e)
            coarse = None
    if coarse is None:
        coarse, used = imaging.white_sweep_alpha(rgb), 'white backdrop'
    save_png(file(pid, 'coarse.png'), coarse)
    alpha = coarse.astype(np.float32) if used == 'own transparency' else imaging.refine_alpha(rgb, coarse)
    return _store_cutout(p, rgb, alpha, used)


def set_mask(pid, mask, refine=True):
    """A mask edited by hand: snapped to the photo's edges unless refine is off."""
    p = load(pid)
    rgb = load_rgb(file(pid, p['photo']))
    h, w = rgb.shape[:2]
    if mask.shape != (h, w):
        mask = resize(mask.astype(np.float32), w, h, resample=2)
    alpha = imaging.refine_alpha(rgb, mask) if refine else np.clip(mask, 0, 1).astype(np.float32)
    return _store_cutout(p, rgb, alpha, 'edited')


def _store_cutout(p, rgb, alpha, used):
    pid = p['id']
    bg = imaging.background_field(rgb, alpha)
    fg = imaging.decontaminate(rgb, alpha, bg)
    save_png(file(pid, 'mask.png'), alpha)
    save_png(file(pid, 'fg.png'), fg, compress=3)
    backdrop = np.median(rgb[alpha < 0.02], axis=0) if (alpha < 0.02).any() else np.array([0.9, 0.9, 0.9])
    box = composite.product_box(alpha)
    p['cutout'] = {
        'method': used, 'at': now_iso(), 'box': list(box), 'open_edges': composite.open_edges(alpha),
        'axis_deg': round(composite.long_axis_angle(alpha), 1), 'coverage': round(float((alpha > 0.5).mean()), 4),
    }
    p['backdrop'] = [round(float(c), 4) for c in backdrop]
    if p.get('kind') == 'instrument' and not p.get('cover'):
        try:
            cover = composite.suggest_cover(alpha)
            if cover.max() > 0:
                save_png(file(pid, 'cover.png'), cover)
                p['cover'] = True
                p['cover_source'] = 'suggested'
        except Exception as e:
            print('[EA] could not suggest the handle:', e)
    save(p)
    _thumb(p, fg, alpha)
    previews(pid, rgb=rgb, fg=fg, alpha=alpha)
    return {'product': pid, 'method': used, 'box': list(box)}


def _thumb(p, fg, alpha, size=480):
    x0, y0, x1, y1 = composite.product_box(alpha)
    m = int(0.06 * max(x1 - x0, y1 - y0)) + 2
    h, w = alpha.shape
    x0, y0, x1, y1 = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
    crop = fg[y0:y1, x0:x1]; a = alpha[y0:y1, x0:x1]
    s = size / max(crop.shape[:2])
    tw, th = max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))
    crop = resize(crop, tw, th); a = resize(a, tw, th)
    out = np.ones((size, size, 3), np.float32) * CREAM
    ox, oy = (size - tw) // 2, (size - th) // 2
    region = out[oy:oy + th, ox:ox + tw]
    out[oy:oy + th, ox:ox + tw] = region * (1 - a[..., None]) + crop * a[..., None]
    save_jpg(file(p['id'], 'thumb.jpg'), out, quality=86)


def set_cover(pid, cover):
    p = load(pid)
    w, h = p['size']
    if cover is None or float(np.max(cover)) <= 0:
        path = file(pid, 'cover.png')
        if os.path.exists(path):
            os.remove(path)
        p['cover'] = False
    else:
        if cover.shape != (h, w):
            cover = resize(cover.astype(np.float32), w, h, resample=2)
        save_png(file(pid, 'cover.png'), np.clip(cover, 0, 1))
        p['cover'] = True
        p['cover_source'] = 'edited'
    save(p)
    previews(pid)
    return load(pid)


def previews(pid, rgb=None, fg=None, alpha=None):
    """Smaller copies for the page: the cut-out for placing (preview.png, RGBA), the handle for showing
    (cover_preview.png), and the photo with its masks for editing (edit.jpg, mask_edit.png, cover_edit.png)."""
    p = load(pid)
    if rgb is None:
        rgb = load_rgb(file(pid, p['photo']))
    if fg is None:
        fg = load_rgb(file(pid, 'fg.png'))
    if alpha is None:
        alpha = load_gray(file(pid, 'mask.png'))
    cpath = file(pid, 'cover.png')
    cover = load_gray(cpath) if p.get('cover') and os.path.exists(cpath) else None
    h, w = alpha.shape
    x0, y0, x1, y1 = composite.product_box(alpha)
    m = int(0.03 * max(x1 - x0, y1 - y0)) + 4
    x0, y0, x1, y1 = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
    s = min(1.0, 1600 / max(x1 - x0, y1 - y0))
    tw, th = max(1, round((x1 - x0) * s)), max(1, round((y1 - y0) * s))
    rgba = np.concatenate([resize(fg[y0:y1, x0:x1], tw, th), resize(alpha[y0:y1, x0:x1], tw, th)[..., None]], axis=2)
    save_png(file(pid, 'preview.png'), np.clip(rgba, 0, 1))
    if cover is not None:
        save_png(file(pid, 'cover_preview.png'), np.clip(resize(cover[y0:y1, x0:x1], tw, th), 0, 1))
    es = min(1.0, 2048 / max(w, h))
    ew, eh = max(1, round(w * es)), max(1, round(h * es))
    save_jpg(file(pid, 'edit.jpg'), resize(rgb, ew, eh), quality=90)
    save_png(file(pid, 'mask_edit.png'), np.clip(resize(alpha, ew, eh), 0, 1))
    if cover is not None:
        save_png(file(pid, 'cover_edit.png'), np.clip(resize(cover, ew, eh), 0, 1))
    p['preview'] = {'box': [int(x0), int(y0), int(x1), int(y1)], 'size': [tw, th]}
    p['edit'] = {'size': [ew, eh]}
    p['rev'] = int(p.get('rev', 0)) + 1
    save(p)


def layers(pid):
    """The product's colours, alpha and cover mask, for placing it on a frame."""
    p = load(pid)
    if not p.get('cutout'):
        raise ValueError('The product has no cut-out yet.')
    fg = load_rgb(file(pid, 'fg.png'))
    alpha = load_gray(file(pid, 'mask.png'))
    cover = load_gray(file(pid, 'cover.png')) if p.get('cover') and os.path.exists(file(pid, 'cover.png')) else None
    return p, fg, alpha, cover
