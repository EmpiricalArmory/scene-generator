"""Placing the product on the frame, the masks that tell the model where to draw, and putting the
product's own pixels back on the generated picture.

Placement is kept in fractions of the frame, so the same layout serves every model's frame size and
the final output size:
    cx, cy     centre of the product in the frame (0..1)
    length     the product's long side as a fraction of the frame's height
    rotation   degrees, clockwise
    flip       mirror left to right (changes the product: off by default)
"""
import math

import numpy as np
from scipy import ndimage

from . import imaging
from .util import resize

ASPECTS = {'1:1': (1, 1), '4:5': (4, 5), '5:4': (5, 4), '3:2': (3, 2), '2:3': (2, 3), '16:9': (16, 9), '9:16': (9, 16)}


def frame_size(aspect, megapixels, multiple=32, allowed=None):
    """Width and height near `megapixels` with the aspect, in multiples of `multiple`.

    allowed: a list of (w, h) a model was trained at; the one closest in aspect wins."""
    aw, ah = ASPECTS.get(aspect, (1, 1))
    if allowed:
        target = aw / ah
        return min(allowed, key=lambda s: abs(math.log((s[0] / s[1]) / target)))
    px = megapixels * 1024 * 1024
    h = math.sqrt(px * ah / aw)
    w = h * aw / ah
    w = max(multiple, int(round(w / multiple)) * multiple)
    h = max(multiple, int(round(h / multiple)) * multiple)
    return w, h


def product_box(alpha, thr=0.5):
    ys, xs = np.nonzero(alpha > thr)
    if len(xs) == 0:
        h, w = alpha.shape
        return 0, 0, w, h
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def open_edges(alpha, thr=0.5, margin=2):
    """Which sides of the photo the product runs off (its cut ends must stay at the frame's edge)."""
    a = alpha > thr
    out = []
    if a[:margin].any(): out.append('top')
    if a[-margin:].any(): out.append('bottom')
    if a[:, :margin].any(): out.append('left')
    if a[:, -margin:].any(): out.append('right')
    return out


def long_axis_angle(alpha):
    """The product's long axis in degrees (0 = horizontal), from the mask's second moments."""
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) < 10:
        return 0.0
    step = max(1, len(xs) // 200000)
    xs = xs[::step].astype(np.float64); ys = ys[::step].astype(np.float64)
    xs -= xs.mean(); ys -= ys.mean()
    cov = np.cov(np.stack([xs, ys]))
    vals, vecs = np.linalg.eigh(cov)
    v = vecs[:, int(np.argmax(vals))]
    return math.degrees(math.atan2(v[1], v[0]))


def length_to_width(alpha):
    """How many times longer the product is than it is wide, along its long axis and across it (a sword: its
    length over the span of its cross), from the mask; 0 when it can't tell."""
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) < 50:
        return 0.0
    step = max(1, len(xs) // 300000)
    pts = np.stack([xs[::step], ys[::step]], axis=1).astype(np.float64)
    pts -= pts.mean(axis=0)
    vals, vecs = np.linalg.eigh(np.cov(pts.T))
    along = pts @ vecs[:, int(np.argmax(vals))]
    across = pts @ vecs[:, int(np.argmin(vals))]
    length = np.percentile(along, 99.9) - np.percentile(along, 0.1)
    width = np.percentile(across, 99.9) - np.percentile(across, 0.1)
    return float(length / width) if width > 0 else 0.0


def point_direction(alpha):
    """Direction (degrees, image coordinates: 0 = right, 90 = down) from the product's middle toward its
    thin end: for a sword, the point. The cross is the widest part, and the point is the end farther from it."""
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) < 20:
        return 0.0
    step = max(1, len(xs) // 300000)
    pts = np.stack([xs[::step], ys[::step]], axis=1).astype(np.float64)
    c = pts.mean(axis=0)
    a = math.radians(long_axis_angle(alpha))
    v = np.array([math.cos(a), math.sin(a)]); n = np.array([-v[1], v[0]])
    t = (pts - c) @ v; d = (pts - c) @ n
    bins = 64
    edges = np.linspace(t.min(), t.max() + 1e-6, bins + 1)
    idx = np.clip(np.digitize(t, edges) - 1, 0, bins - 1)
    width = np.zeros(bins)
    for b in range(bins):
        sel = d[idx == b]
        if len(sel):
            width[b] = sel.max() - sel.min()
    widest = (edges[int(np.argmax(width))] + edges[int(np.argmax(width)) + 1]) / 2
    direction = v if (t.max() - widest) > (widest - t.min()) else -v
    return math.degrees(math.atan2(direction[1], direction[0]))


def suggest_cover(alpha):
    """For a sword or trainer: the handle between the cross and the pommel, where hands may cover it."""
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) < 50:
        return np.zeros_like(alpha)
    a = math.radians(point_direction(alpha))
    v = np.array([math.cos(a), math.sin(a)])                      # toward the point
    n = np.array([-v[1], v[0]])
    step = max(1, len(xs) // 300000)
    pts = np.stack([xs[::step], ys[::step]], axis=1).astype(np.float64)
    c = pts.mean(axis=0)
    t = (pts - c) @ v; d = (pts - c) @ n
    t_point, t_end = t.max(), t.min()                              # the point, and the pommel's end
    L = t_point - t_end
    bins = 96
    edges = np.linspace(t_end, t_point + 1e-6, bins + 1)
    idx = np.clip(np.digitize(t, edges) - 1, 0, bins - 1)
    width = np.array([(d[idx == b].max() - d[idx == b].min()) if np.any(idx == b) else 0 for b in range(bins)])
    hilt_half = bins // 2                                          # the cross is in the hilt's half
    b_cross = int(np.argmax(width[:hilt_half + bins // 4]))
    t_cross = (edges[b_cross] + edges[b_cross + 1]) / 2
    grip = width[:b_cross]
    if len(grip) < 4:
        return np.zeros_like(alpha)
    # the pommel: the wider part at the very end; the handle starts where the width drops back to the grip's
    g_w = np.median(grip[len(grip) // 3:])
    b_pommel = 0
    for b in range(min(len(grip), bins // 6)):
        if grip[b] > 1.25 * g_w:
            b_pommel = b + 1
    t0 = edges[b_pommel] + 0.01 * L
    t1 = t_cross - 0.012 * L
    H, W = alpha.shape
    tt = ((np.arange(W, dtype=np.float32) - c[0]) * v[0])[None, :] + ((np.arange(H, dtype=np.float32) - c[1]) * v[1])[:, None]
    cover = ((tt >= t0) & (tt <= t1) & (alpha > 0.02)).astype(np.float32)
    return cover * alpha


TARGETS = {'up': -90.0, 'up-left': -125.0, 'up-right': -55.0, 'diagonal': -50.0, 'left': 180.0, 'right': 0.0}


def auto_place(alpha, layout, frame_aspect=None, margin=0.05):
    """A starting placement from a preset's layout: turn the product so its point faces the preset's way,
    then size it to the preset's length, shrunk if it would not fit inside the frame's margins."""
    aw, ah = ASPECTS.get(layout.get('aspect', frame_aspect or '4:5'), (4, 5))
    want = layout.get('point', 'keep')
    rot = 0.0
    if want in TARGETS:
        rot = TARGETS[want] - point_direction(alpha)
    rot += float(layout.get('tilt', 0.0))
    rot = (rot + 180.0) % 360.0 - 180.0
    box = product_box(alpha)
    bw, bh = box[2] - box[0], box[3] - box[1]
    long_side = max(bw, bh)
    # the product's rotated extent, in units of its long side
    ys, xs = np.nonzero(alpha > 0.5)
    step = max(1, len(xs) // 200000)
    pts = np.stack([xs[::step], ys[::step]], axis=1).astype(np.float64)
    pts -= np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    rx = pts[:, 0] * c - pts[:, 1] * s; ry = pts[:, 0] * s + pts[:, 1] * c
    ext_w = (rx.max() - rx.min()) / long_side; ext_h = (ry.max() - ry.min()) / long_side
    frame_w_in_h = aw / ah
    length = float(layout.get('length', 0.8))
    fit = min((1 - 2 * margin) / max(ext_h, 1e-6), (1 - 2 * margin) * frame_w_in_h / max(ext_w, 1e-6))
    length = min(length, fit)
    # centre the rotated extent, not the box, on the requested point
    cx = float(layout.get('cx', 0.5)) - ((rx.max() + rx.min()) / 2 / long_side) * length / frame_w_in_h
    cy = float(layout.get('cy', 0.5)) - ((ry.max() + ry.min()) / 2 / long_side) * length
    return {'aspect': layout.get('aspect', '4:5'), 'cx': round(cx, 4), 'cy': round(cy, 4), 'length': round(length, 4),
            'rotation': round(rot, 2), 'flip': False}


class Placement:
    """Maps photo pixels to frame pixels for one frame size."""

    def __init__(self, box, place, frame_w, frame_h):
        bx0, by0, bx1, by1 = box
        self.pc = np.array([(bx0 + bx1) / 2.0, (by0 + by1) / 2.0])
        long_side = max(bx1 - bx0, by1 - by0, 1)
        self.s = float(place.get('length', 0.8)) * frame_h / long_side
        self.theta = math.radians(float(place.get('rotation', 0.0)))
        self.flip = bool(place.get('flip', False))
        self.cc = np.array([float(place.get('cx', 0.5)) * frame_w, float(place.get('cy', 0.5)) * frame_h])
        self.w, self.h = int(frame_w), int(frame_h)

    def matrix(self, pre_scale=1.0):
        """2x3 matrix taking (x, y) in a source pre-scaled by pre_scale to the frame."""
        c, s = math.cos(self.theta), math.sin(self.theta)
        R = np.array([[c, -s], [s, c]])
        F = np.diag([-1.0, 1.0]) if self.flip else np.eye(2)
        A = R @ F * (self.s / pre_scale)
        t = self.cc - A @ (self.pc * pre_scale)
        return A, t


def _warp(src, A, t, out_w, out_h, order):
    """Sample src at the frame's pixels (inverse map of x_frame = A x_src + t)."""
    Ai = np.linalg.inv(A)
    # scipy works in (row, col) = (y, x)
    M = np.array([[Ai[1, 1], Ai[1, 0]], [Ai[0, 1], Ai[0, 0]]])
    ti = -Ai @ t
    off = np.array([ti[1], ti[0]])
    if src.ndim == 2:
        return ndimage.affine_transform(src, M, offset=off, output_shape=(out_h, out_w), order=order,
                                        mode='constant', cval=0.0, prefilter=order > 1).astype(np.float32)
    return np.stack([ndimage.affine_transform(src[..., c], M, offset=off, output_shape=(out_h, out_w), order=order,
                                              mode='constant', cval=0.0, prefilter=order > 1)
                     for c in range(src.shape[2])], axis=2).astype(np.float32)


def place_layers(rgb, alpha, cover, place, frame_w, frame_h, box=None, margin=0.03):
    """The product's colour, alpha and cover mask drawn into a frame of frame_w x frame_h."""
    box = box or product_box(alpha)
    P = Placement(box, place, frame_w, frame_h)
    h, w = alpha.shape
    bx0, by0, bx1, by1 = box
    m = int(margin * max(bx1 - bx0, by1 - by0)) + 4
    x0, y0, x1, y1 = max(0, bx0 - m), max(0, by0 - m), min(w, bx1 + m), min(h, by1 + m)
    crop = (slice(y0, y1), slice(x0, x1))
    pre = min(1.0, P.s * 1.25)                     # shrink with an antialiasing filter first
    cw, ch = x1 - x0, y1 - y0
    pw, ph = max(1, int(round(cw * pre))), max(1, int(round(ch * pre)))
    pre_x, pre_y = pw / cw, ph / ch
    layers = {}
    srcs = {'rgb': rgb[crop], 'alpha': alpha[crop]}
    if cover is not None:
        srcs['cover'] = cover[crop]
    for k, a in srcs.items():
        small = resize(a, pw, ph) if pre < 1.0 else a
        layers[k] = small
    # Continuous coordinates (pixel i spans [i, i+1)): frame = A (S u + o) + t for u in the pre-scaled
    # crop, o the crop's origin. In array indices (centres at integers) that adds half-pixel terms.
    A, t = P.matrix(1.0)
    S = np.diag([1.0 / pre_x, 1.0 / pre_y])
    A2 = A @ S
    half = np.array([0.5, 0.5])
    t2 = A2 @ half + A @ np.array([x0, y0], dtype=np.float64) + t - half
    out = {
        'rgb': np.clip(_warp(layers['rgb'], A2, t2, frame_w, frame_h, order=3), 0, 1),
        'alpha': np.clip(_warp(layers['alpha'], A2, t2, frame_w, frame_h, order=1), 0, 1),
    }
    if 'cover' in layers:
        out['cover'] = np.clip(_warp(layers['cover'], A2, t2, frame_w, frame_h, order=1), 0, 1)
    else:
        out['cover'] = np.zeros((frame_h, frame_w), np.float32)
    return out


def model_inputs(rgb, alpha, cover, place, frame_w, frame_h, backdrop, product_hold=0.0, cover_free=1.0):
    """What the model gets: the product on a plain backdrop, and where it may draw (1 = draw).

    product_hold is how free the model is over the product itself: 0 keeps it exactly, a little above
    zero lets the model relight it in the last steps (the detail is put back afterwards)."""
    L = place_layers(rgb, alpha, cover, place, frame_w, frame_h)
    a = L['alpha']
    canvas = backdrop[None, None, :] * (1 - a[..., None]) + L['rgb'] * a[..., None]
    solid = imaging.erode(a > 0.5, 1)
    draw = np.where(solid, float(product_hold), 1.0).astype(np.float32)
    covered = (L['cover'] > 0.5) & (a > 0.02)
    draw = np.where(covered, np.maximum(draw, float(cover_free)), draw)
    draw = imaging.feather(draw, 1.2)
    return np.clip(canvas, 0, 1).astype(np.float32), draw, L


def paste_back(generated, rgb, alpha, cover, place, out_w, out_h, mode='exact', restore_uncovered=True):
    """The final picture: the generated scene at out_w x out_h with the product's own pixels on top.

    mode 'exact' pastes the photo's pixels as they are; 'relit' keeps the photo's detail but takes the
    broad light and colour from the model's version of the product (generated with product_hold > 0)."""
    gen = resize(generated, out_w, out_h) if generated.shape[1] != out_w or generated.shape[0] != out_h else generated
    gen = np.clip(gen, 0, 1)
    L = place_layers(rgb, alpha, cover, place, out_w, out_h)
    a = L['alpha']; prod = L['rgb']; cov = imaging.feather(L['cover'], 1.5)
    if mode == 'relit':
        sig = max(3.0, 0.012 * max(out_w, out_h))
        w = (a > 0.5).astype(np.float32)
        def low(img):
            num = np.stack([ndimage.gaussian_filter(img[..., c] * w, sig) for c in range(3)], axis=2)
            den = ndimage.gaussian_filter(w, sig)[..., None]
            return num / np.maximum(den, 1e-4)
        prod = np.clip(low(gen) + (prod - low(prod)), 0, 1)
    paste = a * (1 - cov)
    if restore_uncovered:
        # inside the may-be-covered parts, bring the photo back wherever the model left the product alone
        diff = np.abs(gen - prod).max(axis=2)
        diff = ndimage.gaussian_filter(diff, 2.0)
        same = np.clip(1 - (diff - 0.05) / 0.06, 0, 1)
        paste = np.maximum(paste, a * cov * imaging.feather(same, 1.0))
    paste = np.clip(paste, 0, 1)[..., None]
    out = gen * (1 - paste) + prod * paste
    return np.clip(out, 0, 1).astype(np.float32), L, paste[..., 0]


PART_COLOURS = {'gear': (0xD9, 0x47, 0x2B), 'kit': (0x2F, 0x6B, 0xD8), 'skin': (0xEF, 0xB0, 0x2E),
                'steel': (0x8B, 0x55, 0xD9), 'place': (0x2E, 0x9E, 0x55)}


def parts_map(product_alpha):
    """A parts map for Tuned by part: the product painted in Product red, the rest left for its auto split."""
    h, w = product_alpha.shape
    out = np.zeros((h, w, 4), np.float32)
    r, g, b = PART_COLOURS['gear']
    m = product_alpha > 0.5
    out[m] = (r / 255, g / 255, b / 255, 1.0)
    return out
