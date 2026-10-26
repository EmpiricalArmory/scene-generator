"""Reference pictures: photographs whose look the generated scenes should follow, and the training set.

Each lives in data/references/<id>/ with the picture and reference.json: where it came from, who made it,
its licence, and whether it may be used for training. Only pictures with a recorded right go into training.
"""
import os
import shutil

from . import paths
from .util import inside, load_rgb, new_id, now_iso, read_json, safe_name, thumbnail, write_json

ROOT = os.path.join(paths.DATA, 'references')

RIGHTS = {
    'own': 'My own photograph',
    'cc0': 'Public domain or CC0',
    'cc-by': 'Creative Commons with attribution (CC BY, CC BY-SA)',
    'licensed': 'Licensed for this use (a written permission or a stock licence)',
    'unknown': 'Unknown: not for training or publishing',
}


def folder(rid):
    return inside(ROOT, safe_name(rid))


def all_references():
    if not os.path.isdir(ROOT):
        return []
    out = []
    for d in os.listdir(ROOT):
        r = read_json(os.path.join(ROOT, d, 'reference.json'))
        if r:
            out.append(r)
    out.sort(key=lambda r: r.get('created', ''), reverse=True)
    return out


def add(src, original_name, meta):
    rid = new_id('r')
    d = folder(rid)
    os.makedirs(d, exist_ok=True)
    ext = os.path.splitext(original_name or src)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        ext = '.jpg'
    name = 'picture' + ext
    shutil.copyfile(src, os.path.join(d, name))
    rgb = load_rgb(os.path.join(d, name))
    thumbnail(os.path.join(d, name), os.path.join(d, 'thumb.jpg'), 480)
    rights = meta.get('rights') if meta.get('rights') in RIGHTS else 'unknown'
    r = {
        'id': rid, 'file': name, 'original_name': original_name or '', 'size': [int(rgb.shape[1]), int(rgb.shape[0])],
        'created': now_iso(), 'title': meta.get('title') or os.path.splitext(original_name or 'Reference')[0],
        'creator': meta.get('creator', ''), 'licence': meta.get('licence', ''), 'source': meta.get('source', ''),
        'rights': rights, 'notes': meta.get('notes', ''), 'tags': [t.strip() for t in (meta.get('tags') or '').split(',') if t.strip()],
        'caption': '', 'train': rights in ('own', 'cc0', 'cc-by', 'licensed'),
    }
    write_json(os.path.join(d, 'reference.json'), r)
    return r


def update(rid, body):
    p = os.path.join(folder(rid), 'reference.json')
    r = read_json(p)
    if not r:
        raise KeyError('No such reference: ' + rid)
    for k in ('title', 'creator', 'licence', 'source', 'rights', 'notes', 'tags', 'caption', 'train'):
        if k in body:
            r[k] = body[k]
    if r.get('rights') not in RIGHTS:
        r['rights'] = 'unknown'
    if r['rights'] == 'unknown':
        r['train'] = False
    r['updated'] = now_iso()
    write_json(p, r)
    return r


def remove(rid):
    d = folder(rid)
    if os.path.isdir(d):
        shutil.rmtree(d)
