"""Automatic quote refresh – no "Recalculate" button needed.

The *working quote* of a project is its newest quote while it is still a draft. Whenever the wizard selections,
the project, a layout, the catalog, the labor matrix, roof types or the pricing settings change, the working quote
takes over the project's current selections (unless the user switched ``auto_sync`` off on that quote) and is
recalculated. Sent / accepted / rejected quotes are frozen documents and are never touched. Locked and manual
lines survive every recalculation (see ``pricing.apply_lines``).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models import Project, Quote
from . import pricing

log = logging.getLogger("gmsun.autosync")

QUOTE_FIELDS = ("markup_pct", "discount_pct", "vat_pct", "advance_pct", "valid_days")


def working_quote(project: Project) -> Quote | None:
    qs = sorted(project.quotes or [], key=lambda q: (q.version or 0, q.id or 0))
    if not qs:
        return None
    q = qs[-1]
    return q if (q.status or "draft") == "draft" else None


def _apply_project_selections(project: Project, q: Quote) -> bool:
    psel = (project.params or {}).get("selections")
    if not isinstance(psel, dict) or not psel:
        return False
    cur = dict(q.selections or {})
    if cur.get("auto_sync") is False:
        return False
    new = {k: v for k, v in psel.items() if not k.startswith("_") and k not in QUOTE_FIELDS}
    for k in ("_info", "_warnings"):
        if k in cur:
            new[k] = cur[k]
    if "auto_sync" in cur:
        new["auto_sync"] = cur["auto_sync"]
    for f in QUOTE_FIELDS:
        v = psel.get(f)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            setattr(q, f, int(v) if f == "valid_days" else float(v))
    changed = {k: v for k, v in new.items() if not k.startswith("_")} != {k: v for k, v in cur.items() if not k.startswith("_")}
    q.selections = new
    return changed


def sync_project(db: Session, project: Project | None, *, copy_selections: bool = True) -> Quote | None:
    """Refresh and commit the project's working quote.

    Call it *after* the triggering change has been committed: the refresh is committed on its own, and if it fails
    the session is rolled back (only the refresh is lost) – a failed refresh never blocks saving the project."""
    if project is None:
        return None
    q = working_quote(project)
    if q is None:
        return None
    pid = project.id
    try:
        if copy_selections:
            _apply_project_selections(project, q)
        pricing.recalculate(db, q)
        db.commit()
        return q
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.exception("autosync failed for project %s: %s", pid, e)
        return None


def recalc_all_drafts(db: Session) -> int:
    """After catalog / settings changes: refresh every project's working quote. Returns the number refreshed."""
    n = 0
    for p in db.query(Project).all():
        if sync_project(db, p) is not None:
            n += 1
    return n


def mirror_to_project(db: Session, q: Quote, selections: dict[str, Any] | None = None, fields: dict[str, Any] | None = None) -> bool:
    """Changes made directly on the working quote (selection keys, markup/discount/VAT/advance/validity, one-click
    completeness fixes) are written back to the project's wizard selections – the project stays the single source of
    truth, so the next automatic refresh can never revert them."""
    project = q.project
    if project is None or working_quote(project) is not q or (q.selections or {}).get("auto_sync") is False:
        return False
    params = dict(project.params or {})
    psel = dict(params.get("selections") or {})
    changed = False
    for k, v in (selections or {}).items():
        if k.startswith("_") or k == "auto_sync":
            continue
        if psel.get(k) != v:
            psel[k] = v
            changed = True
    for k, v in (fields or {}).items():
        if k in QUOTE_FIELDS and v is not None and psel.get(k) != v:
            psel[k] = v
            changed = True
    if changed:
        params["selections"] = psel
        project.params = params
    return changed


def summary(q: Quote | None) -> dict[str, Any] | None:
    if q is None:
        return None
    return {"id": q.id, "number": q.number, "version": q.version, "total": q.total}
