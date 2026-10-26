// The frame: the product's cut-out drawn where it will sit, moved, sized and turned by hand.
// The maths matches ea_scene/composite.py: photo point p goes to centre + R(rotation) * flip * s * (p - pc),
// with s = length * frameHeight / (the product box's long side).

const ASPECTS = { '1:1': [1, 1], '4:5': [4, 5], '5:4': [5, 4], '3:2': [3, 2], '2:3': [2, 3], '16:9': [16, 9], '9:16': [9, 16] };

export class Stage {
  constructor(frameEl, canvasEl, wrapEl, onChange) {
    this.frame = frameEl; this.canvas = canvasEl; this.wrap = wrapEl; this.onChange = onChange;
    this.ctx = canvasEl.getContext('2d');
    this.place = { aspect: '4:5', cx: 0.5, cy: 0.5, length: 0.8, rotation: 0, flip: false };
    this.product = null; this.img = null; this.cover = null; this.showCover = true;
    this.drag = null;
    new ResizeObserver(() => this.layout()).observe(wrapEl);
    this.bind();
  }

  setProduct(product, img, coverImg) { this.product = product; this.img = img; this.cover = coverImg; this.draw(); }
  setPlace(place) { this.place = { ...this.place, ...place }; this.layout(); }

  aspect() { return ASPECTS[this.place.aspect] || [4, 5]; }

  layout() {
    const [aw, ah] = this.aspect();
    const r = this.wrap.getBoundingClientRect();
    const pad = 36;
    const W = Math.max(50, r.width - pad), H = Math.max(50, r.height - pad);
    let w = W, h = (W * ah) / aw;
    if (h > H) { h = H; w = (H * aw) / ah; }
    this.frame.style.width = Math.round(w) + 'px';
    this.frame.style.height = Math.round(h) + 'px';
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(w * dpr); this.canvas.height = Math.round(h * dpr);
    this.fw = w; this.fh = h; this.dpr = dpr;
    this.draw();
  }

  // photo pixels -> frame (CSS px)
  transform() {
    const p = this.product; if (!p?.cutout) return null;
    const [x0, y0, x1, y1] = p.cutout.box;
    const long = Math.max(x1 - x0, y1 - y0, 1);
    return {
      pcx: (x0 + x1) / 2, pcy: (y0 + y1) / 2,
      s: (this.place.length * this.fh) / long,
      th: (this.place.rotation * Math.PI) / 180,
      cx: this.place.cx * this.fw, cy: this.place.cy * this.fh,
      flip: !!this.place.flip,
    };
  }

  draw() {
    const c = this.ctx, d = this.dpr || 1;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.canvas.width, this.canvas.height);
    c.scale(d, d);
    // thirds, faintly
    c.strokeStyle = 'rgba(31,27,22,0.10)'; c.lineWidth = 1;
    for (const f of [1 / 3, 2 / 3]) {
      c.beginPath(); c.moveTo(f * this.fw, 0); c.lineTo(f * this.fw, this.fh); c.stroke();
      c.beginPath(); c.moveTo(0, f * this.fh); c.lineTo(this.fw, f * this.fh); c.stroke();
    }
    const t = this.transform();
    if (!t || !this.img) return;
    const pv = this.product.preview;
    const [bx0, by0, bx1, by1] = pv.box;
    c.save();
    c.translate(t.cx, t.cy);
    c.rotate(t.th);
    c.scale(t.flip ? -t.s : t.s, t.s);
    c.translate(-t.pcx, -t.pcy);
    c.drawImage(this.img, bx0, by0, bx1 - bx0, by1 - by0);
    if (this.cover && this.showCover && this.product.cover) {
      c.globalAlpha = 0.55;
      c.drawImage(this.cover, bx0, by0, bx1 - bx0, by1 - by0);
      c.globalAlpha = 1;
    }
    c.restore();
    // the cut ends of a product cropped by its photo's edge
    const open = this.product.cutout.open_edges || [];
    if (open.length) {
      c.fillStyle = 'rgba(170,54,17,0.9)'; c.font = '500 13px Cabin, sans-serif';
      c.fillText('This photo cuts the product off at its ' + open.join(' and ') + ' edge: keep that end at the frame\'s edge.', 10, 20);
    }
  }

  bind() {
    const el = this.frame;
    const pts = new Map();
    const local = (e) => { const r = el.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    el.addEventListener('pointerdown', (e) => {
      if (!this.product) return;
      el.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, local(e));
      const [x, y] = local(e);
      this.drag = { x, y, place: { ...this.place }, rotate: e.shiftKey, pinch: null };
      if (pts.size === 2) this.drag.pinch = this.pinchState(pts);
      el.classList.add('dragging');
    });
    el.addEventListener('pointermove', (e) => {
      if (!this.drag || !pts.has(e.pointerId)) return;
      pts.set(e.pointerId, local(e));
      const d = this.drag;
      if (pts.size === 2 && d.pinch) {
        const now = this.pinchState(pts);
        this.place.length = clamp(d.place.length * (now.dist / d.pinch.dist), 0.05, 2.5);
        this.place.rotation = norm(d.place.rotation + ((now.ang - d.pinch.ang) * 180) / Math.PI);
      } else {
        const [x, y] = local(e);
        if (d.rotate) {
          const cx = d.place.cx * this.fw, cy = d.place.cy * this.fh;
          const a0 = Math.atan2(d.y - cy, d.x - cx), a1 = Math.atan2(y - cy, x - cx);
          let rot = d.place.rotation + ((a1 - a0) * 180) / Math.PI;
          if (e.altKey === false) rot = Math.round(rot * 2) / 2;
          this.place.rotation = norm(rot);
        } else {
          this.place.cx = d.place.cx + (x - d.x) / this.fw;
          this.place.cy = d.place.cy + (y - d.y) / this.fh;
        }
      }
      this.draw(); this.onChange?.(this.place, false);
    });
    const end = (e) => {
      pts.delete(e.pointerId);
      if (pts.size === 0 && this.drag) { this.drag = null; el.classList.remove('dragging'); this.onChange?.(this.place, true); }
    };
    el.addEventListener('pointerup', end); el.addEventListener('pointercancel', end);
    el.addEventListener('wheel', (e) => {
      if (!this.product) return;
      e.preventDefault();
      const k = Math.exp(-e.deltaY * 0.0015);
      this.place.length = clamp(this.place.length * k, 0.05, 2.5);
      this.draw(); this.onChange?.(this.place, true);
    }, { passive: false });
  }

  pinchState(pts) {
    const [a, b] = [...pts.values()];
    return { dist: Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, ang: Math.atan2(b[1] - a[1], b[0] - a[0]) };
  }
}

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
function norm(d) { return ((((d + 180) % 360) + 360) % 360) - 180; }
