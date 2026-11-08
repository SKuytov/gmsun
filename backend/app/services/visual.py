"""Server-side renders of a layout.

* ``render_plan``  – rectified plan view (metre grid, roof outline, obstacles, numbered modules) → ``render_path``
* ``render_photo`` – photorealistic overlay: the modules are drawn in plane space (frame, glass, cell grid,
  specular highlight that follows the photo's lighting, soft shadow) and warped with the plane homography onto the
  original photo → ``visual_path``
* ``render_rect``  – rectified photo of the plane (used as roof texture in the 3D scene) → ``rect_path``

Everything is generated from the stored geometry, so the PDF, the 3D view and the client visualisation stay in
sync with the layout without the browser having to upload a canvas.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CatalogItem, Layout
from .module_fit import module_dims_m

FONT_PATHS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"]
FONT_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
PLAN_PX = 1400  # longest side of the plan render

FRAME_COLOURS = {"black": (18, 18, 20), "silver": (168, 172, 178)}
ROOF_COLOURS = {  # fallback roof colours by type (RGB)
    "tile": (173, 88, 62), "tile_xt": (173, 88, 62), "tile_xtr": (173, 88, 62), "plain_tile": (150, 70, 55),
    "lt_sheet": (142, 148, 156), "lt_sheet_ts": (142, 148, 156), "standing_seam": (110, 116, 124), "sandwich": (190, 194, 200),
    "fibre_cement": (128, 128, 122), "flat_concrete": (150, 148, 142), "flat_ew": (150, 148, 142), "flat_bifacial": (120, 140, 90),
    "ground_ballast": (112, 134, 78), "ground": (112, 134, 78),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in (FONT_BOLD if bold else FONT_PATHS):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _panel_dims(db: Session, lay: Layout) -> tuple[float, float, int, float]:
    panel = db.get(CatalogItem, lay.panel_item_id) if lay.panel_item_id else None
    sp = (panel.specs or {}) if panel else {}
    w, h, _est = module_dims_m(sp)
    cells = int(float(sp.get("cells") or 0) or 0)
    return w, h, cells, float(sp.get("wp") or 0)


def _cells_grid(cells: int, w_m: float, h_m: float) -> tuple[int, int, bool]:
    """(columns across the short side, rows along the long side, half-cut split) for the cell pattern."""
    if cells <= 0:
        cells = 144 if h_m > 2.2 else 108
    cols = 6 if cells % 6 == 0 else (5 if cells % 5 == 0 else 6)
    rows = max(1, cells // cols)
    half = cells >= 100  # half-cut modules have a visible split in the middle
    return cols, rows, half


def homography(lay: Layout) -> np.ndarray | None:
    """3×3 matrix: plane metres → photo pixels."""
    if not lay.corners or len(lay.corners) != 4:
        return None
    src = np.array([[0, 0], [lay.plane_w_m, 0], [lay.plane_w_m, lay.plane_h_m], [0, lay.plane_h_m]], dtype=np.float32)
    dst = np.array([[float(c[0]), float(c[1])] for c in lay.corners], dtype=np.float32)
    try:
        return cv2.getPerspectiveTransform(src, dst)
    except cv2.error:
        return None


def _load_photo(lay: Layout) -> np.ndarray | None:
    if not lay.image_path:
        return None
    p = get_settings().data_dir / lay.image_path
    if not p.exists():
        return None
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    return img


# ----------------------------------------------------------------------------- plan view
def render_plan(db: Session, lay: Layout) -> Path:
    s = get_settings()
    W, H = float(lay.plane_w_m), float(lay.plane_h_m)
    scale = PLAN_PX / max(W, H)
    pad = 70
    w_px, h_px = int(W * scale), int(H * scale)
    im = Image.new("RGB", (w_px + 2 * pad, h_px + 2 * pad), (248, 249, 251))
    dr = ImageDraw.Draw(im, "RGBA")
    ox, oy = pad, pad
    photo = _load_photo(lay)
    Hm = homography(lay)
    if photo is not None and Hm is not None:
        rect = cv2.warpPerspective(photo, np.diag([scale, scale, 1.0]) @ np.linalg.inv(Hm), (w_px, h_px), flags=cv2.INTER_LINEAR)
        rect = cv2.cvtColor(rect, cv2.COLOR_BGR2RGB)
        tex = Image.fromarray(rect).convert("RGB")
        tex = Image.blend(tex, Image.new("RGB", tex.size, (255, 255, 255)), 0.35)
        im.paste(tex, (ox, oy))
    else:
        dr.rectangle([ox, oy, ox + w_px, oy + h_px], fill=(236, 239, 243))
    # roof polygon & shading of the unusable part
    roof = [(ox + x * scale, oy + y * scale) for x, y in (lay.roof_polygon or [])]
    if len(roof) >= 3:
        mask = Image.new("L", im.size, 0)
        md = ImageDraw.Draw(mask)
        md.rectangle([ox, oy, ox + w_px, oy + h_px], fill=80)  # shade the plane …
        md.polygon(roof, fill=0)  # … except the usable roof
        im.paste(Image.new("RGB", im.size, (90, 90, 100)), (0, 0), mask)
        dr = ImageDraw.Draw(im, "RGBA")
        dr.line(roof + [roof[0]], fill=(190, 40, 40, 255), width=3)
    # 1 m grid
    for gx in range(0, int(W) + 1):
        x = ox + gx * scale
        dr.line([x, oy, x, oy + h_px], fill=(0, 0, 0, 22), width=1)
    for gy in range(0, int(H) + 1):
        y = oy + gy * scale
        dr.line([ox, y, ox + w_px, y], fill=(0, 0, 0, 22), width=1)
    # obstacles
    for ob in lay.obstacles or []:
        pts = [(ox + x * scale, oy + y * scale) for x, y in ob]
        if len(pts) >= 3:
            dr.polygon(pts, fill=(230, 120, 40, 120), outline=(200, 90, 20, 255))
    # panels
    pw, ph, cells, wp = _panel_dims(db, lay)
    f_small = _font(max(10, int(scale * min(pw, ph) * 0.28)), bold=True)
    for i, p in enumerate(lay.panels or [], 1):
        x0, y0 = ox + p["x"] * scale, oy + p["y"] * scale
        x1, y1 = x0 + p["w"] * scale, y0 + p["h"] * scale
        on = p.get("enabled", True)
        dr.rectangle([x0, y0, x1, y1], fill=(24, 40, 72, 225) if on else (120, 120, 120, 90), outline=(255, 255, 255, 230), width=2)
        if on:
            cols, rows, half = _cells_grid(cells, pw, ph)
            if p["w"] > p["h"]:
                cols, rows = rows, cols
            for c in range(1, cols):
                x = x0 + (x1 - x0) * c / cols
                dr.line([x, y0, x, y1], fill=(255, 255, 255, 40), width=1)
            for r in range(1, rows):
                y = y0 + (y1 - y0) * r / rows
                dr.line([x0, y, x1, y], fill=(255, 255, 255, 40), width=1)
            txt = str(i)
            tw = dr.textlength(txt, font=f_small)
            dr.text(((x0 + x1) / 2 - tw / 2, (y0 + y1) / 2 - f_small.size / 2), txt, fill=(255, 255, 255, 230), font=f_small)
    # dimensions
    f = _font(22)
    fb = _font(26, bold=True)
    dr.line([ox, oy - 28, ox + w_px, oy - 28], fill=(60, 60, 60, 255), width=2)
    for x in (ox, ox + w_px):
        dr.line([x, oy - 36, x, oy - 20], fill=(60, 60, 60, 255), width=2)
    txt = f"{W:g} m"
    dr.text((ox + w_px / 2 - dr.textlength(txt, font=f) / 2, oy - 62), txt, fill=(40, 40, 40), font=f)
    dr.line([ox - 28, oy, ox - 28, oy + h_px], fill=(60, 60, 60, 255), width=2)
    for y in (oy, oy + h_px):
        dr.line([ox - 36, y, ox - 20, y], fill=(60, 60, 60, 255), width=2)
    vt = Image.new("RGBA", (200, 40), (0, 0, 0, 0))
    ImageDraw.Draw(vt).text((0, 0), f"{H:g} m", fill=(40, 40, 40, 255), font=f)
    vt = vt.rotate(90, expand=True)
    im.paste(vt, (ox - 72, oy + h_px // 2 - 100), vt)
    n = sum(1 for p in (lay.panels or []) if p.get("enabled", True))
    kwp = n * wp / 1000
    foot = f"{lay.name} — {n} × {wp:g} Wp = {kwp:.2f} kWp · наклон {lay.tilt_deg:g}° · азимут {lay.azimuth_deg:g}° · {pw*1000:.0f}×{ph*1000:.0f} mm"
    dr.text((ox, oy + h_px + 18), foot, fill=(30, 30, 30), font=fb)
    out = s.uploads_dir / f"render_{lay.id}.png"
    im.save(out, "PNG", optimize=True)
    lay.render_path = f"uploads/{out.name}"
    return out


# ----------------------------------------------------------------------------- photorealistic overlay
def _panel_layer(w_px: int, h_px: int, lay: Layout, pw: float, ph: float, cells: int, frame: str, light_dir: tuple[float, float], brightness: float) -> np.ndarray:
    """RGBA layer in rectified plane space with the modules drawn as they will look."""
    layer = np.zeros((h_px, w_px, 4), dtype=np.uint8)
    scale = w_px / float(lay.plane_w_m)
    fr = np.array(FRAME_COLOURS.get(frame, FRAME_COLOURS["black"]), dtype=np.float32)
    # module glass colour depends on how bright the photo is (exposure matching)
    base = np.clip(np.array([20, 27, 40], dtype=np.float32) * (0.75 + 0.6 * brightness), 8, 90)
    # sky reflection: one smooth band across the whole array (not per module), following the light direction
    yy, xx = np.mgrid[0:h_px, 0:w_px]
    g_all = (xx / max(1, w_px - 1)) * light_dir[0] + (yy / max(1, h_px - 1)) * light_dir[1]
    g_all = (g_all - g_all.min()) / max(1e-6, g_all.max() - g_all.min())
    spec_all = np.exp(-((g_all - 0.62) ** 2) / 0.06) * (28 + 50 * brightness)
    rng = np.random.default_rng(lay.id or 1)
    cols0, rows0, half = _cells_grid(cells, pw, ph)
    for p in lay.panels or []:
        if not p.get("enabled", True):
            continue
        x0, y0 = int(round(p["x"] * scale)), int(round(p["y"] * scale))
        x1, y1 = int(round((p["x"] + p["w"]) * scale)), int(round((p["y"] + p["h"]) * scale))
        if x1 - x0 < 3 or y1 - y0 < 3:
            continue
        hh, ww = y1 - y0, x1 - x0
        tile = np.empty((hh, ww, 4), dtype=np.float32)
        var = 1.0 + rng.uniform(-0.05, 0.05)  # slight module-to-module variation looks real
        shade = 0.9 + 0.25 * (np.linspace(0, 1, hh, dtype=np.float32)[:, None] * -light_dir[1] + 0.5)
        for c in range(3):
            tile[..., c] = base[c] * var * shade
        tile[..., :3] += spec_all[y0:y1, x0:x1, None] * np.array([0.9, 0.95, 1.0], dtype=np.float32)
        tile[..., 3] = 255
        cols, rows = (rows0, cols0) if p["w"] > p["h"] else (cols0, rows0)
        line = np.array([150, 156, 166], dtype=np.float32)
        m = max(1, int(round(min(ww, hh) * 0.014)))  # frame width
        for c in range(1, cols):
            x = int(round(ww * c / cols))
            tile[m:-m, max(0, x - 1):x, :3] = tile[m:-m, max(0, x - 1):x, :3] * 0.72 + line * 0.28
        for r in range(1, rows):
            y = int(round(hh * r / rows))
            tile[max(0, y - 1):y, m:-m, :3] = tile[max(0, y - 1):y, m:-m, :3] * 0.72 + line * 0.28
        if half:
            if p["w"] > p["h"]:
                x = ww // 2
                tile[m:-m, max(0, x - 1):x + 1, :3] = tile[m:-m, max(0, x - 1):x + 1, :3] * 0.5 + line * 0.5
            else:
                y = hh // 2
                tile[max(0, y - 1):y + 1, m:-m, :3] = tile[max(0, y - 1):y + 1, m:-m, :3] * 0.5 + line * 0.5
        # frame with a lighter top edge (bevel)
        tile[:m, :, :3] = fr
        tile[-m:, :, :3] = fr * 0.8
        tile[:, :m, :3] = fr
        tile[:, -m:, :3] = fr * 0.9
        tile[:1, :, :3] = np.minimum(255, fr * 1.6 + 25)
        layer[y0:y1, x0:x1] = np.clip(tile, 0, 255).astype(np.uint8)
    return layer


def render_photo(db: Session, lay: Layout, frame: str = "black") -> Path | None:
    """Composite the modules onto the original photo. Returns None when the layout has no photo/corners."""
    s = get_settings()
    photo = _load_photo(lay)
    Hm = homography(lay)
    if photo is None or Hm is None or not lay.panels:
        return None
    H_img, W_img = photo.shape[:2]
    pw, ph, cells, wp = _panel_dims(db, lay)
    # rectified working resolution
    px_per_m = max(60, min(220, int(2200 / max(lay.plane_w_m, lay.plane_h_m))))
    w_px, h_px = int(lay.plane_w_m * px_per_m), int(lay.plane_h_m * px_per_m)
    S = np.diag([px_per_m, px_per_m, 1.0])
    rect = cv2.warpPerspective(photo, S @ np.linalg.inv(Hm), (w_px, h_px), flags=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    brightness = float(np.clip(gray.mean(), 0.15, 0.95))
    # light direction from the brightness gradient of the roof (where the roof is brighter the glass reflects more)
    gy, gx = np.gradient(cv2.GaussianBlur(gray, (0, 0), max(3, px_per_m // 4)))
    lx, ly = float(gx.mean()), float(gy.mean())
    n = math.hypot(lx, ly)
    light_dir = (lx / n, ly / n) if n > 1e-5 else (0.3, -1.0)
    layer = _panel_layer(w_px, h_px, lay, pw, ph, cells, frame, light_dir, brightness)
    # shadow: offset copy of the alpha, blurred
    alpha = layer[..., 3].astype(np.float32) / 255.0
    off = max(2, int(px_per_m * 0.06))
    shadow = np.zeros_like(alpha)
    shadow[off:, off:] = alpha[:-off, :-off]
    shadow = cv2.GaussianBlur(shadow, (0, 0), max(1.5, px_per_m * 0.05)) * 0.55
    # local exposure match: multiply the glass by the photo's local luminance so shaded parts of the roof stay shaded
    lum = cv2.GaussianBlur(gray, (0, 0), max(2, px_per_m // 3))
    lum_n = np.clip(lum / max(1e-3, float(np.percentile(lum, 85))), 0.55, 1.2)
    rgb = layer[..., :3].astype(np.float32) * lum_n[..., None]
    layer_rgb = np.clip(rgb, 0, 255)
    # warp to the photo
    M = Hm @ np.linalg.inv(S)
    warped_rgb = cv2.warpPerspective(layer_rgb, M, (W_img, H_img), flags=cv2.INTER_LINEAR)
    warped_a = cv2.warpPerspective(alpha, M, (W_img, H_img), flags=cv2.INTER_LINEAR)
    warped_sh = cv2.warpPerspective(shadow, M, (W_img, H_img), flags=cv2.INTER_LINEAR)
    base = photo.astype(np.float32)
    base = base * (1 - warped_sh[..., None] * (1 - warped_a[..., None]))  # darken for the shadow outside the modules
    # layer is RGB; photo is BGR
    warped_bgr = warped_rgb[..., ::-1]
    out = base * (1 - warped_a[..., None]) + warped_bgr * warped_a[..., None]
    out = np.clip(out, 0, 255).astype(np.uint8)
    # caption
    pil = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
    dr = ImageDraw.Draw(pil, "RGBA")
    nmod = sum(1 for p in lay.panels if p.get("enabled", True))
    cap = f"{lay.name}: {nmod} × {wp:g} Wp = {nmod * wp / 1000:.2f} kWp"
    f = _font(max(16, W_img // 60), bold=True)
    tw = dr.textlength(cap, font=f)
    dr.rectangle([12, H_img - f.size - 26, 12 + tw + 24, H_img - 10], fill=(0, 0, 0, 120))
    dr.text((24, H_img - f.size - 20), cap, fill=(255, 255, 255, 240), font=f)
    dest = s.uploads_dir / f"visual_{lay.id}.jpg"
    pil.save(dest, "JPEG", quality=90)
    lay.visual_path = f"uploads/{dest.name}"
    return dest


def render_rect(lay: Layout) -> Path | None:
    """Rectified photo of the plane (texture for the 3D scene)."""
    photo = _load_photo(lay)
    Hm = homography(lay)
    if photo is None or Hm is None:
        return None
    px_per_m = max(40, min(160, int(1600 / max(lay.plane_w_m, lay.plane_h_m))))
    w_px, h_px = int(lay.plane_w_m * px_per_m), int(lay.plane_h_m * px_per_m)
    S = np.diag([px_per_m, px_per_m, 1.0])
    rect = cv2.warpPerspective(photo, S @ np.linalg.inv(Hm), (w_px, h_px), flags=cv2.INTER_LINEAR)
    dest = get_settings().uploads_dir / f"rect_{lay.id}.jpg"
    cv2.imwrite(str(dest), rect, [cv2.IMWRITE_JPEG_QUALITY, 86])
    lay.rect_path = f"uploads/{dest.name}"
    return dest


def render_all(db: Session, lay: Layout, frame: str | None = None) -> dict[str, str | None]:
    """Regenerate plan, photo overlay and rectified texture; commits the paths."""
    if not frame:
        frame = (((lay.project.params or {}).get("visual") or {}).get("frame") if lay.project else None) or "black"
    try:
        render_plan(db, lay)
    except Exception:  # noqa: BLE001 - renders must never block saving
        pass
    try:
        if render_photo(db, lay, frame=frame) is None:
            lay.visual_path = None
    except Exception:  # noqa: BLE001
        lay.visual_path = None
    try:
        if render_rect(lay) is None:
            lay.rect_path = None
    except Exception:  # noqa: BLE001
        lay.rect_path = None
    db.commit()
    db.refresh(lay)
    return {"render_path": lay.render_path, "visual_path": lay.visual_path, "rect_path": lay.rect_path}


def roof_colour(roof_type: str | None) -> tuple[int, int, int]:
    return ROOF_COLOURS.get(roof_type or "", (150, 150, 150))
