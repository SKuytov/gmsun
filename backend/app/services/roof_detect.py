"""Automatic roof-plane proposal from a photo (OpenCV).

Returns the most plausible quadrilateral (normalised 0..1 coordinates in the
order top-left, top-right, bottom-right, bottom-left) so the user only has to
nudge the corners instead of placing them from scratch.

Strategy (robust, no ML dependency):
1. downscale, bilateral filter, Canny edges, close gaps
2. contours -> convex quads via approxPolyDP, keep those covering 8..95 % of
   the image, score by area × rectangularity
3. fallback: dominant-colour segmentation (k-means on Lab) of the central
   region -> largest component -> minAreaRect
"""
from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def _order_quad(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def _quad_score(quad: np.ndarray, img_area: float) -> float:
    area = cv2.contourArea(quad.astype(np.float32))
    if area <= 0:
        return 0.0
    rect = cv2.minAreaRect(quad.astype(np.float32))
    rect_area = max(rect[1][0] * rect[1][1], 1e-6)
    rectangularity = area / rect_area
    frac = area / img_area
    if frac < 0.08 or frac > 0.95:
        return 0.0
    return float(frac * rectangularity)


def detect_roof(image_bytes: bytes) -> dict[str, Any]:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cannot decode image")
    h0, w0 = img.shape[:2]
    scale = 900.0 / max(h0, w0)
    if scale < 1:
        img = cv2.resize(img, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    img_area = float(h * w)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.bilateralFilter(gray, 9, 60, 60)
    v = float(np.median(blur))
    lo, hi = int(max(0, 0.66 * v)), int(min(255, 1.33 * v))
    edges = cv2.Canny(blur, lo, hi)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best: np.ndarray | None = None
    best_score = 0.0
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:40]:
        peri = cv2.arcLength(c, True)
        for eps in (0.02, 0.04, 0.06):
            approx = cv2.approxPolyDP(c, eps * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                sc = _quad_score(approx, img_area)
                if sc > best_score:
                    best_score, best = sc, approx
                break
    method = "edges"
    confidence = min(1.0, best_score * 1.5)

    if best is None or best_score < 0.1:
        # fallback: colour segmentation of the central region
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        Z = lab.reshape((-1, 3)).astype(np.float32)
        K = 4
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, _ = cv2.kmeans(Z, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        labels = labels.reshape((h, w))
        centre_label = int(np.bincount(labels[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3].ravel()).argmax())
        mask = (labels == centre_label).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
        n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask)
        if n > 1:
            idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            comp = (lbl == idx).astype(np.uint8)
            cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                c = max(cnts, key=cv2.contourArea)
                rect = cv2.minAreaRect(c)
                best = cv2.boxPoints(rect).reshape(-1, 1, 2)
                method = "colour"
                confidence = 0.35
    if best is None:
        # last resort: central 80 % box
        best = np.array([[[w * 0.1, h * 0.1]], [[w * 0.9, h * 0.1]], [[w * 0.9, h * 0.9]], [[w * 0.1, h * 0.9]]], dtype=np.float32)
        method = "default"
        confidence = 0.0

    quad = _order_quad(np.array(best, dtype=np.float32))
    quad[:, 0] = np.clip(quad[:, 0] / w, 0, 1)
    quad[:, 1] = np.clip(quad[:, 1] / h, 0, 1)
    return {
        "corners": [[round(float(x), 4), round(float(y), 4)] for x, y in quad],
        "confidence": round(float(confidence), 2),
        "method": method,
    }


def detect_obstacles(image_bytes: bytes, quad_norm: list[list[float]], plane_w_px: int, plane_h_px: int) -> list[list[list[float]]]:
    """Find candidate obstacles (chimneys, windows) inside the rectified plane.

    Returns polygons in rectified-pixel coordinates. Uses colour deviation from
    the dominant roof colour.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    h, w = img.shape[:2]
    src = np.array([[x * w, y * h] for x, y in quad_norm], dtype=np.float32)
    dst = np.array([[0, 0], [plane_w_px, 0], [plane_w_px, plane_h_px], [0, plane_h_px]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img, M, (plane_w_px, plane_h_px))
    lab = cv2.cvtColor(warped, cv2.COLOR_BGR2LAB)
    med = np.median(lab.reshape(-1, 3), axis=0)
    diff = np.linalg.norm(lab.astype(np.float32) - med.astype(np.float32), axis=2)
    thr = float(np.percentile(diff, 90))
    mask = (diff > max(thr, 25)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: list[list[list[float]]] = []
    min_area = 0.004 * plane_w_px * plane_h_px
    max_area = 0.25 * plane_w_px * plane_h_px
    for c in cnts:
        a = cv2.contourArea(c)
        if a < min_area or a > max_area:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        # ignore border-touching blobs (edges of the plane)
        if x <= 2 or y <= 2 or x + bw >= plane_w_px - 2 or y + bh >= plane_h_px - 2:
            continue
        out.append([[float(x), float(y)], [float(x + bw), float(y)], [float(x + bw), float(y + bh)], [float(x), float(y + bh)]])
    return out[:12]
