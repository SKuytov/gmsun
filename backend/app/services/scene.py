"""3D scene description of the PV plant (consumed by the three.js viewer in the frontend).

Coordinate system: metres, X = east, Y = up, Z = south (right-handed, so azimuth 180° = +Z).  Every layout becomes a
tilted plane: the local plane coordinates (u along the eave/ridge, v down the slope) are mapped to 3D by rotating
the plane by its tilt about the eave and then by its azimuth about the vertical axis.  Planes with the same azimuth
are laid side by side along the eave; different azimuths are placed around the building footprint so a hip/gable
roof with south + west planes looks like one roof.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, Project
from .visual import roof_colour
from .module_fit import module_dims_m

FLAT = {"flat_concrete", "flat_ew", "flat_bifacial"}
GROUND = {"ground", "ground_ballast"}


def _panel(db: Session, pid: int | None) -> dict[str, Any]:
    it = db.get(CatalogItem, pid) if pid else None
    sp = (it.specs or {}) if it else {}
    return {
        "name": it.name if it else None, "wp": float(sp.get("wp") or 0), "width_m": module_dims_m(sp)[0],
        "height_m": module_dims_m(sp)[1], "thickness_m": float(sp.get("thickness_mm") or 35) / 1000,
        "cells": int(float(sp.get("cells") or 0) or 0), "bifacial": float(sp.get("bifaciality") or 0) > 0,
    }


def build_scene(db: Session, project: Project) -> dict[str, Any]:
    params = project.params or {}
    survey = params.get("survey") or {}
    roof_type = project.roof_type
    flat = roof_type in FLAT
    ground = roof_type in GROUND
    eave_h = float(survey.get("building_height_m") or 0) or (0.0 if ground else (3.2 if not flat else 3.5))
    if not ground and not flat and eave_h > 3.0:
        eave_h = max(2.6, eave_h - 1.5)  # survey height is to the ridge; drop to the eave
    layouts = sorted(project.layouts, key=lambda l: (round(l.azimuth_deg / 15), l.id))
    planes: list[dict[str, Any]] = []
    # footprint: group planes by azimuth; same azimuth → side by side along the eave
    by_az: dict[int, list] = {}
    for l in layouts:
        by_az.setdefault(int(round(l.azimuth_deg / 15.0) * 15) % 360, []).append(l)
    # the "reference" group (largest total width) sits along +Z (south) facing; other groups are rotated around
    groups = sorted(by_az.items(), key=lambda kv: -sum(x.plane_w_m for x in kv[1]))
    ref_depth = max([l.plane_h_m * math.cos(math.radians(l.tilt_deg)) for l in layouts] or [6.0])
    ref_width = sum(l.plane_w_m for l in groups[0][1]) if groups else 10.0
    # planes that face sideways (gable/hip ends) run along the building depth — stretch the footprint to hold them
    side_w = max([sum(l.plane_w_m for l in g) for a, g in groups[1:] if abs(math.cos(math.radians(a - 180))) <= 0.5] or [0.0])
    half_w, half_d = ref_width / 2, max(ref_depth, side_w / 2)
    for az, group in groups:
        total_w = sum(l.plane_w_m for l in group) + 0.3 * (len(group) - 1)
        u0 = -total_w / 2
        for l in group:
            tilt = float(l.tilt_deg)
            az_rad = math.radians(float(l.azimuth_deg))
            # the eave line is horizontal, at height eave_h, offset from the centre toward the plane's azimuth
            # by the footprint half-size; the plane rises from the eave toward the centre (ridge)
            if flat or ground:
                eave_offset = 0.0
            else:
                eave_offset = half_d if abs(math.cos(math.radians(az - 180))) > 0.5 else half_w
            planes.append({
                "layout_id": l.id, "name": l.name, "width_m": l.plane_w_m, "height_m": l.plane_h_m, "tilt": tilt, "azimuth": float(l.azimuth_deg),
                "u_offset": u0, "eave_offset": eave_offset, "eave_height": eave_h if not ground else 0.8,
                "roof_polygon": l.roof_polygon or [[0, 0], [l.plane_w_m, 0], [l.plane_w_m, l.plane_h_m], [0, l.plane_h_m]],
                "obstacles": l.obstacles or [], "panels": [p for p in (l.panels or []) if p.get("enabled", True)],
                "panel": _panel(db, l.panel_item_id), "texture": l.rect_path, "colour": roof_colour(roof_type),
                "ballast": flat, "elevated": ground or flat,
                "_az": az_rad,
            })
            u0 += l.plane_w_m + 0.3
    for p in planes:
        p.pop("_az", None)
    n_mod = sum(len(p["panels"]) for p in planes)
    kwp = sum(len(p["panels"]) * p["panel"]["wp"] for p in planes) / 1000
    return {
        "project_id": project.id, "name": project.name, "roof_type": roof_type, "flat": flat, "ground": ground,
        "building": {"width_m": ref_width + 1.0, "depth_m": 2 * half_d + 1.0 if not (flat or ground) else ref_depth + 1.0, "eave_height_m": eave_h,
                      "ridge_height_m": eave_h + (max([l.plane_h_m * math.sin(math.radians(l.tilt_deg)) for l in layouts] or [0.0])), "colour": [214, 210, 200]},
        "planes": planes, "modules": n_mod, "kwp": round(kwp, 2),
        "site": {"lat": 43.0, "lon": 25.5},
        "render3d_path": (params.get("visual") or {}).get("render3d_path"),
    }
