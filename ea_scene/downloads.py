"""Downloading model files from Hugging Face in the background, with resume and a checksum.

The Hugging Face token (needed only for FLUX 3, whose licence must be accepted first) is kept in
data/secrets/hf_token.txt on this computer and sent only to huggingface.co.
"""
import hashlib
import os
import threading
import time
import urllib.request

from . import paths
from .models import HELPERS, helper_files
from .util import read_json

SECRETS = os.path.join(paths.DATA, 'secrets')
TOKEN_FILE = os.path.join(SECRETS, 'hf_token.txt')
_STATE = {}
_LOCK = threading.Lock()


def has_token():
    return os.path.isfile(TOKEN_FILE) and os.path.getsize(TOKEN_FILE) > 0


def _token():
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def set_token(token):
    if not token:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        return True, 'Token removed.'
    req = urllib.request.Request('https://huggingface.co/api/whoami-v2', headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = r.status == 200
    except Exception as e:
        return False, 'Hugging Face did not accept the token (' + str(e) + ').'
    if ok:
        os.makedirs(SECRETS, exist_ok=True)
        with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
            f.write(token)
        return True, 'Token saved on this computer.'
    return False, 'Hugging Face did not accept the token.'


def catalogue():
    """Everything the generator knows how to fetch: the installer's files plus the helpers (some of
    which are more than one file)."""
    items = {}
    man = read_json(paths.MANIFEST, {}) or {}
    for f in man.get('files', []):
        key = f['dest']
        part = {'url': f['url'], 'dest': f['dest'], 'size': f['size'], 'sha256': f.get('sha256')}
        items[key] = {'key': key, 'label': f['label'], 'parts': [part], 'size': f['size'], 'gated': f.get('gated', False)}
    for k, h in HELPERS.items():
        parts = [{'url': x['url'], 'dest': x['folder'] + '/' + x['file'], 'size': x['size'], 'sha256': x['sha256']}
                 for x in helper_files(h)]
        items[k] = {'key': k, 'label': h['label'], 'parts': parts, 'size': sum(p['size'] for p in parts), 'gated': False}
    return items


def state():
    with _LOCK:
        return {k: dict(v) for k, v in _STATE.items()}


def start(key):
    items = catalogue()
    if key not in items:
        raise KeyError('Unknown model file: ' + key)
    it = items[key]
    if it['gated'] and not has_token():
        raise PermissionError('This model needs a Hugging Face token: add it under Models first.')
    with _LOCK:
        cur = _STATE.get(key)
        if cur and cur.get('state') == 'running':
            return
        _STATE[key] = {'label': it['label'], 'state': 'running', 'done': 0, 'size': it['size'], 'speed': 0, 'error': ''}
    threading.Thread(target=_run, args=(it,), daemon=True).start()


def _run(it):
    key = it['key']
    try:
        before = 0                       # bytes of the parts already finished
        for p in it['parts']:
            dest = os.path.join(paths.MODELS, *p['dest'].split('/'))
            if os.path.isfile(dest) and os.path.getsize(dest) == p['size']:
                before += p['size']
                continue
            _fetch(key, it, p, dest, before)
            before += p['size']
        with _LOCK:
            _STATE[key].update(state='done', done=it['size'])
    except Exception as e:
        with _LOCK:
            _STATE[key].update(state='error', error=str(e))


def _fetch(key, it, p, dest, before):
    part = dest + '.part'
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(30):
        have = os.path.getsize(part) if os.path.exists(part) else 0
        if have >= p['size']:
            break
        headers = {'User-Agent': 'EmpiricalArmory-SceneGenerator'}
        if have:
            headers['Range'] = f'bytes={have}-'
        if it['gated']:
            headers['Authorization'] = 'Bearer ' + _token()
        try:
            req = urllib.request.Request(p['url'], headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r, open(part, 'ab' if have else 'wb') as f:
                if have and r.status != 206:
                    f.truncate(0)
                    have = 0
                t0, last = time.time(), have
                while True:
                    chunk = r.read(1 << 22)
                    if not chunk:
                        break
                    f.write(chunk)
                    have += len(chunk)
                    dt = time.time() - t0
                    if dt > 1:
                        with _LOCK:
                            _STATE[key].update(done=before + have, speed=int((have - last) / dt))
                        t0, last = time.time(), have
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError('Hugging Face refused the download: accept the model\'s licence on its page with the same account as the token.')
            time.sleep(10)
        except Exception:
            time.sleep(10)
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if have != p['size']:
        raise IOError('The download did not finish. Try again to carry on.')
    with _LOCK:
        _STATE[key].update(state='checking', done=before + have)
    if p.get('sha256'):
        h = hashlib.sha256()
        with open(part, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 24), b''):
                h.update(chunk)
        if h.hexdigest() != p['sha256']:
            os.remove(part)
            raise IOError('The file was damaged in the download and has been removed. Try again.')
    os.replace(part, dest)
    with _LOCK:
        _STATE[key].update(state='running')
