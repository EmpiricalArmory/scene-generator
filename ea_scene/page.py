"""The page (under /ea/) and the files in data/ (under /ea/data/). Registered after the API."""
import os

from aiohttp import web
import server

from . import paths
from .util import inside

routes = server.PromptServer.instance.routes

MIME = {
    '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
    '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2', '.ico': 'image/x-icon',
    '.tif': 'image/tiff', '.tiff': 'image/tiff',
}


def _send(full, cache='no-cache'):
    if not os.path.isfile(full):
        raise web.HTTPNotFound()
    ext = os.path.splitext(full)[1].lower()
    return web.FileResponse(full, headers={'Cache-Control': cache, 'Content-Type': MIME.get(ext, 'application/octet-stream')})


@routes.get('/ea/data/{tail:.*}')
async def data_file(request):
    tail = request.match_info.get('tail', '')
    if tail.startswith('secrets') or '/secrets' in tail:
        raise web.HTTPForbidden()
    try:
        full = inside(paths.DATA, *tail.split('/'))
    except ValueError:
        raise web.HTTPForbidden()
    return _send(full)


@routes.get('/ea')
async def page_root(request):
    raise web.HTTPFound('/ea/')


@routes.get('/ea/{tail:.*}')
async def page(request):
    tail = request.match_info.get('tail') or 'index.html'
    if tail.startswith('api/'):
        raise web.HTTPNotFound()
    try:
        full = inside(paths.WEB, *tail.split('/'))
    except ValueError:
        raise web.HTTPForbidden()
    if os.path.isdir(full):
        full = os.path.join(full, 'index.html')
    return _send(full)
