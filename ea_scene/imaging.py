"""Image maths for cut-outs and compositing, on float32 arrays in 0..1 (numpy and scipy only)."""
import numpy as np
from scipy import ndimage

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def luma(rgb):
    return rgb @ LUMA


def box(a, r):
    """Mean over a (2r+1) square window, edges handled by shrinking the window (cumulative sums)."""
    if r <= 0:
        return a.astype(np.float32, copy=True)
    a = a.astype(np.float64)
    h, w = a.shape[:2]
    c = np.cumsum(np.cumsum(np.pad(a, ((1, 0), (1, 0)) + ((0, 0),) * (a.ndim - 2)), axis=0), axis=1)
    y0 = np.clip(np.arange(h) - r, 0, h); y1 = np.clip(np.arange(h) + r + 1, 0, h)
    x0 = np.clip(np.arange(w) - r, 0, w); x1 = np.clip(np.arange(w) + r + 1, 0, w)
    s = c[y1][:, x1] - c[y0][:, x1] - c[y1][:, x0] + c[y0][:, x0]
    n = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    if a.ndim == 3:
        n = n[..., None]
    return (s / n).astype(np.float32)


def guided(guide, src, r, eps):
    """He et al.'s guided filter with a grey guide."""
    mI = box(guide, r); mp = box(src, r)
    cov = box(guide * src, r) - mI * mp
    var = box(guide * guide, r) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return box(a, r) * guide + box(b, r)


def disk(r):
    r = max(1, int(round(r)))
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return (x * x + y * y) <= r * r


def erode(mask, r):
    if r <= 0:
        return mask.copy()
    return ndimage.binary_erosion(mask, structure=disk(r), border_value=0)


def dilate(mask, r):
    if r <= 0:
        return mask.copy()
    return ndimage.binary_dilation(mask, structure=disk(r))


def drop_specks(mask, min_frac=0.0005, keep_largest=False):
    """Remove islands smaller than min_frac of the largest one; optionally keep only the largest."""
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    sizes = ndimage.sum(np.ones_like(mask, dtype=np.float32), lab, index=np.arange(1, n + 1))
    big = sizes.max()
    keep = np.zeros(n + 1, bool)
    if keep_largest:
        keep[1 + int(np.argmax(sizes))] = True
    else:
        keep[1:] = sizes >= max(min_frac * mask.size, 0.02 * big)
    return keep[lab]


def fill_small_holes(mask, max_frac=0.002):
    holes = ndimage.binary_fill_holes(mask) & ~mask
    lab, n = ndimage.label(holes)
    if n == 0:
        return mask
    sizes = ndimage.sum(np.ones_like(mask, dtype=np.float32), lab, index=np.arange(1, n + 1))
    small = np.zeros(n + 1, bool)
    small[1:] = sizes <= max_frac * mask.size
    return mask | small[lab]


def refine_alpha(rgb, coarse, scale_px=None):
    """Snap a coarse product mask to the photo's edges and clean it up.

    coarse: 0..1 at the photo's size (from a model or a hand-drawn mask). The result keeps the
    model's decision away from edges and takes a guided-filter alpha in a thin band along them."""
    h, w = coarse.shape
    diag = float(np.hypot(h, w))
    r = int(scale_px or max(2, round(diag / 1400)))           # ~5 px on a 6000 px photo
    hard = coarse > 0.5
    hard = drop_specks(hard)
    hard = fill_small_holes(hard)
    band = dilate(hard, 2 * r) & ~erode(hard, 2 * r)
    g = luma(rgb)
    soft = guided(g, hard.astype(np.float32), r, 1e-3)
    soft = np.clip((soft - 0.1) / 0.8, 0.0, 1.0)
    alpha = np.where(band, soft, hard.astype(np.float32))
    # the guided filter can creep along low-contrast edges: never past the band
    return np.clip(alpha, 0.0, 1.0).astype(np.float32)


def background_field(rgb, alpha, radius_frac=0.04):
    """The colour behind the product, estimated from the uncovered backdrop and spread smoothly under it."""
    h, w = alpha.shape
    bgw = (alpha < 0.02).astype(np.float32)
    small = max(64, int(max(h, w) / 8))
    sc = small / max(h, w)
    sh, sw = max(8, int(h * sc)), max(8, int(w * sc))
    from .util import resize
    rgb_s = resize(rgb, sw, sh)
    w_s = resize(bgw, sw, sh)
    sigma = max(2.0, radius_frac * max(sh, sw))
    num = np.stack([ndimage.gaussian_filter(rgb_s[..., c] * w_s, sigma) for c in range(3)], axis=2)
    den = ndimage.gaussian_filter(w_s, sigma)[..., None]
    fallback = np.median(rgb[alpha < 0.02], axis=0) if (alpha < 0.02).any() else np.array([1, 1, 1], np.float32)
    field = np.where(den > 1e-3, num / np.maximum(den, 1e-6), fallback[None, None, :])
    return resize(field.astype(np.float32), w, h, resample=2)  # bilinear up


def decontaminate(rgb, alpha, bg=None):
    """Foreground colour at soft edges, with the backdrop's colour taken back out (I = aF + (1-a)B)."""
    if bg is None:
        bg = background_field(rgb, alpha)
    a = alpha[..., None]
    core = (alpha > 0.96).astype(np.float32)
    # the colour of nearby solid product, for where alpha is too small to unmix reliably
    sig = 3.0
    num = np.stack([ndimage.gaussian_filter(rgb[..., c] * core, sig) for c in range(3)], axis=2)
    den = ndimage.gaussian_filter(core, sig)[..., None]
    near = np.where(den > 1e-3, num / np.maximum(den, 1e-6), rgb)
    unmixed = np.clip((rgb - (1 - a) * bg) / np.maximum(a, 1e-3), 0.0, 1.0)
    t = np.clip((alpha - 0.15) / 0.35, 0, 1)[..., None]          # trust unmixing from alpha 0.5 up
    fg = t * unmixed + (1 - t) * near
    edge = (alpha < 0.985)[..., None]
    return np.where(edge, fg, rgb).astype(np.float32)


def feather(alpha, sigma):
    if sigma <= 0:
        return alpha
    return np.clip(ndimage.gaussian_filter(alpha, sigma), 0, 1).astype(np.float32)


def white_sweep_alpha(rgb):
    """A classical cut-out for gear shot on a light seamless backdrop (no model needed).

    Works on difference from the smooth backdrop, so soft shadows stay out of the product. Bright steel
    that matches the backdrop is the weak spot; the model-based cut-out handles that better."""
    h, w = rgb.shape[:2]
    lum = luma(rgb)
    # the backdrop: a heavy median at low resolution, then blurred
    from .util import resize
    s = 256 / max(h, w)
    small = resize(rgb, max(16, int(w * s)), max(16, int(h * s)))
    med = np.stack([ndimage.median_filter(small[..., c], size=31) for c in range(3)], axis=2)
    med = np.stack([ndimage.gaussian_filter(med[..., c], 6) for c in range(3)], axis=2)
    bg = resize(med.astype(np.float32), w, h, resample=2)
    diff = np.abs(rgb - bg).max(axis=2)
    dl = luma(bg) - lum                                           # darker than the backdrop
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    score = np.maximum(diff * 1.0, np.maximum(dl, 0) * 0.6) + sat * 0.5
    # shadows: darker but the same hue as the backdrop and soft; keep only strong differences
    hard = score > 0.10
    hard = ndimage.binary_opening(hard, structure=disk(1))
    hard = drop_specks(hard, keep_largest=False)
    hard = fill_small_holes(hard, 0.01)
    return hard.astype(np.float32)
