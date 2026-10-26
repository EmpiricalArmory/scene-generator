"""Product photos and their cut-outs.

Each product lives in data/products/<id>/:
    photo.<ext>     the main photo as it came, never changed
    product.json    name, what it is, what it's made of, its other photos, the cut-out's facts
    mask.png        where the product is (0..255), snapped to the photo's edges
    fg.png          the product's colours with the backdrop taken out of soft edges
    ref.png         the product on a plain backdrop, cropped to it: what the models look at
    cover.png       optional: parts that hands may cover (the grip of a sword, say)
    thumb.jpg       the cut-out on the cream, for lists
    views/<vid>/    more photos of the same product (other sides, details), or views a model made
                    from a photo: photo.<ext>, mask.png, fg.png, ref.png, thumb.jpg

The models draw the product from every ref.png that is ticked for use: more sides seen means a
truer product at a new angle.
"""
import os
import shutil

import numpy as np

from . import composite, imaging, paths
from .util import (inside, load_alpha_if_any, load_gray, load_rgb, new_id, now_iso, read_json, resize,
                   safe_name, save_jpg, save_png, write_json)

ROOT = os.path.join(paths.DATA, 'products')
CREAM = np.array([230, 223, 207], np.float32) / 255
REF_BACKDROP = np.array([0.93, 0.93, 0.92], np.float32)      # a plain light grey for the models' pictures
MAX_VIEWS = 8

KINDS = {
    'instrument': 'a sword or trainer',
    'gloves': 'gloves',
    'mask': 'a fencing mask',
    'jacket': 'a jacket',
    'other': 'other gear',
}

# What SAM 3 looks for in a generated picture to find the product (":2" finds up to two).
FIND = {'instrument': 'sword', 'gloves': 'glove:2', 'mask': 'fencing mask', 'jacket': 'jacket'}


def folder(pid):
    return inside(ROOT, safe_name(pid))


def file(pid, name):
    return inside(folder(pid), name)


def view_folder(pid, vid):
    return inside(folder(pid), 'views', safe_name(vid))


def load(pid):
    p = read_json(file(pid, 'product.json'))
    if not p:
        raise KeyError('No such product: ' + str(pid))
    p.setdefault('views', [])
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
            p.setdefault('views', [])
            out.append(p)
    out.sort(key=lambda p: p.get('created', ''), reverse=True)
    return out


def _photo_name(src_path, original_name):
    ext = os.path.splitext(original_name or src_path)[1].lower() or '.jpg'
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff'):
        ext = '.jpg'
    return 'photo' + ext


def create(src_path, name, kind='other', noun='', credit=None, original_name=''):
    rgb = load_rgb(src_path)                       # read it before anything is saved
    pid = new_id('p')
    d = folder(pid)
    os.makedirs(d, exist_ok=True)
    photo = _photo_name(src_path, original_name)
    shutil.copyfile(src_path, os.path.join(d, photo))
    p = {
        'id': pid, 'name': name or os.path.splitext(original_name or 'Product')[0], 'kind': kind if kind in KINDS else 'other',
        'noun': noun or '', 'materials': '', 'find': '', 'photo': photo, 'size': [int(rgb.shape[1]), int(rgb.shape[0])],
        'created': now_iso(), 'cutout': None, 'cover': False, 'credit': credit or None, 'views': [],
    }
    save(p)
    return p


def remove(pid):
    d = folder(pid)
    if os.path.isdir(d):
        shutil.rmtree(d)


def find_term(p):
    """The words SAM 3 looks for to find the product in a picture."""
    t = (p.get('find') or '').strip()
    if not t:
        t = FIND.get(p.get('kind'))
    if not t:
        n = (p.get('noun') or 'product').strip().lower()
        for a in ('a pair of ', 'pair of ', 'a ', 'an ', 'the '):
            if n.startswith(a):
                n = n[len(a):]
        t = n
    return ' '.join(t.replace(',', ' ').replace('(', ' ').replace(')', ' ').split()) or 'product'


# ---------------------------------------------------------------- cut-outs

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


def _find_alpha(src, rgb, method='auto', mask=None):
    """The product's alpha in a photo, and how it was found.

    method: 'auto' (the photo's own transparency if it has one, else the model, else the backdrop
    method), 'model', 'white backdrop', or a mask drawn or uploaded by hand."""
    h, w = rgb.shape[:2]
    coarse, used = None, None
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
    alpha = coarse.astype(np.float32) if used == 'own transparency' else imaging.refine_alpha(rgb, coarse)
    return coarse, alpha, used


def cut_out(pid, method='auto', mask=None):
    """Find the product in its main photo and save mask.png, fg.png, ref.png and thumb.jpg."""
    p = load(pid)
    src = file(pid, p['photo'])
    rgb = load_rgb(src)
    coarse, alpha, used = _find_alpha(src, rgb, method, mask)
    save_png(file(pid, 'coarse.png'), coarse)
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
    save_png(file(pid, 'ref.png'), reference_picture(fg, alpha), compress=3)
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
    _thumb(file(pid, 'thumb.jpg'), fg, alpha)
    previews(pid, rgb=rgb, fg=fg, alpha=alpha)
    return {'product': pid, 'method': used, 'box': list(box)}


def reference_picture(fg, alpha, megapixels=1.5, backdrop=REF_BACKDROP):
    """The product alone on a plain light backdrop, cropped to it with a margin, at most `megapixels`:
    the picture a model draws the product from."""
    x0, y0, x1, y1 = composite.product_box(alpha)
    h, w = alpha.shape
    m = int(0.06 * max(x1 - x0, y1 - y0)) + 8
    x0, y0, x1, y1 = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
    a = alpha[y0:y1, x0:x1, None]
    pic = backdrop[None, None, :] * (1 - a) + fg[y0:y1, x0:x1] * a
    sc = min(1.0, (megapixels * 1024 * 1024 / (pic.shape[0] * pic.shape[1])) ** 0.5)
    if sc < 1:
        pic = resize(pic, pic.shape[1] * sc, pic.shape[0] * sc)
    return np.clip(pic, 0, 1).astype(np.float32)


def _thumb(path, fg, alpha, size=480):
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
    save_jpg(path, out, quality=86)


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


# ---------------------------------------------------------------- more photos of the product

def _view(p, vid):
    for v in p.get('views', []):
        if v['id'] == vid:
            return v
    raise KeyError('No such photo of this product: ' + str(vid))


def add_view(pid, src_path, original_name='', made='photo', label='', source=None):
    """Another photo of the same product (another side, a detail), or a view a model made from one."""
    p = load(pid)
    if len(p['views']) >= MAX_VIEWS:
        raise ValueError(f'A product can have up to {MAX_VIEWS + 1} photos. Remove one first.')
    try:
        rgb = load_rgb(src_path)                   # read it before anything is saved
    except Exception:
        raise ValueError('That file could not be read as a picture.')
    vid = new_id('v')
    d = view_folder(pid, vid)
    os.makedirs(d, exist_ok=True)
    photo = _photo_name(src_path, original_name)
    shutil.copyfile(src_path, os.path.join(d, photo))
    v = {'id': vid, 'photo': photo, 'made': made if made in ('photo', 'model') else 'photo', 'label': label or '',
         'use': True, 'size': [int(rgb.shape[1]), int(rgb.shape[0])], 'created': now_iso(), 'cutout': None,
         'source': source, 'rev': 0}
    p['views'].append(v)
    save(p)
    return v


def add_view_array(pid, rgb, label='', source=None):
    """A view a model made (an array), saved as a PNG photo and cut out."""
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        save_png(tmp, np.clip(rgb, 0, 1), compress=3)
        v = add_view(pid, tmp, 'view.png', made='model', label=label, source=source)
    finally:
        os.remove(tmp)
    cut_out_view(pid, v['id'], 'auto')
    return _view(load(pid), v['id'])


def cut_out_view(pid, vid, method='auto', mask=None):
    p = load(pid)
    v = _view(p, vid)
    d = view_folder(pid, vid)
    src = os.path.join(d, v['photo'])
    rgb = load_rgb(src)
    coarse, alpha, used = _find_alpha(src, rgb, method, mask)
    bg = imaging.background_field(rgb, alpha)
    fg = imaging.decontaminate(rgb, alpha, bg)
    save_png(os.path.join(d, 'mask.png'), alpha)
    save_png(os.path.join(d, 'fg.png'), fg, compress=3)
    save_png(os.path.join(d, 'ref.png'), reference_picture(fg, alpha), compress=3)
    _thumb(os.path.join(d, 'thumb.jpg'), fg, alpha, size=320)
    p = load(pid)
    v = _view(p, vid)
    edges = composite.open_edges(alpha)
    v['cutout'] = {'method': used, 'at': now_iso(), 'box': list(composite.product_box(alpha)), 'open_edges': edges}
    if not v.get('shows_set'):
        v['shows'] = 'detail' if edges else 'whole'      # a photo that cuts the product off is a close-up
    v['rev'] = int(v.get('rev', 0)) + 1
    save(p)
    return {'product': pid, 'view': vid, 'method': used}


def update_view(pid, vid, body):
    p = load(pid)
    v = _view(p, vid)
    if 'label' in body:
        v['label'] = str(body['label'] or '')[:80]
    if 'use' in body:
        v['use'] = bool(body['use'])
    if body.get('shows') in ('whole', 'detail'):
        v['shows'] = body['shows']
        v['shows_set'] = True
    save(p)
    return p


def remove_view(pid, vid):
    p = load(pid)
    _view(p, vid)
    p['views'] = [v for v in p['views'] if v['id'] != vid]
    save(p)
    d = view_folder(pid, vid)
    if os.path.isdir(d):
        shutil.rmtree(d)
    return p


def main_reference(pid):
    """ref.png for the main photo, made now for products cut out before it existed."""
    path = file(pid, 'ref.png')
    if not os.path.exists(path):
        p, fg, alpha, cover = layers(pid)
        save_png(path, reference_picture(fg, alpha), compress=3)
    return path


def reference_set(pid):
    """The product's pictures for a model, as (path, shows): the main photo first, then the other photos
    ticked for use that show the whole product, then the close-ups."""
    p = load(pid)
    main_shows = 'detail' if (p.get('cutout') or {}).get('open_edges') else 'whole'
    whole, detail = [(main_reference(pid), main_shows)], []
    changed = False
    for v in p.get('views', []):
        if v.get('cutout') and not v.get('shows'):          # cut out before views knew what they show
            mpath = os.path.join(view_folder(pid, v['id']), 'mask.png')
            if os.path.exists(mpath):
                edges = composite.open_edges(load_gray(mpath))
                v['cutout']['open_edges'] = edges
                v['shows'] = 'detail' if edges else 'whole'
                changed = True
    if changed:
        save(p)
    for v in p.get('views', []):
        if v.get('use', True) and v.get('cutout'):
            path = os.path.join(view_folder(pid, v['id']), 'ref.png')
            if os.path.exists(path):
                (detail if v.get('shows') == 'detail' else whole).append((path, v.get('shows') or 'whole'))
    return whole + detail


def reference_files(pid, limit=None):
    out = [path for path, _ in reference_set(pid)]
    return out[:limit] if limit else out


HILT = {'instrument': 'sword hilt'}       # a closer look in the detail pass, by kind


def hilt_term(p):
    return HILT.get(p.get('kind'))
