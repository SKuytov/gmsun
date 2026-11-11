"""Site kind of a roof / terrain type: ``pitched`` | ``flat`` | ``ground`` | ``fence``.

The kind decides which survey fields are relevant, which completeness checks run (scaffold vs. trench …), how the
3-D scene is drawn and how the client PDF calls the plant ("покривна", "наземна", "соларна ограда"). It is stored on
``RoofTypeConfig.kind`` (editable in the catalog) and derived from the code for older rows."""
from __future__ import annotations

from typing import Any

KINDS = ("pitched", "flat", "ground", "fence")
ROOF_KINDS = {"pitched", "flat"}


def kind_from_code(code: str | None) -> str:
    c = str(code or "").lower()
    if c.startswith("ground"):
        return "ground"
    if c.startswith("flat"):
        return "flat"
    if "fence" in c or c.startswith("wall") or c.startswith("facade"):
        return "fence"
    return "pitched"


def kind_of(code: str | None, roof: Any = None) -> str:
    k = getattr(roof, "kind", None) if roof is not None else None
    return k if k in KINDS else kind_from_code(code)


def project_kind(db, project) -> str:
    from ..models import RoofTypeConfig

    code = getattr(project, "roof_type", None)
    roof = db.get(RoofTypeConfig, code) if (db is not None and code) else None
    return kind_of(code, roof)


def where_bg(kind: str) -> str:
    return {"ground": "наземна", "fence": "соларна ограда", "flat": "покривна"}.get(kind, "покривна")
