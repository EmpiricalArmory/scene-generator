"""A job is one request to a model: the product placed on its frame, the masks, the prompt and settings.

data/jobs/<id>/      job.json, canvas.png (the product on a plain backdrop), draw.png (where the
                     model may draw: 1 draws, 0 keeps), ref1.png... (style references)
data/results/<day>/  for each picture: <name>.png (final), <name>-parts.png (a parts map for Tuned
                     by part), <name>-raw.png (the model's own picture), <name>.json (how it was made)
"""
import os
import time

import numpy as np

from . import composite, paths, products, scene
from .models import FAMILIES
from .util import (inside, load_rgb, new_id, now_iso, read_json, resize, safe_name, save_jpg, save_png,
                   write_json)

JOBS = os.path.join(paths.DATA, 'jobs')
RESULTS = os.path.join(paths.DATA, 'results')
REFS = os.path.join(paths.DATA, 'references')


def folder(jid):
    return inside(JOBS, safe_name(jid))


def file_path(jid, name):
    return inside(folder(jid), name)


def load(jid):
    j = read_json(file_path(jid, 'job.json'))
    if not j:
        raise KeyError('No such job: ' + str(jid))
    return j


def frame_for(family, aspect, quality):
    f = FAMILIES[family]
    if f.get('sizes'):
        return composite.frame_size(aspect, 4.0, allowed=f['sizes'])
    mp = f['megapixels']['draft' if quality == 'draft' else 'final']
    return composite.frame_size(aspect, mp, multiple=32)


def output_size(aspect, long_side):
    aw, ah = composite.ASPECTS.get(aspect, (1, 1))
    if aw >= ah:
        return int(long_side), int(round(long_side * ah / aw))
    return int(round(long_side * aw / ah)), int(long_side)


def create(req):
    """Prepare a job from a request:
        product, place {aspect, cx, cy, length, rotation, flip}, scene {...}, family, quality,
        seed, product_mode ('exact' or 'relit'), output_long (px), refs [reference ids], prompt?, negative?"""
    p, fg, alpha, cover = products.layers(req['product'])
    family = req.get('family', 'qwen')
    if family not in FAMILIES:
        raise ValueError('Unknown model: ' + family)
    quality = req.get('quality', 'final')
    place = dict(req.get('place') or {})
    aspect = place.get('aspect', '4:5')
    fw, fh = frame_for(family, aspect, quality)
    ow, oh = output_size(aspect, int(req.get('output_long') or 2400))
    s = dict(req.get('scene') or {})
    worn = s.get('pose') in scene.WORN or req.get('product_mode') == 'reference'
    mode = 'reference' if worn else req.get('product_mode', 'exact')
    if mode not in ('exact', 'relit', 'reference'):
        mode = 'exact'
    backdrop = np.array(p.get('backdrop') or [0.9, 0.9, 0.9], np.float32)
    jid = new_id('j')
    d = folder(jid)
    os.makedirs(d, exist_ok=True)
    if mode == 'reference':
        # the model draws the product from this picture: the cut-out on its backdrop, cropped to it
        save_png(os.path.join(d, 'product.png'), product_picture(fg, alpha, backdrop))
        ow, oh = fw, fh
    else:
        hold = 0.0 if mode == 'exact' else 0.35
        canvas, draw, L = composite.model_inputs(fg, alpha, cover, place, fw, fh, backdrop, product_hold=hold,
                                                 cover_free=float(req.get('cover_free', 1.0)))
        save_png(os.path.join(d, 'canvas.png'), canvas)
        save_png(os.path.join(d, 'draw.png'), draw)
    refs = []
    for i, rid in enumerate((req.get('refs') or [])[:FAMILIES[family]['max_refs']]):
        rp = reference_file(rid)
        if rp:
            r = load_rgb(rp)
            sc = (1024 * 1024 / (r.shape[0] * r.shape[1])) ** 0.5
            if sc < 1:
                r = resize(r, r.shape[1] * sc, r.shape[0] * sc)
            save_png(os.path.join(d, f'ref{i + 1}.png'), r)
            refs.append(rid)
    text = req.get('prompt') or scene.prompt(s, p, family, refs=len(refs))
    style = req.get('style') or None
    if style and style.get('base') != family:
        style = None                                   # a style is trained for one model only
    if style and style.get('trigger') and style['trigger'].lower() not in text.lower():
        text = style['trigger'] + ', ' + text
    neg = req.get('negative') if req.get('negative') is not None else scene.negative(s)
    seed = int(req.get('seed') if req.get('seed') not in (None, '') else int(time.time() * 1000) % 2**32)
    j = {
        'id': jid, 'created': now_iso(), 'product': p['id'], 'product_name': p.get('name'), 'family': family,
        'quality': quality, 'place': place, 'scene': s, 'prompt': text, 'negative': neg, 'seed': seed,
        'frame': [fw, fh], 'output': [ow, oh], 'product_mode': mode, 'refs': refs,
        'variations': int(req.get('variations', 1)), 'upsample_prompt': bool(req.get('upsample_prompt')),
        'name': req.get('name') or '', 'batch': req.get('batch') or '', 'results': [],
        'style': style,
    }
    write_json(os.path.join(d, 'job.json'), j)
    return j


def product_picture(fg, alpha, backdrop, megapixels=2.0):
    """The product cut out on a plain backdrop, cropped to it with a margin, at most `megapixels`."""
    x0, y0, x1, y1 = composite.product_box(alpha)
    h, w = alpha.shape
    m = int(0.06 * max(x1 - x0, y1 - y0)) + 8
    x0, y0, x1, y1 = max(0, x0 - m), max(0, y0 - m), min(w, x1 + m), min(h, y1 + m)
    a = alpha[y0:y1, x0:x1, None]
    pic = backdrop[None, None, :] * (1 - a) + fg[y0:y1, x0:x1] * a
    sc = min(1.0, (megapixels * 1024 * 1024 / (pic.shape[0] * pic.shape[1])) ** 0.5)
    if sc < 1:
        pic = resize(pic, pic.shape[1] * sc, pic.shape[0] * sc)
    return np.clip(pic, 0, 1)


def reference_file(rid):
    meta = read_json(inside(REFS, safe_name(rid), 'reference.json'))
    if not meta:
        return None
    return inside(REFS, safe_name(rid), meta['file'])


_CACHE = {}


def _product_layers(pid):
    key = (pid, os.path.getmtime(products.file(pid, 'product.json')))
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = products.layers(pid)
    return _CACHE[key]


def finish(jid, generated, index=0):
    """Paste the product back on a generated picture and save the result files."""
    t0 = time.time()
    j = load(jid)
    ow, oh = j['output']
    if j.get('product_mode') == 'reference':
        p = products.load(j['product'])
        final, paste = np.clip(generated, 0, 1), None
        oh, ow = final.shape[:2]
    else:
        p, fg, alpha, cover = _product_layers(j['product'])
        final, L, paste = composite.paste_back(generated, fg, alpha, cover, j['place'], ow, oh,
                                               mode='relit' if j.get('product_mode') == 'relit' else 'exact')
    day = time.strftime('%Y-%m-%d')
    preset = j['scene'].get('preset') or j['scene'].get('pose') or 'scene'
    base = '-'.join(x for x in [safe_name(p.get('name'), 'product').lower(), safe_name(preset), j['family'], str(j['seed'] + index)] if x)
    out_dir = inside(RESULTS, day)
    os.makedirs(out_dir, exist_ok=True)
    name = base
    n = 2
    while os.path.exists(os.path.join(out_dir, name + '.png')):
        name = f'{base}-{n}'; n += 1
    save_png(os.path.join(out_dir, name + '.png'), final, compress=3)
    save_png(os.path.join(out_dir, name + '-raw.png'), np.clip(generated, 0, 1), compress=3)
    if paste is not None:
        save_png(os.path.join(out_dir, name + '-parts.png'), composite.parts_map(paste))
    th = resize(final, 640, int(640 * oh / ow))
    save_jpg(os.path.join(out_dir, name + '-thumb.jpg'), th, quality=85)
    info = {k: j.get(k) for k in ('id', 'product', 'product_name', 'family', 'quality', 'place', 'scene', 'prompt', 'negative',
                                  'frame', 'output', 'product_mode', 'refs', 'name', 'batch', 'style')}
    info['output'] = [int(ow), int(oh)]
    info.update({'job': jid, 'seed': j['seed'] + index, 'variation': index, 'result': name, 'day': day,
                 'finished': now_iso(), 'paste_seconds': round(time.time() - t0, 2)})
    write_json(os.path.join(out_dir, name + '.json'), info)
    rel = f'{day}/{name}'
    j['results'].append(rel)
    write_json(file_path(jid, 'job.json'), j)
    return {'id': rel, 'url': f'/ea/data/results/{rel}.png', 'thumb': f'/ea/data/results/{rel}-thumb.jpg',
            'raw': f'/ea/data/results/{rel}-raw.png', 'parts': f'/ea/data/results/{rel}-parts.png' if paste is not None else None,
            'family': j['family'], 'seed': j['seed'] + index, 'batch': j.get('batch', '')}


def list_results(limit=500, batch=None):
    out = []
    if not os.path.isdir(RESULTS):
        return out
    for day in sorted(os.listdir(RESULTS), reverse=True):
        dd = os.path.join(RESULTS, day)
        if not os.path.isdir(dd):
            continue
        for f in sorted(os.listdir(dd), reverse=True):
            if not f.endswith('.json'):
                continue
            info = read_json(os.path.join(dd, f))
            if not info or (batch and info.get('batch') != batch):
                continue
            rel = f'{day}/{f[:-5]}'
            info['urls'] = {'final': f'/ea/data/results/{rel}.png', 'thumb': f'/ea/data/results/{rel}-thumb.jpg',
                            'raw': f'/ea/data/results/{rel}-raw.png',
                            'parts': f'/ea/data/results/{rel}-parts.png' if os.path.exists(os.path.join(dd, f[:-5] + '-parts.png')) else None}
            info['rid'] = rel
            out.append(info)
            if len(out) >= limit:
                return out
    out.sort(key=lambda r: r.get('finished', ''), reverse=True)
    return out
