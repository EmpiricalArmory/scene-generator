// Empirical Armory scene generator: the page.
import * as comfy from './comfy.js';
import { Stage } from './stage.js';
import { editMask } from './editor.js';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const gb = (b) => (b / 1e9).toFixed(1) + ' GB';

const FAMILY_ORDER = ['flux3', 'qwen', 'hidream'];
const WORN = new Set(['worn-hands', 'worn-head', 'worn-torso', 'worn-guard']);
const isWorn = () => WORN.has(S.scene.pose);
const KIND_LABELS = { instrument: 'Sword or trainer', gloves: 'Gloves', mask: 'Mask', jacket: 'Jacket', other: 'Other' };

const S = {
  options: null, status: null, products: [], product: null, references: [],
  place: { aspect: '4:5', cx: 0.5, cy: 0.5, length: 0.8, rotation: 0, flip: false },
  scene: { preset: 'cover', pose: 'held-up', people: 'hand', place: 'brick', light: 'overcast', height: 'eye', lens: '85', aperture: '2.8', side: 'right', framing: 'half', extra: '', place_text: '' },
  custom: false, customText: '', family: null, quality: 'final', variations: 2, seed: '', mode: 'exact', outLong: 2400, refs: [],
  cards: [],
};

// ---------------------------------------------------------------- small helpers
async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.json !== undefined) { init.method = init.method || 'POST'; init.headers = { 'Content-Type': 'application/json' }; init.body = JSON.stringify(opts.json); }
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (!res.ok || body.error) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
}
let toastTimer = null;
function toast(msg, err = false) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false; t.classList.toggle('err', err);
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), err ? 9000 : 4000);
}
function store(key, val) { try { localStorage.setItem('ea-sg-' + key, JSON.stringify(val)); } catch { /* private window */ } }
function recall(key, dflt) { try { const v = localStorage.getItem('ea-sg-' + key); return v ? JSON.parse(v) : dflt; } catch { return dflt; } }
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function loadImg(src) { return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; }); }
const dataUrl = (p) => '/ea/data/' + p;

function seg(el, items, current, onPick, { multi = false } = {}) {
  el.innerHTML = items.map((it) => `<button type="button" data-v="${esc(it.id)}" ${it.title ? `title="${esc(it.title)}"` : ''} ${it.disabled ? 'disabled' : ''}>${esc(it.label)}</button>`).join('');
  const sync = (cur) => { for (const b of $$('button', el)) b.setAttribute('aria-pressed', multi ? cur.includes(b.dataset.v) : b.dataset.v === cur); };
  sync(current);
  el.onclick = (e) => {
    const b = e.target.closest('button'); if (!b || b.disabled) return;
    onPick(b.dataset.v, sync);
  };
  return sync;
}
function segStatic(el, current, onPick) {
  const sync = (cur) => { for (const b of $$('button', el)) b.setAttribute('aria-pressed', b.dataset.v === String(cur)); };
  sync(current);
  el.onclick = (e) => { const b = e.target.closest('button'); if (!b || b.disabled) return; onPick(b.dataset.v); sync(b.dataset.v); };
  return sync;
}

// ---------------------------------------------------------------- tabs
function showTab(name) {
  for (const b of $$('.tabs button')) b.setAttribute('aria-selected', b.dataset.tab === name);
  for (const t of $$('main.tab')) t.hidden = t.id !== 'tab-' + name;
  store('tab', name);
  if (name === 'make') stage.layout();
  if (name === 'results') loadResults();
  if (name === 'compare') renderCompareSetup();
  if (name === 'references') loadReferences();
  if (name === 'models') refreshStatus();
}
for (const b of $$('.tabs button')) b.addEventListener('click', () => showTab(b.dataset.tab));

// ---------------------------------------------------------------- queue indicator
comfy.on((type, data) => {
  if (type === 'connection' || type === 'queue') {
    $('#connDot').classList.toggle('on', comfy.connected());
    const n = comfy.remaining();
    $('#queueText').textContent = !comfy.connected() ? 'Not connected: is the generator\'s window open?' : (n ? `Making pictures: ${n} in the queue` : 'Ready');
    $('#btnStop').hidden = !n;
  }
});
$('#btnStop').addEventListener('click', async () => { await comfy.clearQueue(); await comfy.interrupt(); toast('Stopped, and the queue is empty.'); });

// ---------------------------------------------------------------- the frame
const stage = new Stage($('#frame'), $('#frameCanvas'), $('#stageWrap'), (place, done) => {
  S.place = { ...place };
  $('#inRotation').value = Math.round(place.rotation * 10) / 10;
  $('#inLength').value = place.length;
  if (done) savePlace();
});
function savePlace() { if (S.product) store('place:' + S.product.id, S.place); syncPlaceInputs(); }
function syncPlaceInputs() { $('#inRotation').value = Math.round((S.place.rotation || 0) * 10) / 10; $('#inLength').value = S.place.length; }
const syncAspect = segStatic($('#segAspect'), S.place.aspect, async (v) => {
  S.place.aspect = v; stage.setPlace({ aspect: v });
  if (S.product?.cutout) await autoPlace(S.scene.preset, v);
  savePlace();
});
$('#inRotation').addEventListener('change', (e) => { S.place.rotation = +e.target.value || 0; stage.setPlace(S.place); savePlace(); });
$('#inLength').addEventListener('input', (e) => { S.place.length = +e.target.value; stage.setPlace(S.place); savePlace(); });
$('#btnCentre').addEventListener('click', async () => { if (S.product) await autoPlace(S.scene.preset, S.place.aspect, { keepTurn: true }); });
$('#btnPointUp').addEventListener('click', async () => {
  if (!S.product) return;
  const r = await api(`/ea/api/products/${S.product.id}/place?point=up&aspect=${S.place.aspect}&length=${S.place.length}`);
  S.place = { ...S.place, ...r.place }; stage.setPlace(S.place); savePlace();
});
$('#chkCover').addEventListener('change', (e) => { stage.showCover = e.target.checked; stage.draw(); });

async function autoPlace(presetId, aspect, { keepTurn = false } = {}) {
  if (!S.product?.cutout) return;
  const q = presetId ? `preset=${encodeURIComponent(presetId)}&aspect=${aspect || S.place.aspect}` : `aspect=${aspect || S.place.aspect}`;
  try {
    const r = await api(`/ea/api/products/${S.product.id}/place?${q}`);
    const rot = S.place.rotation;
    S.place = { ...S.place, ...r.place };
    if (keepTurn) S.place.rotation = rot;
    syncAspect(S.place.aspect);
    stage.setPlace(S.place);
    savePlace();
  } catch (e) { toast(e.message, true); }
}

// ---------------------------------------------------------------- products
async function loadProducts(selectId) {
  const r = await api('/ea/api/products');
  S.products = r.products;
  const want = selectId || S.product?.id || recall('product', null);
  renderProducts();
  const p = S.products.find((x) => x.id === want) || S.products[0];
  if (p) await selectProduct(p.id, { quiet: true });
  else showEmpty(true);
}
function showEmpty(on) { $('#makeEmpty').hidden = !on; $('#frame').hidden = on; }

function renderProducts() {
  const el = $('#productList');
  el.innerHTML = S.products.map((p) => `<button type="button" class="pitem" data-id="${p.id}" aria-selected="${p.id === S.product?.id}" title="${esc(p.name)}">
      <img src="${dataUrl(`products/${p.id}/thumb.jpg?r=${p.rev || 0}`)}" alt="" onerror="this.style.visibility='hidden'">
      <span>${esc(p.name)}</span>${p.cutout ? '' : '<div class="busy">Cutting out…</div>'}</button>`).join('')
    + `<label class="pitem add">Add a<br>product photo<input type="file" accept="image/*" hidden id="fileProduct2"></label>`;
  el.onclick = (e) => { const b = e.target.closest('.pitem[data-id]'); if (b) selectProduct(b.dataset.id); };
  $('#fileProduct2').addEventListener('change', (e) => { if (e.target.files[0]) addProduct(e.target.files[0]); e.target.value = ''; });
}

async function selectProduct(id, { quiet = false } = {}) {
  const r = await api('/ea/api/products/' + id);
  S.product = r.product; store('product', id);
  renderProducts();
  $('#productDetail').hidden = false;
  $('#inName').value = S.product.name || '';
  $('#inNoun').value = S.product.noun || '';
  segKind(S.product.kind || 'other');
  const c = S.product.cutout;
  $('#cutInfo').textContent = !c ? 'Cutting it out…' : `Cut out ${c.method === 'model' ? 'by the model' : c.method === 'edited' ? 'and edited by hand' : 'by ' + c.method}. ${S.product.size[0]} × ${S.product.size[1]} px.` + (S.product.credit ? ` ${S.product.credit.title || ''} by ${S.product.credit.creator}, ${S.product.credit.licence}.` : '');
  showEmpty(false);
  renderPoses(); renderPresets();
  if (c) {
    const rev = S.product.rev || 0;
    const [img, cov] = await Promise.all([
      loadImg(dataUrl(`products/${id}/preview.png?r=${rev}`)),
      S.product.cover ? loadImg(dataUrl(`products/${id}/cover_preview.png?r=${rev}`)).then(tintCover).catch(() => null) : null,
    ]);
    stage.setProduct(S.product, img, cov);
    const saved = recall('place:' + id, null);
    if (saved) { S.place = { ...S.place, ...saved }; syncAspect(S.place.aspect); stage.setPlace(S.place); syncPlaceInputs(); }
    else await autoPlace(S.scene.preset, S.place.aspect);
  } else {
    stage.setProduct(null, null, null);
  }
  updatePrompt(); updateGenerate();
}

// the cover preview is grey; turn it into a translucent orange layer
async function tintCover(img) {
  const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
  const x = c.getContext('2d'); x.drawImage(img, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height), a = d.data;
  for (let i = 0; i < a.length; i += 4) { const v = a[i]; a[i] = 239; a[i + 1] = 176; a[i + 2] = 46; a[i + 3] = v; }
  x.putImageData(d, 0, 0);
  return c;
}

function segKind(kind) {
  const el = $('#segKind');
  el.innerHTML = Object.entries(KIND_LABELS).map(([k, l]) => `<button type="button" data-v="${k}" aria-pressed="${k === kind}">${l}</button>`).join('');
  el.onclick = async (e) => {
    const b = e.target.closest('button'); if (!b || !S.product) return;
    S.product = (await api('/ea/api/products/' + S.product.id, { json: { kind: b.dataset.v } })).product;
    segKind(S.product.kind); renderPoses(); renderPresets(); updatePrompt();
  };
}
$('#inName').addEventListener('change', async (e) => { if (!S.product) return; S.product = (await api('/ea/api/products/' + S.product.id, { json: { name: e.target.value } })).product; renderProducts(); });
$('#inNoun').addEventListener('change', async (e) => { if (!S.product) return; S.product = (await api('/ea/api/products/' + S.product.id, { json: { noun: e.target.value } })).product; updatePrompt(); });

async function addProduct(file, extra = {}) {
  const fd = new FormData();
  fd.append('file', file, file.name);
  fd.append('name', extra.name || file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' '));
  fd.append('kind', extra.kind || 'other');
  if (extra.noun) fd.append('noun', extra.noun);
  if (extra.credit) fd.append('credit', JSON.stringify(extra.credit));
  toast('Adding the photo and cutting it out…');
  try {
    const r = await api('/ea/api/products', { method: 'POST', body: fd });
    S.products.unshift(r.product); S.product = r.product; renderProducts(); showEmpty(false);
    await comfy.run(r.cutout);
    await loadProducts(r.product.id);
    toast('Cut out. Check the edges with "Check the cut-out" if you like.');
  } catch (e) { toast('Could not add the photo: ' + e.message, true); await loadProducts(); }
}
$('#fileProduct').addEventListener('change', (e) => { if (e.target.files[0]) addProduct(e.target.files[0]); e.target.value = ''; });
$('#btnSample').addEventListener('click', async () => {
  const meta = await (await fetch('samples/samples.json')).json();
  const s = meta[0];
  const blob = await (await fetch('samples/' + s.file)).blob();
  await addProduct(new File([blob], s.file, { type: blob.type }), { name: s.title, kind: s.kind, noun: s.noun, credit: { title: s.originalTitle, creator: s.creator, licence: s.licence, source: s.source } });
});
document.addEventListener('dragover', (e) => { if ($('#tab-make').hidden) return; e.preventDefault(); });
document.addEventListener('drop', (e) => {
  if ($('#tab-make').hidden) return;
  e.preventDefault();
  const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith('image/'));
  if (f) addProduct(f);
});

$('#btnRecut').addEventListener('click', async () => {
  if (!S.product) return;
  const method = confirm('Cut it out with the model? (Cancel uses the plain-backdrop method instead.)') ? 'model' : 'white backdrop';
  toast('Cutting it out again…');
  try { const r = await api(`/ea/api/products/${S.product.id}/cutout`, { json: { method } }); await comfy.run(r.prompt); await loadProducts(S.product.id); toast('Done.'); }
  catch (e) { toast(e.message, true); }
});
$('#btnDeleteProduct').addEventListener('click', async () => {
  if (!S.product || !confirm(`Remove "${S.product.name}" from the generator? Pictures already made stay.`)) return;
  await api('/ea/api/products/' + S.product.id, { method: 'DELETE' });
  S.product = null; store('product', null); await loadProducts();
});
$('#btnEditMask').addEventListener('click', async () => {
  const p = S.product; if (!p?.cutout) return;
  const rev = p.rev || 0;
  const r = await editMask({ title: 'Check the cut-out: ' + p.name, photo: dataUrl(`products/${p.id}/edit.jpg?r=${rev}`), mask: dataUrl(`products/${p.id}/mask_edit.png?r=${rev}`), colour: [217, 71, 43], snap: true,
    hint: 'Red is the product. Paint more of it with Add, take away with Remove (X). "Snap to edges" fits your strokes to the photo\'s edges when you save.' });
  if (!r) return;
  const fd = new FormData(); fd.append('mask', r.blob, 'mask.png'); fd.append('refine', r.snap ? '1' : '0');
  toast('Saving the cut-out…');
  try { await api(`/ea/api/products/${p.id}/mask`, { method: 'POST', body: fd }); await selectProduct(p.id, { quiet: true }); toast('Saved.'); } catch (e) { toast(e.message, true); }
});
$('#btnEditCover').addEventListener('click', async () => {
  const p = S.product; if (!p?.cutout) return;
  const rev = p.rev || 0;
  const r = await editMask({ title: 'Where hands may go: ' + p.name, photo: dataUrl(`products/${p.id}/edit.jpg?r=${rev}`), mask: p.cover ? dataUrl(`products/${p.id}/cover_edit.png?r=${rev}`) : null,
    under: dataUrl(`products/${p.id}/mask_edit.png?r=${rev}`), colour: [239, 176, 46], snap: false, allowClear: true,
    hint: 'Paint (yellow) the parts of the product that hands or other things may cover, such as a sword\'s grip. Everywhere else the product stays exactly as photographed.' });
  if (!r) return;
  const fd = new FormData(); fd.append('cover', r.blob, 'cover.png');
  try { await api(`/ea/api/products/${p.id}/cover`, { method: 'POST', body: fd }); await selectProduct(p.id, { quiet: true }); toast('Saved.'); } catch (e) { toast(e.message, true); }
});

// ---------------------------------------------------------------- scene settings
let syncPlace, syncLight, syncPeople, syncPose, syncHeight, syncLens, syncAperture, syncFraming, syncSide, syncPreset;
function renderScene() {
  const o = S.options;
  syncPlace = seg($('#segPlace'), o.places, S.scene.place, (v, sync) => { S.scene.place = v; S.scene.place_text = ''; $('#inPlaceText').value = ''; sync(v); sceneChanged(); });
  syncLight = seg($('#segLight'), o.lights, S.scene.light, (v, sync) => { S.scene.light = v; sync(v); sceneChanged(); });
  syncPeople = seg($('#segPeople'), o.people, S.scene.people, (v, sync) => { S.scene.people = v; sync(v); sceneChanged(); });
  syncHeight = seg($('#segHeight'), o.heights, S.scene.height, (v, sync) => { S.scene.height = v; sync(v); sceneChanged(); });
  syncLens = seg($('#segLens'), o.lenses, S.scene.lens, (v, sync) => { S.scene.lens = v; sync(v); sceneChanged(); });
  syncAperture = seg($('#segAperture'), o.apertures, S.scene.aperture, (v, sync) => { S.scene.aperture = v; sync(v); sceneChanged(); });
  syncFraming = seg($('#segFraming'), o.framings, S.scene.framing, (v, sync) => { S.scene.framing = v; sync(v); sceneChanged(); });
  syncSide = segStatic($('#segSide'), S.scene.side, (v) => { S.scene.side = v; sceneChanged(); });
  $('#inPlaceText').value = S.scene.place_text || '';
  $('#inExtra').value = S.scene.extra || '';
  renderPoses(); renderPresets();
}
function poseKind() { return (S.product?.kind || 'instrument') === 'instrument' ? 'instrument' : 'worn'; }
function renderPoses() {
  if (!S.options) return;
  const list = S.options.poses[poseKind()];
  if (!list.find((p) => p.id === S.scene.pose)) S.scene.pose = list[0].id;
  syncPose = seg($('#segPose'), list, S.scene.pose, (v, sync) => { S.scene.pose = v; sync(v); sceneChanged(); });
}
function presetsFor(product) {
  const kind = product?.kind || 'instrument';
  return S.options.presets.filter((p) => p.kind === 'any' || p.kind === kind || (p.kind === 'worn' && kind !== 'instrument'));
}
function renderPresets() {
  if (!S.options) return;
  const list = presetsFor(S.product).map((p) => ({ id: p.id, label: p.label }));
  syncPreset = seg($('#segPreset'), list, S.scene.preset, async (v, sync) => {
    const pr = S.options.presets.find((p) => p.id === v);
    S.scene = { ...S.scene, ...pr.scene, preset: v, place_text: '' };
    sync(v); renderScene(); sceneChanged();
    if (pr.mode === 'reference') { S.place.aspect = pr.layout.aspect; syncAspect(S.place.aspect); stage.setPlace(S.place); }
    else await autoPlace(v, pr.layout.aspect);
  });
}
function sceneChanged() {
  const worn = isWorn();
  $('#stageWrap').classList.toggle('worn', worn);
  $('#wornNote').hidden = !worn;
  for (const id of ['#btnPointUp', '#btnCentre', '#inRotation', '#inLength']) $(id).disabled = worn;
  $('#rowSide').hidden = !(['hand', 'hands'].includes(S.scene.people) || ['held-up', 'in-hand'].includes(S.scene.pose));
  $('#rowFraming').hidden = !['fencer', 'pair'].includes(S.scene.people);
  store('scene', S.scene);
  updatePrompt();
}
$('#inPlaceText').addEventListener('input', debounce((e) => { S.scene.place_text = e.target.value.trim(); if (S.scene.place_text) syncPlace(''); sceneChanged(); }, 400));
$('#inExtra').addEventListener('input', debounce((e) => { S.scene.extra = e.target.value.trim(); sceneChanged(); }, 400));
$('#chkCustom').addEventListener('change', (e) => {
  S.custom = e.target.checked; $('#txtPrompt').readOnly = !S.custom;
  if (S.custom) { S.customText = $('#txtPrompt').value; $('#txtPrompt').focus(); } else updatePrompt();
});
$('#txtPrompt').addEventListener('input', (e) => { if (S.custom) S.customText = e.target.value; });

const updatePrompt = debounce(async () => {
  if (S.custom) return;
  try {
    const r = await api('/ea/api/prompt', { json: { product: S.product?.id, scene: S.scene, family: S.family } });
    $('#txtPrompt').value = r.prompt;
  } catch { /* the server may be restarting */ }
}, 150);

// ---------------------------------------------------------------- picture and model
segStatic($('#segMode'), S.mode, (v) => { S.mode = v; store('mode', v); });
segStatic($('#segOut'), S.outLong, (v) => { S.outLong = +v; store('outLong', S.outLong); });
segStatic($('#segQuality'), S.quality, (v) => { S.quality = v; store('quality', v); });
$('#selVariations').addEventListener('change', (e) => { S.variations = +e.target.value; store('variations', S.variations); });
$('#inSeed').addEventListener('change', (e) => { S.seed = e.target.value.trim(); });

function renderModels() {
  const st = S.status?.models || {};
  const ready = FAMILY_ORDER.filter((f) => st[f]?.ready);
  if (!S.family || !st[S.family]?.ready) S.family = ready[0] || FAMILY_ORDER[0];
  $('#modelPick').innerHTML = FAMILY_ORDER.map((f) => {
    const m = st[f] || { name: f };
    const missing = m.ready ? '' : ' · not downloaded yet';
    return `<label class="mopt${m.ready ? '' : ' off'}"><input type="radio" name="family" value="${f}" ${f === S.family ? 'checked' : ''} ${m.ready ? '' : 'disabled'}>
      <span class="mn">${esc(m.name)}${missing}</span><span class="ml">${esc(m.licence || '')}</span></label>`;
  }).join('');
  for (const r of $$('#modelPick input')) r.addEventListener('change', () => { S.family = r.value; store('family', S.family); updatePrompt(); updateGenerate(); });
  updateGenerate();
}
function updateGenerate() {
  const st = S.status?.models || {};
  const ok = S.product?.cutout && st[S.family]?.ready;
  $('#btnGenerate').disabled = !ok;
  $('#genHint').textContent = !S.product ? 'Add a product first.' : !S.product.cutout ? 'Waiting for the cut-out.' : !st[S.family]?.ready ? 'This model is still downloading (see Models).' : '';
}

function renderRefPick() {
  const usable = S.references;
  $('#refPick').innerHTML = usable.map((r) => `<button type="button" data-id="${r.id}" aria-pressed="${S.refs.includes(r.id)}" title="${esc(r.title)}"><img src="${dataUrl(`references/${r.id}/thumb.jpg`)}" alt=""></button>`).join('');
  $('#refPick').onclick = (e) => {
    const b = e.target.closest('button'); if (!b) return;
    const id = b.dataset.id;
    S.refs = S.refs.includes(id) ? S.refs.filter((x) => x !== id) : [...S.refs, id].slice(-4);
    renderRefPick();
  };
}

// ---------------------------------------------------------------- generating
function request(extra = {}) {
  return {
    product: S.product.id, place: S.place, scene: S.scene, family: S.family, quality: S.quality,
    variations: S.variations, seed: S.seed === '' ? null : +S.seed, product_mode: S.mode, output_long: S.outLong,
    refs: S.refs, prompt: S.custom ? S.customText : null, ...extra,
  };
}

$('#btnGenerate').addEventListener('click', async () => {
  if (!S.product) return;
  $('#btnGenerate').disabled = true;
  try {
    const r = await api('/ea/api/jobs', { json: request() });
    for (const j of r.jobs) runJob(j, $('#sessionStrip'), true);
  } catch (e) { toast(e.message, true); }
  finally { updateGenerate(); }
});

const FAMILY_SHORT = { flux3: 'FLUX 3', qwen: 'Qwen 2511', hidream: 'HiDream O1' };

// queue each variation of a job and keep a card up to date for it
function runJob(j, container, prepend = false, cardWidth) {
  const job = j.job;
  j.prompts.forEach((prompt, v) => {
    const card = document.createElement('div');
    card.className = 'card';
    if (cardWidth) card.style.width = cardWidth;
    card.innerHTML = `<div class="ph" style="aspect-ratio:${job.output[0]} / ${job.output[1]}"><div class="state">Waiting in the queue</div><div class="bar"><span></span></div></div>
      <div class="cap">${esc(FAMILY_SHORT[job.family] || job.family)} · seed ${job.seed + v}</div>`;
    if (prepend) container.prepend(card); else container.append(card);
    const st = $('.state', card), bar = $('.bar span', card);
    let pid = null;
    const loaders = new Set(['UNETLoader', 'CLIPLoader', 'VAELoader', 'CheckpointLoaderSimple']);
    comfy.queue(prompt, {
      onNode: (node) => {
        if (node === 'start') { st.textContent = 'Starting'; return; }
        const cls = prompt[node]?.class_type || '';
        st.textContent = loaders.has(cls) ? 'Loading the model' : cls.includes('Encode') ? 'Reading the prompt' : cls === 'TextGenerate' ? 'Writing the prompt' : cls === 'EAFinish' ? 'Putting the product back' : cls.startsWith('KSampler') || cls === 'SamplerCustom' ? 'Drawing' : st.textContent;
      },
      onProgress: (value, max) => { bar.style.width = ((100 * value) / max).toFixed(1) + '%'; st.textContent = `Drawing: step ${value} of ${max}`; },
      onOutput: (node, out) => {
        for (const res of out.ea_results || []) {
          card.innerHTML = `<div class="ph" style="aspect-ratio:${job.output[0]} / ${job.output[1]}"><img src="${res.thumb}" alt=""></div><div class="cap">${esc(FAMILY_SHORT[res.family] || res.family)} · seed ${res.seed}</div>`;
          card.onclick = () => openViewer(res.id);
        }
      },
      onDone: () => {},
      onError: (msg) => { card.classList.add('err'); st.textContent = msg; bar.parentElement.hidden = true; },
    }).then((id) => { pid = id; }).catch((e) => { card.classList.add('err'); st.textContent = e.message; });
  });
}

// ---------------------------------------------------------------- the viewer
let viewing = null;
async function openViewer(rid) {
  const all = (await api('/ea/api/results?limit=2000')).results;
  const r = all.find((x) => x.rid === rid);
  if (!r) return;
  viewing = r;
  const show = (k) => {
    const img = $('#vImg');
    img.src = r.urls[k === 'parts' ? 'parts' : k === 'raw' ? 'raw' : 'final'];
    img.classList.toggle('parts', k === 'parts');
  };
  segStatic($('#segViewer'), 'final', show);
  show('final');
  $('#vTitle').textContent = `${r.product_name || ''} · ${FAMILY_SHORT[r.family] || r.family} · seed ${r.seed}`;
  $('#vDownload').href = r.urls.final; $('#vDownload').download = r.result + '.png';
  $('#vDownloadParts').hidden = !r.urls.parts;
  $('#segViewer button[data-v="parts"]').hidden = !r.urls.parts;
  if (r.urls.parts) { $('#vDownloadParts').href = r.urls.parts; $('#vDownloadParts').download = r.result + '-parts.png'; }
  const sc = r.scene || {};
  $('#vInfo').innerHTML = `
    <p><span class="k">File</span><br>data/results/${esc(r.rid)}.png</p>
    <p><span class="k">Model</span><br>${esc(S.status?.models?.[r.family]?.name || r.family)}, ${esc(r.quality)}; seed ${r.seed}</p>
    <p><span class="k">Size</span><br>${r.output[0]} × ${r.output[1]} px (the model drew at ${r.frame[0]} × ${r.frame[1]})</p>
    <p><span class="k">The product</span><br>${r.product_mode === 'reference' ? 'Drawn by the model from the photo (worn gear): close, not exact' : r.product_mode === 'relit' ? 'Exact detail, the scene\'s light' : 'Exact pixels'}</p>
    <p><span class="k">Prompt</span><br>${esc(r.prompt)}</p>
    ${r.negative ? `<p><span class="k">Avoid</span><br>${esc(r.negative)}</p>` : ''}
    <p class="hint">The parts map paints the product in Product red for Tuned by part: open both there, or crop them the same way first.</p>`;
  $('#viewer').showModal();
}
$('#vClose').addEventListener('click', () => $('#viewer').close());
$('#vReuse').addEventListener('click', async () => {
  const r = viewing; if (!r) return;
  $('#viewer').close();
  showTab('make');
  if (r.product && r.product !== S.product?.id) await selectProduct(r.product, { quiet: true });
  S.scene = { ...S.scene, ...(r.scene || {}) }; S.place = { ...S.place, ...(r.place || {}) };
  S.family = r.family; S.quality = r.quality; S.seed = String(r.seed); $('#inSeed').value = S.seed;
  renderScene(); renderModels(); syncAspect(S.place.aspect); stage.setPlace(S.place); sceneChanged();
  toast('Settings loaded, seed included.');
});
$('#vDelete').addEventListener('click', async () => {
  const r = viewing; if (!r || !confirm('Delete this picture and its files?')) return;
  const [day, name] = r.rid.split('/');
  await api(`/ea/api/results/${day}/${name}`, { method: 'DELETE' });
  $('#viewer').close(); loadResults();
});

// ---------------------------------------------------------------- results
async function loadResults() {
  const r = await api('/ea/api/results?limit=2000');
  const prodSel = $('#selResultProduct'), modSel = $('#selResultModel');
  const prods = [...new Map(r.results.map((x) => [x.product, x.product_name])).entries()];
  const keepP = prodSel.value, keepM = modSel.value;
  prodSel.innerHTML = '<option value="">Every product</option>' + prods.map(([id, n]) => `<option value="${id}">${esc(n)}</option>`).join('');
  modSel.innerHTML = '<option value="">Every model</option>' + FAMILY_ORDER.map((f) => `<option value="${f}">${FAMILY_SHORT[f]}</option>`).join('');
  prodSel.value = keepP; modSel.value = keepM;
  const list = r.results.filter((x) => (!prodSel.value || x.product === prodSel.value) && (!modSel.value || x.family === modSel.value));
  $('#resultsCount').textContent = `${list.length} picture${list.length === 1 ? '' : 's'}`;
  $('#gallery').innerHTML = list.map((x) => `<div class="card" data-rid="${esc(x.rid)}"><div class="ph" style="aspect-ratio:${x.output[0]} / ${x.output[1]}"><img loading="lazy" src="${x.urls.thumb}" alt=""></div>
    <div class="cap">${esc(x.product_name || '')} · ${esc(FAMILY_SHORT[x.family] || x.family)} · ${esc(x.scene?.preset || x.scene?.pose || '')}</div></div>`).join('');
  $('#gallery').onclick = (e) => { const c = e.target.closest('.card'); if (c) openViewer(c.dataset.rid); };
}
$('#selResultProduct').addEventListener('change', loadResults);
$('#selResultModel').addEventListener('change', loadResults);
$('#btnOpenFolder').addEventListener('click', () => toast(`The pictures are in ${S.status?.data || 'the data folder'}\\results, one folder per day.`));

// ---------------------------------------------------------------- compare
let cmpPresets = recall('cmpPresets', ['cover', 'guard', 'table']);
let cmpModels = recall('cmpModels', FAMILY_ORDER);
function renderCompareSetup() {
  if (!S.options) return;
  const presets = presetsFor(S.product);
  seg($('#cmpPresets'), presets.map((p) => ({ id: p.id, label: p.label })), cmpPresets, (v, sync) => {
    cmpPresets = cmpPresets.includes(v) ? cmpPresets.filter((x) => x !== v) : [...cmpPresets, v]; sync(cmpPresets); store('cmpPresets', cmpPresets);
  }, { multi: true });
  const st = S.status?.models || {};
  seg($('#cmpModels'), FAMILY_ORDER.map((f) => ({ id: f, label: (st[f]?.name || f) + (st[f]?.ready ? '' : ' (not downloaded)'), disabled: !st[f]?.ready })), cmpModels, (v, sync) => {
    cmpModels = cmpModels.includes(v) ? cmpModels.filter((x) => x !== v) : [...cmpModels, v]; sync(cmpModels); store('cmpModels', cmpModels);
  }, { multi: true });
  $('#cmpHint').textContent = S.product ? `Product: ${S.product.name}` : 'Choose a product under Make first.';
  loadBatches();
}
async function loadBatches() {
  const r = await api('/ea/api/results?limit=2000');
  const batches = [...new Set(r.results.map((x) => x.batch).filter((b) => b && b.startsWith('cmp-')))];
  $('#cmpBatches').innerHTML = batches.map((b) => `<button type="button" data-v="${esc(b)}">${esc(b.replace('cmp-', '').replace(/T/, ' '))}</button>`).join('') || '<span class="hint">None yet.</span>';
  $('#cmpBatches').onclick = (e) => { const b = e.target.closest('button'); if (b) showBatch(b.dataset.v, r.results); };
}
function showBatch(batch, results) {
  const list = results.filter((x) => x.batch === batch);
  const presets = [...new Set(list.map((x) => x.scene?.preset))];
  const fams = FAMILY_ORDER.filter((f) => list.some((x) => x.family === f));
  const head = fams.map((f) => `<th>${esc(S.status?.models?.[f]?.name || f)}</th>`).join('');
  const rows = presets.map((p) => `<tr><th class="rowh">${esc(S.options.presets.find((x) => x.id === p)?.label || p)}</th>${fams.map((f) => `<td><div class="cmp-cell">${list.filter((x) => x.scene?.preset === p && x.family === f).sort((a, b) => a.seed - b.seed).map((x) => `<div class="card" data-rid="${esc(x.rid)}"><div class="ph" style="aspect-ratio:${x.output[0]} / ${x.output[1]}"><img loading="lazy" src="${x.urls.thumb}" alt=""></div><div class="cap">seed ${x.seed}</div></div>`).join('')}</div></td>`).join('')}</tr>`).join('');
  $('#cmpGrid').innerHTML = `<table class="cmp-table"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
  $('#cmpGrid').onclick = (e) => { const c = e.target.closest('.card[data-rid]'); if (c) openViewer(c.dataset.rid); };
}
$('#btnCompare').addEventListener('click', async () => {
  if (!S.product?.cutout) { toast('Choose a product under Make first.', true); return; }
  const fams = cmpModels.filter((f) => S.status?.models?.[f]?.ready);
  if (!fams.length || !cmpPresets.length) { toast('Pick at least one scene and one downloaded model.', true); return; }
  const batch = 'cmp-' + new Date().toISOString().slice(0, 16);
  const seeds = +$('#cmpSeeds').value, quality = $('#cmpQuality').value;
  const seed = S.seed === '' ? Math.floor(Math.random() * 1e9) : +S.seed;
  const table = document.createElement('table'); table.className = 'cmp-table';
  table.innerHTML = `<thead><tr><th></th>${fams.map((f) => `<th>${esc(S.status.models[f].name)}</th>`).join('')}</tr></thead><tbody></tbody>`;
  $('#cmpGrid').innerHTML = ''; $('#cmpGrid').append(table);
  for (const pid of cmpPresets) {
    const pr = S.options.presets.find((p) => p.id === pid); if (!pr) continue;
    const place = pr.mode === 'reference' ? { ...S.place, aspect: pr.layout.aspect } : (await api(`/ea/api/products/${S.product.id}/place?preset=${pid}`)).place;
    const sceneP = { ...S.scene, ...pr.scene, preset: pid, place_text: '', extra: '' };
    const r = await api('/ea/api/jobs', { json: request({ families: fams, scene: sceneP, place, variations: seeds, seed, quality, batch, prompt: null, refs: [] }) });
    const tr = document.createElement('tr');
    tr.innerHTML = `<th class="rowh">${esc(pr.label)}</th>` + fams.map(() => '<td><div class="cmp-cell"></div></td>').join('');
    $('tbody', table).append(tr);
    r.jobs.forEach((j, i) => runJob(j, $$('.cmp-cell', tr)[i], false, '200px'));
  }
  toast('The comparison is in the queue. It takes a while: each model loads in turn.');
});

// ---------------------------------------------------------------- references
const RIGHTS = { own: 'My own photograph', cc0: 'Public domain or CC0', 'cc-by': 'Creative Commons with credit', licensed: 'Licensed for this use', unknown: 'Unknown: not for training' };
async function loadReferences() {
  S.references = (await api('/ea/api/references')).references;
  renderRefPick();
  $('#refList').innerHTML = S.references.map((r) => `<div class="ref" data-id="${r.id}">
    <img src="${dataUrl(`references/${r.id}/thumb.jpg`)}" alt="">
    <div class="fields">
      <input data-k="title" value="${esc(r.title)}" placeholder="Title">
      <input data-k="creator" value="${esc(r.creator)}" placeholder="Who made it">
      <input data-k="licence" value="${esc(r.licence)}" placeholder="Licence (e.g. CC BY 2.0)">
      <input data-k="source" value="${esc(r.source)}" placeholder="Where it came from (a link)">
      <select data-k="rights">${Object.entries(RIGHTS).map(([k, l]) => `<option value="${k}" ${k === r.rights ? 'selected' : ''}>${l}</option>`).join('')}</select>
    </div>
    <div class="acts"><label class="chk mini"><input type="checkbox" data-k="train" ${r.train ? 'checked' : ''} ${r.rights === 'unknown' ? 'disabled' : ''}> Use for training</label>
      <button class="btn small" type="button" data-del>Remove</button></div></div>`).join('');
}
$('#refList').addEventListener('change', async (e) => {
  const card = e.target.closest('.ref'); const k = e.target.dataset.k; if (!card || !k) return;
  const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
  try { await api('/ea/api/references/' + card.dataset.id, { json: { [k]: val } }); if (k === 'rights') loadReferences(); } catch (err) { toast(err.message, true); }
});
$('#refList').addEventListener('click', async (e) => {
  if (!e.target.matches('[data-del]')) return;
  const card = e.target.closest('.ref');
  if (!confirm('Remove this reference?')) return;
  await api('/ea/api/references/' + card.dataset.id, { method: 'DELETE' }); loadReferences();
});
$('#fileRefs').addEventListener('change', async (e) => {
  for (const f of e.target.files) {
    const fd = new FormData(); fd.append('file', f, f.name); fd.append('title', f.name.replace(/\.[^.]+$/, '')); fd.append('rights', 'unknown');
    try { await api('/ea/api/references', { method: 'POST', body: fd }); } catch (err) { toast(err.message, true); }
  }
  e.target.value = ''; loadReferences();
});

// ---------------------------------------------------------------- models and status
async function refreshStatus() {
  try { S.status = await api('/ea/api/status'); } catch { return; }
  renderModels();
  const st = S.status, sys = st.system || {}, gpu = st.gpu || {};
  $('#sysFacts').innerHTML = [
    ['Graphics', gpu.name ? `${gpu.name}, ${gpu.vram_gb} GB` : (sys.gpu || 'not found')],
    ['Driver', sys.driver || '—'], ['PyTorch', gpu.torch ? `${gpu.torch}, CUDA ${gpu.cuda || '—'}` : '—'],
    ['Memory', sys.ram_gb ? sys.ram_gb + ' GB' : '—'], ['Folder', esc(st.root || '—')], ['Version', esc(st.version)],
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
  $('#familyList').innerHTML = FAMILY_ORDER.map((f) => {
    const m = st.models[f]; if (!m) return '';
    const missing = Object.entries(m.files).filter(([, ok]) => !ok).map(([k]) => k);
    return `<div class="fam"><div class="h"><span>${esc(m.name)} <span class="hint">· ${esc(m.maker)}</span></span><span class="${m.ready ? 'ok' : 'missing'}">${m.ready ? 'Ready' : 'Missing: ' + missing.join(', ')}</span></div><div class="hint">${esc(m.licence)}</div></div>`;
  }).join('');
  const dls = st.downloads || {};
  $('#helperList').innerHTML = Object.entries(st.models._helpers || {}).map(([k, h]) => {
    const d = dls[k];
    const state = h.ready ? 'Ready' : d ? (d.state === 'running' ? `${gb(d.done)} of ${gb(d.size)}` : d.state === 'error' ? d.error : d.state) : '';
    return `<div class="dl"><span>${esc(h.label)} <span class="hint">· ${esc(h.licence)}</span></span><span class="st">${h.ready ? 'Ready' : `<button class="btn small" data-dl="${k}" type="button" ${d?.state === 'running' ? 'disabled' : ''}>Download</button>`} ${esc(state === 'Ready' ? '' : state)}</span>
      ${d && d.state === 'running' ? `<div class="bar"><span style="width:${((100 * d.done) / d.size).toFixed(1)}%"></span></div>` : ''}</div>`;
  }).join('');
  $('#installList').innerHTML = (st.install_files || []).map((f) => `<div class="dl"><span>${esc(f.label)}${f.optional ? ' <span class="hint">(optional)</span>' : ''}</span>
    <span class="st">${f.ready ? 'Ready' : f.downloaded ? `${gb(f.downloaded)} of ${gb(f.size)}` : gb(f.size)}</span>
    <div class="bar"><span style="width:${f.size ? ((100 * f.downloaded) / f.size).toFixed(1) : 0}%"></span></div></div>`).join('');
  $('#tokenState').textContent = st.token ? 'A token is saved.' : 'No token saved.';
}
$('#helperList').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-dl]'); if (!b) return;
  try { await api('/ea/api/models/download', { json: { key: b.dataset.dl } }); refreshStatus(); } catch (err) { toast(err.message, true); }
});
$('#btnToken').addEventListener('click', async () => {
  const r = await api('/ea/api/token', { json: { token: $('#inToken').value } });
  $('#inToken').value = ''; toast(r.message, !r.ok); refreshStatus();
});
$('#btnRestart').addEventListener('click', async () => {
  if (!confirm('Restart the generator? Pictures in the queue are dropped.')) return;
  await api('/ea/api/restart', { json: {} }).catch(() => {});
  toast('Restarting… the page reconnects by itself.');
});
setInterval(() => { if (!$('#tab-models').hidden || !S.status || FAMILY_ORDER.some((f) => !S.status.models?.[f]?.ready)) refreshStatus(); }, 5000);

// ---------------------------------------------------------------- panel width
(() => {
  const sp = $('#splitter'), root = document.documentElement;
  const w0 = recall('panelW', 420); root.style.setProperty('--panel-w', w0 + 'px');
  sp.addEventListener('pointerdown', (e) => {
    sp.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const move = (ev) => { const w = Math.max(320, Math.min(760, window.innerWidth - ev.clientX)); root.style.setProperty('--panel-w', w + 'px'); stage.layout(); };
    const up = () => { document.body.classList.remove('resizing'); sp.removeEventListener('pointermove', move); store('panelW', parseInt(getComputedStyle(root).getPropertyValue('--panel-w'), 10)); };
    sp.addEventListener('pointermove', move); sp.addEventListener('pointerup', up, { once: true });
  });
})();

// ---------------------------------------------------------------- start
(async function start() {
  Object.assign(S.scene, recall('scene', {}));
  S.family = recall('family', null); S.quality = recall('quality', 'final'); S.variations = recall('variations', 2);
  S.mode = recall('mode', 'exact'); S.outLong = recall('outLong', 2400);
  $('#selVariations').value = String(S.variations);
  segStatic($('#segMode'), S.mode, (v) => { S.mode = v; store('mode', v); });
  segStatic($('#segOut'), String(S.outLong), (v) => { S.outLong = +v; store('outLong', S.outLong); });
  segStatic($('#segQuality'), S.quality, (v) => { S.quality = v; store('quality', v); });
  syncAspect(S.place.aspect); stage.setPlace(S.place);
  for (let i = 0; i < 60 && !S.options; i++) {
    try { S.options = await api('/ea/api/options'); } catch { await new Promise((r) => setTimeout(r, 2000)); }
  }
  await refreshStatus();
  renderScene(); sceneChanged();
  await loadProducts().catch((e) => toast(e.message, true));
  loadReferences().catch(() => {});
  showTab(recall('tab', 'make'));
})();
