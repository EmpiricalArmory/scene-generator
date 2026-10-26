"""A job is one request to a model: the pictures it is given, the prompts and the settings.

data/jobs/<id>/      job.json, and the pictures the workflow reads:
                       natural  view1.png... (the product's photos on a plain backdrop), ref1.png... (style)
                       exact    canvas.png (the product on a plain backdrop where it will be), draw.png
                                (where the model may draw: 1 draws, 0 keeps), harmonize.png (how much the
                                relight pass may change), view1.png, ref1.png...
data/results/<day>/  for each picture: <name>.png (final), <name>-parts.png (a parts map for Tuned
                     by part), <name>-raw.png (the model's first picture, before the detail or relight
                     pass), <name>.json (how it was made)
"""
import os
import time

import numpy as np

from . import composite, imaging, models, paths, products, scene
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


def _fit_mp(rgb, megapixels):
    sc = (megapixels * 1024 * 1024 / (rgb.shape[0] * rgb.shape[1])) ** 0.5
    if sc < 1:
        rgb = resize(rgb, rgb.shape[1] * sc, rgb.shape[0] * sc)
    return rgb


def _mode(req, s):
    m = req.get('product_mode') or 'natural'
    if m == 'reference':
        m = 'natural'
    if m == 'relit':
        m = 'exact'
    if s.get('pose') in scene.WORN or m not in scene.MODES:
        m = 'natural'
    return m


def guide_box(fg, alpha, place, fw, fh):
    """Where the product would sit on the frame (fractions), and which way a sword's point would face."""
    sc = min(1.0, 512 / max(fw, fh))
    w, h = max(8, int(fw * sc)), max(8, int(fh * sc))
    L = composite.place_layers(fg, alpha, None, place, w, h)
    x0, y0, x1, y1 = composite.product_box(L['alpha'])
    d = composite.point_direction(alpha)
    if place.get('flip'):
        d = 180.0 - d
    angle = d + float(place.get('rotation', 0.0))
    box = (max(0.0, x0 / w), max(0.0, y0 / h), min(1.0, x1 / w), min(1.0, y1 / h))
    return box, angle


def create(req):
    """Prepare a job from a request:
        product, place {aspect, cx, cy, length, rotation, flip}, scene {...}, family, quality, seed,
        product_mode ('natural' or 'exact'), relight (exact), detail {on, strength} (natural),
        guide (natural: use the frame's placement as a rough guide), upscale ('none' or 'seedvr2'),
        output_long (px), refs [reference ids], prompt?, negative?, style?"""
    p = products.load(req['product'])
    if not p.get('cutout'):
        raise ValueError('The product has no cut-out yet.')
    family = req.get('family', 'qwen')
    if family not in FAMILIES:
        raise ValueError('Unknown model: ' + family)
    F = FAMILIES[family]
    quality = req.get('quality', 'final')
    place = dict(req.get('place') or {})
    aspect = place.get('aspect', '4:5')
    fw, fh = frame_for(family, aspect, quality)
    ow, oh = output_size(aspect, int(req.get('output_long') or 2400))
    s = dict(req.get('scene') or {})
    mode = _mode(req, s)
    jid = new_id('j')
    d = folder(jid)
    os.makedirs(d, exist_ok=True)

    style_ids = [r for r in (req.get('refs') or []) if reference_file(r)]
    max_pics = F['pictures']
    guide = None
    if mode == 'natural':
        views_all = products.reference_files(p['id'])
        style_slots = min(len(style_ids), max(1, max_pics // 3)) if style_ids else 0
        n_views = max(1, min(len(views_all), max_pics - style_slots))
        for i, path in enumerate(views_all[:n_views]):
            save_png(os.path.join(d, f'view{i + 1}.png'), _fit_mp(load_rgb(path), 1.0), compress=3)
        n_style = min(len(style_ids), max_pics - n_views)
        if req.get('guide'):
            _, fg, alpha, _ = products.layers(p['id'])
            box, angle = guide_box(fg, alpha, place, fw, fh)
            guide = {'box': [round(v, 4) for v in box], 'angle': round(angle, 1)}
    else:
        _, fg, alpha, cover = products.layers(p['id'])
        canvas, draw, L = composite.model_inputs(fg, alpha, cover, place, fw, fh, REF_GREY, product_hold=0.0,
                                                 cover_free=float(req.get('cover_free', 1.0)))
        save_png(os.path.join(d, 'canvas.png'), canvas)
        save_png(os.path.join(d, 'draw.png'), draw)
        save_png(os.path.join(d, 'harmonize.png'), harmonize_mask(L, fw, fh))
        save_png(os.path.join(d, 'view1.png'), _fit_mp(load_rgb(products.main_reference(p['id'])), 1.0), compress=3)
        n_views = 1
        n_style = min(len(style_ids), F['max_refs'], max_pics - 1)
    refs = []
    for i, rid in enumerate(style_ids[:n_style]):
        save_png(os.path.join(d, f'ref{i + 1}.png'), _fit_mp(load_rgb(reference_file(rid)), 1.0))
        refs.append(rid)

    layout = None
    if guide:
        layout = scene.layout_phrase(p, guide['box'], guide['angle'], cite='<obj_1>' if family == 'flux3' else '')
    text = req.get('prompt') or scene.prompt(s, p, family, refs=len(refs), mode=mode, views=n_views, layout=layout)
    if guide and family == 'flux3':
        text = scene.flux_layout(text, p, guide['box'], n_views)
    style = req.get('style') or None
    if style and style.get('base') != family:
        style = None                                   # a style is trained for one model only
    if style and style.get('trigger') and style['trigger'].lower() not in text.lower():
        text = style['trigger'] + ', ' + text
    neg = req.get('negative') if req.get('negative') is not None else scene.negative(s)
    seed = int(req.get('seed') if req.get('seed') not in (None, '') else int(time.time() * 1000) % 2**32)

    det = dict(req.get('detail') or {})
    have_sam = models._have(*models.SAM3)
    detail = {
        'on': bool(det.get('on', True)) and mode == 'natural' and have_sam,
        'strength': float(min(0.9, max(0.15, float(det.get('strength', 0.5))))),
        'megapixels': F['detail_mp']['draft' if quality == 'draft' else 'final'],
        'views': max(1, min(n_views, max_pics - 1)),
    }
    detail['prompt'] = scene.detail_prompt(p, detail['views'])
    relight = mode == 'exact' and bool(req.get('relight', True))
    upscale = 'seedvr2' if req.get('upscale') == 'seedvr2' and models.have_helper('seedvr2') else 'none'
    j = {
        'id': jid, 'created': now_iso(), 'product': p['id'], 'product_name': p.get('name'), 'family': family,
        'quality': quality, 'place': place, 'scene': s, 'prompt': text, 'negative': neg, 'seed': seed,
        'frame': [fw, fh], 'output': [ow, oh], 'product_mode': mode, 'views': n_views, 'refs': refs,
        'variations': int(req.get('variations', 1)), 'upsample_prompt': bool(req.get('upsample_prompt')),
        'name': req.get('name') or '', 'batch': req.get('batch') or '', 'results': [],
        'style': style, 'guide': guide, 'detail': detail, 'find': products.find_term(p), 'sam': have_sam,
        'relight': relight, 'harmonize_prompt': scene.harmonize_prompt(s, p) if relight else '',
        'harmonize_strength': float(req.get('relight_strength', 0.4)), 'upscale': upscale,
    }
    write_json(os.path.join(d, 'job.json'), j)
    return j


REF_GREY = products.REF_BACKDROP


def harmonize_mask(L, fw, fh):
    """For the relight pass ("Exact photo"): the product may change fully (within the pass's strength),
    a ring around it for contact shadows a good deal, the rest of the picture only a little."""
    a = L['alpha']
    core = a > 0.5
    r = max(4, int(0.035 * max(fw, fh)))
    ring = imaging.dilate(core, r) & ~core
    m = np.full((fh, fw), 0.25, np.float32)
    m[ring] = 0.6
    m[core] = 1.0
    return imaging.feather(m, max(2.0, 0.008 * max(fw, fh)))


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


def finish(jid, generated, index=0, raw=None, mask=None):
    """Save a finished picture, its parts map and how it was made.

    natural: `generated` is the final picture; `mask` (SAM 3's find on it) makes the parts map.
    exact:   the photo's pixels go back on top of `generated`, with the relit light if relight is on."""
    t0 = time.time()
    j = load(jid)
    ow, oh = j['output']
    gen = np.clip(generated, 0, 1).astype(np.float32)
    parts = None
    if j.get('product_mode') in ('natural', 'reference'):
        p = products.load(j['product'])
        final = gen if gen.shape[:2] == (oh, ow) else np.clip(resize(gen, ow, oh), 0, 1)
        if mask is not None and float(np.max(mask)) > 0.5:
            m = mask.astype(np.float32)
            if m.shape != (oh, ow):
                m = resize(m, ow, oh, resample=2)
            try:
                parts = imaging.refine_alpha(final, m)
            except Exception as e:  # the parts map is a help, not a must
                print('[EA] parts map:', e)
                parts = (m > 0.5).astype(np.float32)
    else:
        p, fg, alpha, cover = _product_layers(j['product'])
        final, L, parts = composite.paste_back(gen, fg, alpha, cover, j['place'], ow, oh,
                                               mode='relit' if j.get('relight') or j.get('product_mode') == 'relit' else 'exact')
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
    save_png(os.path.join(out_dir, name + '-raw.png'), np.clip(raw if raw is not None else gen, 0, 1), compress=3)
    if parts is not None:
        save_png(os.path.join(out_dir, name + '-parts.png'), composite.parts_map(parts))
    th = resize(final, 640, int(640 * oh / ow))
    save_jpg(os.path.join(out_dir, name + '-thumb.jpg'), th, quality=85)
    info = {k: j.get(k) for k in ('id', 'product', 'product_name', 'family', 'quality', 'place', 'scene', 'prompt', 'negative',
                                  'frame', 'output', 'product_mode', 'views', 'refs', 'name', 'batch', 'style', 'guide',
                                  'detail', 'relight', 'upscale', 'find')}
    info['output'] = [int(ow), int(oh)]
    info.update({'job': jid, 'seed': j['seed'] + index, 'variation': index, 'result': name, 'day': day,
                 'finished': now_iso(), 'finish_seconds': round(time.time() - t0, 2), 'found': parts is not None})
    write_json(os.path.join(out_dir, name + '.json'), info)
    rel = f'{day}/{name}'
    j['results'].append(rel)
    write_json(file_path(jid, 'job.json'), j)
    return {'id': rel, 'url': f'/ea/data/results/{rel}.png', 'thumb': f'/ea/data/results/{rel}-thumb.jpg',
            'raw': f'/ea/data/results/{rel}-raw.png', 'parts': f'/ea/data/results/{rel}-parts.png' if parts is not None else None,
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
