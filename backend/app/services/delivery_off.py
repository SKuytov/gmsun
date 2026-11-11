"""One-off: GM SUN does not quote delivery fees any more.

Turns the company setting off, drops the per-quote switch from projects and *draft* quotes (so the setting applies)
and removes their ``delivery:*`` lines. Sent / accepted / rejected quotes are frozen documents and stay untouched."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import Project, Quote, Setting

log = logging.getLogger("gmsun.migrate")
MIGRATION_KEY = "delivery_fees_off_v1"


def migrate(db: Session) -> dict | None:
    mig_row = db.get(Setting, "migrations")
    mig = dict(mig_row.value or {}) if mig_row and mig_row.value else {}
    if mig.get(MIGRATION_KEY):
        return None
    from . import pricing

    pr_row = db.get(Setting, "pricing")
    if pr_row is not None:
        pr_row.value = {**(pr_row.value or {}), "include_delivery_fees": False}
    n_proj = 0
    for p in db.query(Project).all():
        params = dict(p.params or {})
        sel = params.get("selections")
        if isinstance(sel, dict) and "delivery_fees" in sel:
            sel = {k: v for k, v in sel.items() if k != "delivery_fees"}
            params["selections"] = sel
            p.params = params
            n_proj += 1
    db.flush()
    n_q = n_lines = 0
    for q in db.query(Quote).filter(Quote.status == "draft").all():
        sel = dict(q.selections or {})
        had = any(l.key.startswith("delivery:") for l in q.lines)
        if "delivery_fees" not in sel and not had:
            continue
        sel.pop("delivery_fees", None)
        q.selections = sel
        try:
            with db.begin_nested():
                pricing.recalculate(db, q)
                for l in [l for l in q.lines if l.key.startswith("delivery:")]:  # locked / manual copies too
                    q.lines.remove(l)  # delete-orphan
                    n_lines += 1
                pricing.compute_totals(q)
            n_q += 1
        except Exception:  # never block startup – the quote refreshes on its next change
            log.exception("delivery-fee migration failed for quote %s", q.id)
    res = {"at": datetime.now(timezone.utc).isoformat(), "projects": n_proj, "quotes": n_q, "locked_lines_removed": n_lines}
    if mig_row is None:
        db.add(Setting(key="migrations", value={MIGRATION_KEY: res}))
    else:
        mig_row.value = {**mig, MIGRATION_KEY: res}
    db.commit()
    log.info("delivery fees off: %s", res)
    return res
