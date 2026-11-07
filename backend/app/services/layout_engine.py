"""Panel auto-placement engine (metres, plane coordinates).

The same algorithm is implemented in the frontend (TypeScript) for interactive
editing; this server-side version powers the API for measurement-only
projects, tests and recalculation.

Coordinates: x to the right, y downwards (image convention), units: metres.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]
Polygon = list[Point]


@dataclass
class Panel:
    x: float
    y: float
    w: float
    h: float
    enabled: bool = True
    row: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"x": round(self.x, 4), "y": round(self.y, 4), "w": round(self.w, 4), "h": round(self.h, 4), "enabled": self.enabled, "row": self.row}


@dataclass
class FillParams:
    panel_w_m: float  # module width (short side)
    panel_h_m: float  # module height (long side)
    orientation: str = "portrait"  # portrait | landscape | auto
    gap_x_m: float = 0.02
    gap_y_m: float = 0.02
    setback_m: float = 0.3
    row_spacing_m: float = 0.0  # extra spacing between rows (ground mount)
    max_panels: int | None = None
    offsets: int = 6  # grid offset search resolution per axis


@dataclass
class FillResult:
    panels: list[Panel] = field(default_factory=list)
    orientation: str = "portrait"
    count: int = 0
    area_m2: float = 0.0
    lines: list[dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def polygon_area(poly: Polygon) -> float:
    a = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def point_in_polygon(p: Point, poly: Polygon) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def dist_point_segment(p: Point, a: Point, b: Point) -> float:
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def dist_point_polygon_edges(p: Point, poly: Polygon) -> float:
    n = len(poly)
    return min(dist_point_segment(p, poly[i], poly[(i + 1) % n]) for i in range(n))


def segments_intersect(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    def ccw(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = ccw(p3, p4, p1), ccw(p3, p4, p2)
    d3, d4 = ccw(p1, p2, p3), ccw(p1, p2, p4)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def rect_corners(x: float, y: float, w: float, h: float) -> Polygon:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def polygons_intersect(a: Polygon, b: Polygon) -> bool:
    if any(point_in_polygon(p, b) for p in a):
        return True
    if any(point_in_polygon(p, a) for p in b):
        return True
    na, nb = len(a), len(b)
    for i in range(na):
        for j in range(nb):
            if segments_intersect(a[i], a[(i + 1) % na], b[j], b[(j + 1) % nb]):
                return True
    return False


def rect_fits(x: float, y: float, w: float, h: float, roof: Polygon, obstacles: list[Polygon], setback: float) -> bool:
    corners = rect_corners(x, y, w, h)
    for c in corners:
        if not point_in_polygon(c, roof):
            return False
        if setback > 0 and dist_point_polygon_edges(c, roof) < setback - 1e-9:
            return False
    # also check rectangle edge midpoints for concave roofs
    mids = [((corners[i][0] + corners[(i + 1) % 4][0]) / 2, (corners[i][1] + corners[(i + 1) % 4][1]) / 2) for i in range(4)]
    for m in mids:
        if not point_in_polygon(m, roof):
            return False
    for ob in obstacles:
        if len(ob) >= 3 and polygons_intersect(corners, ob):
            return False
    return True


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------
def _fill_orientation(roof: Polygon, obstacles: list[Polygon], params: FillParams, orientation: str) -> list[Panel]:
    if orientation == "portrait":
        w, h = params.panel_w_m, params.panel_h_m
    else:
        w, h = params.panel_h_m, params.panel_w_m
    xs = [p[0] for p in roof]
    ys = [p[1] for p in roof]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    step_x = w + params.gap_x_m
    step_y = h + params.gap_y_m + params.row_spacing_m
    if maxx - minx < w or maxy - miny < h:
        return []
    best: list[Panel] = []
    n_off = max(1, params.offsets)
    for ix in range(n_off):
        ox = minx + params.setback_m + (step_x * ix / n_off)
        for iy in range(n_off):
            oy = miny + params.setback_m + (step_y * iy / n_off)
            panels: list[Panel] = []
            row = 0
            y = oy
            while y + h <= maxy + 1e-9:
                x = ox
                placed_in_row = False
                while x + w <= maxx + 1e-9:
                    if rect_fits(x, y, w, h, roof, obstacles, params.setback_m):
                        panels.append(Panel(x, y, w, h, True, row))
                        placed_in_row = True
                    x += step_x
                if placed_in_row:
                    row += 1
                y += step_y
            if len(panels) > len(best):
                best = panels
    if params.max_panels is not None and len(best) > params.max_panels:
        # keep the most central ones: sort by distance to centroid and drop extras
        cx = sum(p.x + p.w / 2 for p in best) / len(best)
        cy = sum(p.y + p.h / 2 for p in best) / len(best)
        best.sort(key=lambda p: math.hypot(p.x + p.w / 2 - cx, p.y + p.h / 2 - cy))
        best = best[: params.max_panels]
    return best


def auto_fill(roof: Polygon, obstacles: list[Polygon], params: FillParams) -> FillResult:
    if len(roof) < 3:
        return FillResult()
    if params.orientation == "auto":
        a = _fill_orientation(roof, obstacles, params, "portrait")
        b = _fill_orientation(roof, obstacles, params, "landscape")
        panels, orient = (a, "portrait") if len(a) >= len(b) else (b, "landscape")
    else:
        orient = params.orientation
        panels = _fill_orientation(roof, obstacles, params, orient)
    res = FillResult(panels=panels, orientation=orient, count=len(panels))
    res.area_m2 = round(sum(p.w * p.h for p in panels), 2)
    res.lines = rail_lines(panels, params.gap_x_m, 2, params.gap_y_m)
    return res


RAIL_SPAN_3_M = 1.6  # module span across the rails above which 3 rails are used (long landscape modules)


def _rails_for_span(span_m: float, minimum: int = 2, vertical: bool = False) -> int:
    """Rails per run.

    Portrait modules on horizontal rails use 2 rails (industry standard).
    Landscape modules on vertical rails (rails along the slope) need 3 rails when the
    module span across the rails exceeds RAIL_SPAN_3_M (as in the Aerocompact reports).
    """
    if vertical and span_m > RAIL_SPAN_3_M:
        return max(minimum, 3)
    return max(minimum, 2)


def _runs(pts: list[Panel], gap: float, along_x: bool) -> list[list[Panel]]:
    """Group panels into contiguous runs along x (rows) or along y (columns)."""
    if along_x:
        key_a, key_b, size = (lambda p: p.y), (lambda p: p.x), (lambda p: p.w)
        cross = lambda p: p.h  # noqa: E731
    else:
        key_a, key_b, size = (lambda p: p.x), (lambda p: p.y), (lambda p: p.h)
        cross = lambda p: p.w  # noqa: E731
    pts = sorted(pts, key=lambda p: (round(key_a(p), 2), key_b(p)))
    groups: list[list[Panel]] = []
    for p in pts:
        if groups and abs(key_a(groups[-1][0]) - key_a(p)) < 1e-3 and abs(cross(groups[-1][0]) - cross(p)) < 1e-3:
            groups[-1].append(p)
        else:
            groups.append([p])
    runs: list[list[Panel]] = []
    for g in groups:
        g.sort(key=key_b)
        run = [g[0]]
        for p in g[1:]:
            prev = run[-1]
            if abs((key_b(prev) + size(prev) + gap) - key_b(p)) < 0.03:
                run.append(p)
            else:
                runs.append(run)
                run = [p]
        runs.append(run)
    return runs


def rail_lines(panels: list[Panel] | list[dict[str, Any]], gap_x: float, rails_per_module: int = 2, gap_y: float | None = None) -> list[dict[str, Any]]:
    """Group enabled panels into contiguous runs and return rail-line summaries.

    Both rail directions are evaluated (rails along rows, or rails along columns);
    the direction with the smaller total rail length wins. Each entry:
    {modules, length_m, rails, direction, y|x}.
    """
    if gap_y is None:
        gap_y = gap_x
    pts: list[Panel] = []
    for p in panels:
        if isinstance(p, dict):
            if not p.get("enabled", True):
                continue
            pts.append(Panel(float(p["x"]), float(p["y"]), float(p["w"]), float(p["h"]), True, int(p.get("row", 0))))
        elif p.enabled:
            pts.append(p)
    if not pts:
        return []
    best: list[dict[str, Any]] | None = None
    best_m = float("inf")
    for along_x in (True, False):
        runs = _runs(pts, gap_x if along_x else gap_y, along_x)
        lines: list[dict[str, Any]] = []
        total = 0.0
        for run in runs:
            n = len(run)
            if along_x:
                length = sum(p.w for p in run) + gap_x * (n - 1)
                span = run[0].h
            else:
                length = sum(p.h for p in run) + gap_y * (n - 1)
                span = run[0].w
            rails = _rails_for_span(span, rails_per_module, vertical=not along_x)
            total += length * rails
            entry = {"modules": n, "length_m": round(length, 3), "rails": rails, "direction": "h" if along_x else "v"}
            entry["y" if along_x else "x"] = round(run[0].y if along_x else run[0].x, 3)
            lines.append(entry)
        if total < best_m - 1e-6:
            best_m = total
            best = lines
    return best or []


def summarize(panels: list[dict[str, Any]], panel_wp: float, gap_x: float, rails_per_module: int = 2, gap_y: float | None = None) -> dict[str, Any]:
    enabled = [p for p in panels if p.get("enabled", True)]
    count = len(enabled)
    return {
        "count": count,
        "kwp": round(count * panel_wp / 1000.0, 3),
        "area_m2": round(sum(float(p["w"]) * float(p["h"]) for p in enabled), 2),
        "lines": rail_lines(panels, gap_x, rails_per_module, gap_y),
    }
