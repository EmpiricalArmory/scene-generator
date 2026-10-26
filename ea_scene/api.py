"""The generator's HTTP API, under /ea/api/.

Work that touches the GPU (cut-outs, generation) goes through ComfyUI's own queue: these routes return
the workflow, and the page queues it at /prompt and follows it on ComfyUI's websocket.
"""
import asyncio
import os
import shutil
import tempfile

import numpy as np
from aiohttp import web
import server

from . import VERSION, composite, downloads, jobs, models, paths, products, references, scene, training, workflows
from .util import load_gray, read_json

routes = server.PromptServer.instance.routes


async def in_thread(fn, *a, **k):
    return await asyncio.get_running_loop().run_in_executor(None, lambda: fn(*a, **k))


def fail(msg, status=400):
    return web.json_response({'error': str(msg)}, status=status)


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


def install_files():
    man = read_json(paths.MANIFEST, {}) or {}
    out = []
    for f in man.get('files', []):
        dest = os.path.join(paths.MODELS, *f['dest'].split('/'))
        size = int(f.get('size') or 0)
        have = os.path.getsize(dest) if os.path.isfile(dest) else 0
        part = os.path.getsize(dest + '.part') if os.path.isfile(dest + '.part') else 0
        ready = size > 0 and have == size
        out.append({'label': f['label'], 'group': f['group'], 'file': f['dest'], 'size': size, 'ready': ready,
                    'downloaded': size if ready else part, 'optional': bool(f.get('optional')), 'gated': bool(f.get('gated'))})
    return out


async def save_upload(field):
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(field.filename or '')[1] or '.bin')
    with os.fdopen(fd, 'wb') as f:
        shutil.copyfileobj(field.file, f)
    return tmp


def read_mask_upload(path):
    m = load_gray(path)
    return np.clip(m, 0, 1).astype(np.float32)


# ---------------------------------------------------------------- status

@routes.get('/ea/api/ping')
async def ping(request):
    return web.json_response({'ok': True, 'app': 'ea-scene-generator', 'version': VERSION})


@routes.get('/ea/api/status')
async def status(request):
    return web.json_response({
        'version': VERSION, 'root': paths.ROOT, 'data': paths.DATA,
        'install': read_json(os.path.join(paths.SETUP, 'status.json')),
        'system': read_json(os.path.join(paths.SETUP, 'system.json')),
        'gpu': gpu_info(), 'install_files': install_files(), 'models': models.status(),
        'downloads': downloads.state(), 'token': downloads.has_token(),
    })


@routes.get('/ea/api/options')
async def options(request):
    return web.json_response(scene.options())


@routes.post('/ea/api/restart')
async def restart(request):
    """Restart ComfyUI (Start.bat runs it again when it exits with code 42)."""
    async def later():
        await asyncio.sleep(0.5)
        os._exit(42)
    asyncio.get_running_loop().create_task(later())
    return web.json_response({'ok': True})


# ---------------------------------------------------------------- products

@routes.get('/ea/api/products')
async def product_list(request):
    return web.json_response({'products': products.all_products()})


@routes.post('/ea/api/products')
async def product_add(request):
    form = await request.post()
    f = form.get('file')
    if f is None or not getattr(f, 'filename', None):
        return fail('No photo was sent.')
    tmp = await save_upload(f)
    try:
        credit = None
        if form.get('credit'):
            import json
            credit = json.loads(form.get('credit'))
        p = await in_thread(products.create, tmp, form.get('name', ''), form.get('kind', 'other'), form.get('noun', ''),
                            credit, f.filename)
    except Exception as e:
        return fail('That photo could not be read: ' + str(e))
    finally:
        os.remove(tmp)
    return web.json_response({'product': p, 'cutout': workflows.cutout_graph(p['id'], 'auto')})


@routes.get('/ea/api/products/{pid}')
async def product_get(request):
    try:
        return web.json_response({'product': products.load(request.match_info['pid'])})
    except KeyError as e:
        return fail(e, 404)


@routes.post('/ea/api/products/{pid}')
async def product_update(request):
    pid = request.match_info['pid']
    body = await request.json()
    try:
        p = products.load(pid)
    except KeyError as e:
        return fail(e, 404)
    for k in ('name', 'noun', 'kind', 'credit', 'notes'):
        if k in body:
            p[k] = body[k]
    return web.json_response({'product': products.save(p)})


@routes.delete('/ea/api/products/{pid}')
async def product_delete(request):
    await in_thread(products.remove, request.match_info['pid'])
    return web.json_response({'ok': True})


@routes.post('/ea/api/products/{pid}/cutout')
async def product_cutout(request):
    body = await request.json() if request.can_read_body else {}
    return web.json_response({'prompt': workflows.cutout_graph(request.match_info['pid'], body.get('method', 'auto'))})


@routes.post('/ea/api/products/{pid}/mask')
async def product_mask(request):
    pid = request.match_info['pid']
    form = await request.post()
    f = form.get('mask')
    if f is None:
        return fail('No mask was sent.')
    tmp = await save_upload(f)
    try:
        m = read_mask_upload(tmp)
        info = await in_thread(products.set_mask, pid, m, form.get('refine', '1') == '1')
    finally:
        os.remove(tmp)
    return web.json_response({'product': products.load(pid), 'info': info})


@routes.post('/ea/api/products/{pid}/cover')
async def product_cover(request):
    pid = request.match_info['pid']
    form = await request.post()
    f = form.get('cover')
    if f is None:
        p = await in_thread(products.set_cover, pid, None)
        return web.json_response({'product': p})
    tmp = await save_upload(f)
    try:
        p = await in_thread(products.set_cover, pid, read_mask_upload(tmp))
    finally:
        os.remove(tmp)
    return web.json_response({'product': p})


@routes.get('/ea/api/products/{pid}/place')
async def product_place(request):
    """A starting placement for a preset (or a raw layout given as query values)."""
    pid = request.match_info['pid']
    preset = request.query.get('preset')
    layout = None
    for pr in scene.PRESETS:
        if pr['id'] == preset:
            layout = dict(pr['layout'])
    if layout is None:
        layout = {'aspect': request.query.get('aspect', '4:5'), 'point': request.query.get('point', 'keep'),
                  'length': float(request.query.get('length', 0.8)), 'cx': 0.5, 'cy': 0.5}
    if request.query.get('aspect'):
        layout['aspect'] = request.query['aspect']

    def work():
        p, fg, alpha, cover = products.layers(pid)
        if p.get('kind') != 'instrument' and not request.query.get('point'):
            layout['point'] = 'keep'           # gloves, masks and jackets stay as photographed
        return composite.auto_place(alpha, layout)
    try:
        place = await in_thread(work)
    except Exception as e:
        return fail(e)
    return web.json_response({'place': place})


# ---------------------------------------------------------------- prompts and jobs

@routes.post('/ea/api/prompt')
async def prompt_text(request):
    body = await request.json()
    try:
        p = products.load(body['product'])
    except Exception:
        p = {'kind': body.get('kind', 'instrument'), 'noun': body.get('noun', '')}
    s = body.get('scene') or {}
    return web.json_response({'prompt': scene.prompt(s, p, body.get('family', 'qwen')), 'negative': scene.negative(s)})


@routes.post('/ea/api/jobs')
async def job_create(request):
    """Create one job per model asked for, and return each one's workflows (one per variation)."""
    body = await request.json()
    fams = body.get('families') or [body.get('family', 'qwen')]
    st = models.status()
    out = []
    for fam in fams:
        if fam not in st or not st[fam]['ready']:
            return fail(f'{models.FAMILIES.get(fam, {}).get("name", fam)} is not installed yet.')
        req = dict(body)
        req['family'] = fam
        try:
            j = await in_thread(jobs.create, req)
        except Exception as e:
            return fail(e)
        n = max(1, min(8, int(body.get('variations', 1))))
        out.append({'job': j, 'prompts': [workflows.build(j, v, st) for v in range(n)]})
    return web.json_response({'jobs': out})


@routes.get('/ea/api/results')
async def result_list(request):
    items = await in_thread(jobs.list_results, int(request.query.get('limit', 500)), request.query.get('batch'))
    return web.json_response({'results': items})


@routes.delete('/ea/api/results/{day}/{name}')
async def result_delete(request):
    day, name = request.match_info['day'], request.match_info['name']
    from .util import inside, safe_name
    d = inside(jobs.RESULTS, safe_name(day))
    removed = 0
    for suffix in ('.png', '-raw.png', '-parts.png', '-thumb.jpg', '.json'):
        p = inside(d, safe_name(name) + suffix)
        if os.path.exists(p):
            os.remove(p)
            removed += 1
    return web.json_response({'removed': removed})


# ---------------------------------------------------------------- references (style pictures)

@routes.get('/ea/api/references')
async def reference_list(request):
    return web.json_response({'references': references.all_references()})


@routes.post('/ea/api/references')
async def reference_add(request):
    form = await request.post()
    f = form.get('file')
    if f is None:
        return fail('No picture was sent.')
    tmp = await save_upload(f)
    try:
        meta = {k: form.get(k, '') for k in ('title', 'creator', 'licence', 'source', 'rights', 'notes', 'tags')}
        r = await in_thread(references.add, tmp, f.filename, meta)
    except Exception as e:
        return fail(e)
    finally:
        os.remove(tmp)
    return web.json_response({'reference': r})


@routes.get('/ea/api/openverse')
async def openverse_search(request):
    q = request.query.get('q', '').strip()
    if not q:
        return web.json_response({'results': [], 'pages': 0, 'count': 0})
    try:
        return web.json_response(await in_thread(references.search_open, q, int(request.query.get('page', 1))))
    except Exception as e:
        return fail('The search did not answer: ' + str(e), 502)


@routes.post('/ea/api/references/import')
async def reference_import(request):
    body = await request.json()
    try:
        return web.json_response({'reference': await in_thread(references.import_open, body)})
    except Exception as e:
        return fail('Could not fetch that picture: ' + str(e), 502)


@routes.post('/ea/api/references/{rid}')
async def reference_update(request):
    body = await request.json()
    try:
        return web.json_response({'reference': references.update(request.match_info['rid'], body)})
    except KeyError as e:
        return fail(e, 404)


@routes.delete('/ea/api/references/{rid}')
async def reference_delete(request):
    await in_thread(references.remove, request.match_info['rid'])
    return web.json_response({'ok': True})


# ---------------------------------------------------------------- captions and training

@routes.post('/ea/api/references/{rid}/caption')
async def reference_caption(request):
    if not models._have(*training.CAPTION_MODEL):
        return fail('Captions need the Gemma 4 helper: download it under Models first.')
    body = await request.json() if request.can_read_body else {}
    return web.json_response({'prompt': training.caption_graph(request.match_info['rid'], body.get('trigger') or training.TRIGGER)})


def _trained_loras():
    out = []
    for s in training.all_sets():
        if s.get('state') == 'done' and s.get('lora') and models._have('loras', s['lora']):
            out.append({'set': s['id'], 'name': s['name'], 'base': s['base'], 'lora': s['lora'], 'trigger': s['trigger']})
    return out


@routes.get('/ea/api/training')
async def training_list(request):
    return web.json_response({'sets': training.all_sets(), 'loras': _trained_loras(), 'bases': training.BASES,
                              'caption_ready': models._have(*training.CAPTION_MODEL),
                              'usable': sum(1 for r in references.all_references() if training.usable(r))})


@routes.post('/ea/api/training')
async def training_create(request):
    body = await request.json()
    st = models.status()
    base = body.get('base', 'hidream')
    if not st.get(base, {}).get('ready'):
        return fail(training.BASES.get(base, base) + ' is not downloaded yet.')
    try:
        s = await in_thread(training.create, body.get('name', ''), base, body.get('refs'), body.get('trigger') or training.TRIGGER,
                            body.get('steps'), int(body.get('rank', 16)), float(body.get('learning_rate', 1e-4)))
    except Exception as e:
        return fail(e)
    return web.json_response({'set': s, 'prompt': training.train_graph(s, int(body.get('seed', 0)))})


@routes.post('/ea/api/training/{sid}/run')
async def training_run(request):
    try:
        s = training.load(request.match_info['sid'])
    except KeyError as e:
        return fail(e, 404)
    return web.json_response({'set': s, 'prompt': training.train_graph(s)})


@routes.delete('/ea/api/training/{sid}')
async def training_delete(request):
    await in_thread(training.remove, request.match_info['sid'])
    return web.json_response({'ok': True})


# ---------------------------------------------------------------- model downloads

@routes.post('/ea/api/models/download')
async def model_download(request):
    body = await request.json()
    try:
        downloads.start(body['key'])
    except Exception as e:
        return fail(e)
    return web.json_response({'downloads': downloads.state()})


@routes.post('/ea/api/token')
async def set_token(request):
    body = await request.json()
    ok, msg = await in_thread(downloads.set_token, (body.get('token') or '').strip())
    return web.json_response({'ok': ok, 'message': msg, 'token': downloads.has_token()})
