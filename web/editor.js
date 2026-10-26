// A mask editor: brush and lasso to add or remove, zoom and move, undo. Used for the product's
// cut-out and for the parts hands may cover.

const $ = (s) => document.querySelector(s);

export async function editMask({ title, hint, photo, mask, under = null, colour = [217, 71, 43], snap = true, allowClear = false }) {
  const dlg = $('#editor'), area = $('#edArea'), cv = $('#edCanvas');
  $('#edTitle').textContent = title;
  $('#edHint').textContent = hint || 'Brush (B) or Lasso (L) to paint; X switches Add and Remove; scroll to zoom; hold Space or use Move (H) to move the photo; Cmd/Ctrl+Z to undo.';
  $('#edSnapWrap').hidden = !snap;
  $('#edClear').hidden = !allowClear;
  const [img, mimg, uimg] = await Promise.all([load(photo), mask ? load(mask) : null, under ? load(under) : null]);
  const W = img.naturalWidth, H = img.naturalHeight;
  const mc = document.createElement('canvas'); mc.width = W; mc.height = H;
  const mx = mc.getContext('2d', { willReadFrequently: true });
  if (mimg) {
    mx.drawImage(mimg, 0, 0, W, H);
    const d = mx.getImageData(0, 0, W, H), a = d.data;
    for (let i = 0; i < a.length; i += 4) { const v = a[i]; a[i] = 255; a[i + 1] = 255; a[i + 2] = 255; a[i + 3] = v; }
    mx.putImageData(d, 0, 0);
  }
  let underCanvas = null;
  if (uimg) {
    underCanvas = document.createElement('canvas'); underCanvas.width = W; underCanvas.height = H;
    const ux = underCanvas.getContext('2d');
    ux.drawImage(uimg, 0, 0, W, H);
    const d = ux.getImageData(0, 0, W, H), a = d.data;
    for (let i = 0; i < a.length; i += 4) { const v = a[i]; a[i] = 0; a[i + 1] = 0; a[i + 2] = 0; a[i + 3] = 150 - (v * 150) / 255; }
    ux.putImageData(d, 0, 0);
  }
  const tint = document.createElement('canvas'); tint.width = W; tint.height = H;
  const tx = tint.getContext('2d');
  const ctx = cv.getContext('2d');

  let view = { s: 1, x: 0, y: 0 };
  let tool = 'brush', mode = 'add', size = +$('#edSize').value;
  let poly = null, cursor = null, painting = false, space = false, panning = null;
  const undo = [];
  const pushUndo = () => { undo.push(mx.getImageData(0, 0, W, H)); if (undo.length > 30) undo.shift(); };

  function fit() {
    const r = area.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    const s = Math.min(r.width / W, r.height / H) * 0.96;
    view = { s, x: (r.width - W * s) / 2, y: (r.height - H * s) / 2 };
    render();
  }
  function retint() {
    tx.globalCompositeOperation = 'copy'; tx.drawImage(mc, 0, 0);
    tx.globalCompositeOperation = 'source-in'; tx.fillStyle = `rgb(${colour.join(',')})`; tx.fillRect(0, 0, W, H);
    tx.globalCompositeOperation = 'source-over';
  }
  function render() {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.setTransform(dpr * view.s, 0, 0, dpr * view.s, dpr * view.x, dpr * view.y);
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, 0, 0);
    if (underCanvas) ctx.drawImage(underCanvas, 0, 0);
    ctx.globalAlpha = 0.5; ctx.drawImage(tint, 0, 0); ctx.globalAlpha = 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (poly && poly.length) {
      ctx.strokeStyle = mode === 'add' ? '#1F1B16' : '#AA3611'; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
      ctx.beginPath();
      poly.forEach(([x, y], i) => { const [sx, sy] = toScreen(x, y); i ? ctx.lineTo(sx, sy) : ctx.moveTo(sx, sy); });
      if (cursor) { const [sx, sy] = toScreen(cursor[0], cursor[1]); ctx.lineTo(sx, sy); }
      ctx.stroke(); ctx.setLineDash([]);
      const [fx, fy] = toScreen(poly[0][0], poly[0][1]);
      ctx.beginPath(); ctx.arc(fx, fy, 6, 0, Math.PI * 2); ctx.stroke();
    }
    if (cursor && tool === 'brush') {
      const [sx, sy] = toScreen(cursor[0], cursor[1]);
      ctx.strokeStyle = mode === 'add' ? '#1F1B16' : '#AA3611'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(sx, sy, (size / 2) * view.s, 0, Math.PI * 2); ctx.stroke();
    }
  }
  const toScreen = (x, y) => [view.x + x * view.s, view.y + y * view.s];
  const toImage = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left - view.x) / view.s, (e.clientY - r.top - view.y) / view.s]; };
  function dab(x0, y0, x1, y1) {
    mx.globalCompositeOperation = mode === 'add' ? 'source-over' : 'destination-out';
    mx.strokeStyle = '#fff'; mx.fillStyle = '#fff'; mx.lineCap = 'round'; mx.lineWidth = size;
    mx.beginPath(); mx.moveTo(x0, y0); mx.lineTo(x1, y1); mx.stroke();
    mx.globalCompositeOperation = 'source-over';
  }
  function fillPoly(p) {
    mx.globalCompositeOperation = mode === 'add' ? 'source-over' : 'destination-out';
    mx.fillStyle = '#fff'; mx.beginPath();
    p.forEach(([x, y], i) => (i ? mx.lineTo(x, y) : mx.moveTo(x, y)));
    mx.closePath(); mx.fill();
    mx.globalCompositeOperation = 'source-over';
  }
  const setTool = (t) => { tool = t; poly = null; for (const b of document.querySelectorAll('#edTool button')) b.setAttribute('aria-pressed', b.dataset.v === t); area.classList.toggle('hand', t === 'hand'); render(); };
  const setMode = (m) => { mode = m; for (const b of document.querySelectorAll('#edMode button')) b.setAttribute('aria-pressed', b.dataset.v === m); render(); };

  const ac = new AbortController(); const sig = { signal: ac.signal };
  let last = null;
  cv.addEventListener('pointerdown', (e) => {
    cv.setPointerCapture(e.pointerId);
    if (tool === 'hand' || space || e.button === 1) { panning = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; return; }
    const p = toImage(e);
    if (tool === 'brush') { pushUndo(); painting = true; last = p; dab(p[0], p[1], p[0], p[1]); retint(); render(); }
    if (tool === 'lasso') {
      if (!poly) poly = [p];
      else {
        const [fx, fy] = toScreen(poly[0][0], poly[0][1]), [sx, sy] = toScreen(p[0], p[1]);
        if (poly.length > 2 && Math.hypot(fx - sx, fy - sy) < 10) { pushUndo(); fillPoly(poly); poly = null; retint(); }
        else poly.push(p);
      }
      render();
    }
  }, sig);
  cv.addEventListener('pointermove', (e) => {
    if (panning) { view.x = panning.vx + e.clientX - panning.x; view.y = panning.vy + e.clientY - panning.y; render(); return; }
    cursor = toImage(e);
    if (painting) { dab(last[0], last[1], cursor[0], cursor[1]); last = cursor; retint(); }
    render();
  }, sig);
  const up = () => { painting = false; panning = null; };
  cv.addEventListener('pointerup', up, sig); cv.addEventListener('pointercancel', up, sig);
  cv.addEventListener('pointerleave', () => { cursor = null; render(); }, sig);
  cv.addEventListener('dblclick', () => { if (poly && poly.length > 2) { pushUndo(); fillPoly(poly); poly = null; retint(); render(); } }, sig);
  cv.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = cv.getBoundingClientRect(), mxp = e.clientX - r.left, myp = e.clientY - r.top;
    const k = Math.exp(-e.deltaY * 0.0015), s2 = Math.max(0.05, Math.min(40, view.s * k));
    view.x = mxp - ((mxp - view.x) * s2) / view.s; view.y = myp - ((myp - view.y) * s2) / view.s; view.s = s2;
    render();
  }, { passive: false, signal: ac.signal });
  document.addEventListener('keydown', (e) => {
    if (!dlg.open) return;
    if (e.target.tagName === 'INPUT' && e.target.type === 'text') return;
    if (e.key === ' ') { space = true; e.preventDefault(); }
    if (e.key === 'b' || e.key === 'B') setTool('brush');
    if (e.key === 'l' || e.key === 'L') setTool('lasso');
    if (e.key === 'h' || e.key === 'H') setTool('hand');
    if (e.key === 'x' || e.key === 'X') setMode(mode === 'add' ? 'remove' : 'add');
    if (e.key === '[') { size = Math.max(2, size * 0.8); $('#edSize').value = size; render(); }
    if (e.key === ']') { size = Math.min(300, size * 1.25); $('#edSize').value = size; render(); }
    if (e.key === 'Enter' && poly && poly.length > 2) { pushUndo(); fillPoly(poly); poly = null; retint(); render(); }
    if (e.key === 'Escape' && poly) { poly = null; render(); e.preventDefault(); }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); doUndo(); }
  }, sig);
  document.addEventListener('keyup', (e) => { if (e.key === ' ') space = false; }, sig);
  function doUndo() { const d = undo.pop(); if (d) { mx.putImageData(d, 0, 0); retint(); render(); } }
  for (const b of document.querySelectorAll('#edTool button')) b.addEventListener('click', () => setTool(b.dataset.v), sig);
  for (const b of document.querySelectorAll('#edMode button')) b.addEventListener('click', () => setMode(b.dataset.v), sig);
  $('#edSize').addEventListener('input', (e) => { size = +e.target.value; render(); }, sig);
  $('#edUndo').addEventListener('click', doUndo, sig);
  $('#edClear').addEventListener('click', () => { pushUndo(); mx.clearRect(0, 0, W, H); retint(); render(); }, sig);
  const ro = new ResizeObserver(() => fit());

  return new Promise((resolve) => {
    const finish = (val) => { ac.abort(); ro.disconnect(); dlg.close(); resolve(val); };
    $('#edCancel').addEventListener('click', () => finish(null), sig);
    dlg.addEventListener('cancel', (e) => { e.preventDefault(); if (poly) { poly = null; render(); } else finish(null); }, sig);
    $('#edSave').addEventListener('click', async () => {
      const out = document.createElement('canvas'); out.width = W; out.height = H;
      const ox = out.getContext('2d');
      const d = mx.getImageData(0, 0, W, H), a = d.data;
      for (let i = 0; i < a.length; i += 4) { const v = a[i + 3]; a[i] = v; a[i + 1] = v; a[i + 2] = v; a[i + 3] = 255; }
      ox.putImageData(d, 0, 0);
      const blob = await new Promise((r) => out.toBlob(r, 'image/png'));
      finish({ blob, snap: $('#edSnap').checked });
    }, sig);
    dlg.showModal();
    setTool('brush'); setMode('add');
    retint();
    ro.observe(area);
    fit();
  });
}

function load(src) {
  return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('Could not load ' + src)); i.src = src; });
}
