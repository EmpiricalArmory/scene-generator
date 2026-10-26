"""Reference pictures: photographs whose look the generated scenes should follow, and the training set.

Each lives in data/references/<id>/ with the picture and reference.json: where it came from, who made it,
its licence, and whether it may be used for training. Only pictures with a recorded right go into training.
"""
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request

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


# ---------------------------------------------------------------- finding openly licensed pictures (Openverse)

UA = 'EmpiricalArmory-SceneGenerator/0.2 (https://github.com/EmpiricalArmory/scene-generator)'
OPEN_LICENCES = 'by,by-sa,cc0,pdm'          # commercial use and changes allowed; no NC or ND
LICENCE_NAMES = {'by': 'CC BY', 'by-sa': 'CC BY-SA', 'cc0': 'CC0', 'pdm': 'Public domain'}


def search_open(q, page=1):
    url = 'https://api.openverse.org/v1/images/?' + urllib.parse.urlencode(
        {'q': q, 'license': OPEN_LICENCES, 'page_size': 20, 'page': max(1, int(page)), 'mature': 'false'})
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    out = []
    for x in d.get('results', []):
        lic = (x.get('license') or '').lower()
        out.append({
            'id': x.get('id'), 'title': x.get('title') or '', 'url': x.get('url'), 'thumb': x.get('thumbnail'),
            'creator': x.get('creator') or '', 'licence': (LICENCE_NAMES.get(lic, lic.upper()) + ' ' + (x.get('license_version') or '')).strip(),
            'licence_url': x.get('license_url') or '', 'source': x.get('foreign_landing_url') or x.get('url'),
            'provider': x.get('provider') or '', 'size': [x.get('width'), x.get('height')], 'rights': 'cc0' if lic in ('cc0', 'pdm') else 'cc-by',
        })
    return {'results': out, 'pages': d.get('page_count', 1), 'count': d.get('result_count', 0)}


def _polite_url(item):
    """Wikimedia asks automated clients for standard thumbnail sizes: take the 3840 px one of very large files."""
    url = item.get('url') or ''
    w = (item.get('size') or [0])[0] or 0
    pre = 'https://upload.wikimedia.org/wikipedia/commons/'
    if url.startswith(pre) and '/thumb/' not in url and w and w > 3840:
        rest = url[len(pre):]                      # a/ab/Name.jpg
        name = rest.rsplit('/', 1)[-1]
        return pre + 'thumb/' + rest + '/3840px-' + name
    return url


def import_open(item):
    """Download an Openverse picture into the references, with its credit and licence."""
    import time
    url = _polite_url(item)
    if not url.startswith('https://'):
        raise ValueError('Only https links can be imported.')
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(urllib.parse.urlparse(url).path)[1] or '.jpg')
    os.close(fd)
    try:
        for wait in (0, 5, 20, 45):
            time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA})
                with urllib.request.urlopen(req, timeout=120) as r, open(tmp, 'wb') as f:
                    shutil.copyfileobj(r, f)
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or wait == 45:
                    raise
        meta = {'title': item.get('title') or 'Openverse picture', 'creator': item.get('creator', ''), 'licence': item.get('licence', ''),
                'source': item.get('source', ''), 'rights': item.get('rights', 'cc-by'),
                'notes': ('Licence: ' + item['licence_url']) if item.get('licence_url') else '', 'tags': ''}
        return add(tmp, os.path.basename(urllib.parse.urlparse(url).path), meta)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
