"""The generator's HTTP API (under /ea/api/) and its page (under /ea/)."""
import json
import os

from aiohttp import web
import server

from . import VERSION, paths

routes = server.PromptServer.instance.routes

MIME = {
    '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
    '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2', '.ico': 'image/x-icon',
}


def read_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return default


_GPU = None


def gpu_info():
    global _GPU
    if _GPU is None:
        try:
            import torch
            if torch.cuda.is_available():
                p = torch.cuda.get_device_properties(0)
                _GPU = {'name': p.name, 'vram_gb': round(p.total_memory / 2**30, 1), 'torch': torch.__version__, 'cuda': torch.version.cuda}
            else:
                _GPU = {'name': None, 'torch': torch.__version__}
        except Exception as e:  # pragma: no cover
            _GPU = {'name': None, 'error': str(e)}
    return _GPU


def model_files():
    man = read_json(paths.MANIFEST, {}) or {}
    out = []
    for f in man.get('files', []):
        dest = os.path.join(paths.MODELS, *f['dest'].split('/'))
        size = int(f.get('size') or 0)
        have = os.path.getsize(dest) if os.path.isfile(dest) else 0
        part = os.path.getsize(dest + '.part') if os.path.isfile(dest + '.part') else 0
        ready = size > 0 and have == size
        out.append({
            'label': f['label'], 'group': f['group'], 'file': f['dest'], 'size': size,
            'ready': ready, 'downloaded': size if ready else part,
            'optional': bool(f.get('optional')), 'gated': bool(f.get('gated')),
        })
    return out


@routes.get('/ea/api/ping')
async def ping(request):
    return web.json_response({'ok': True, 'app': 'ea-scene-generator', 'version': VERSION})


@routes.get('/ea/api/status')
async def status(request):
    return web.json_response({
        'version': VERSION,
        'root': paths.ROOT,
        'install': read_json(os.path.join(paths.SETUP, 'status.json')),
        'system': read_json(os.path.join(paths.SETUP, 'system.json')),
        'gpu': gpu_info(),
        'models': model_files(),
    })


# ---------------------------------------------------------------- the page (registered last)

@routes.get('/ea')
async def page_root(request):
    raise web.HTTPFound('/ea/')


@routes.get('/ea/{tail:.*}')
async def page(request):
    tail = request.match_info.get('tail') or 'index.html'
    if tail.startswith('api/'):
        raise web.HTTPNotFound()
    full = os.path.normpath(os.path.join(paths.WEB, tail))
    if not (full == paths.WEB or full.startswith(paths.WEB + os.sep)):
        raise web.HTTPForbidden()
    if os.path.isdir(full):
        full = os.path.join(full, 'index.html')
    if not os.path.isfile(full):
        raise web.HTTPNotFound()
    ext = os.path.splitext(full)[1].lower()
    return web.FileResponse(full, headers={'Cache-Control': 'no-cache', 'Content-Type': MIME.get(ext, 'application/octet-stream')})
