from __future__ import annotations

import base64
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image, ImageOps
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..db import get_db
from ..models import CatalogItem, Layout, Project, Quote, RoofTypeConfig, User
from ..schemas import LayoutIn, LayoutOut, ProjectCreate, ProjectListItem, ProjectOut, ProjectUpdate, RoofDetectOut
from ..services import layout_engine as le
from ..services import autosync, module_fit, proposals, scene, visual
from ..services.pricing import active_layout_summary
from ..services.roof_detect import detect_obstacles, detect_roof

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_number(db: Session) -> str:
    y = date.today().year
    # Next number = highest existing + 1 (a count would reuse a number after a project is deleted -> unique violation).
    prefix = f"P{y}-"
    n = 0
    for (num,) in db.query(Project.number).filter(Project.number.like(prefix + "%")).all():
        tail = (num or "")[len(prefix):]
        if tail.isdigit():
            n = max(n, int(tail))
    return f"{prefix}{n + 1:04d}"


def _get(db: Session, pid: int) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _project_out(db: Session, p: Project) -> ProjectOut:
    o = ProjectOut.model_validate(p)
    o.quote_count = len(p.quotes)
    if p.quotes:
        latest = max(p.quotes, key=lambda q: (q.version, q.id))
        o.latest_total = latest.total
    return o


@router.get("", response_model=list[ProjectListItem])
def list_projects(q: str | None = None, status: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    qry = db.query(Project)
    if q:
        like = f"%{q}%"
        qry = qry.filter((Project.name.ilike(like)) | (Project.client_name.ilike(like)) | (Project.site_address.ilike(like)) | (Project.number.ilike(like)))
    if status:
        qry = qry.filter(Project.status == status)
    out = []
    for p in qry.order_by(Project.updated_at.desc()).all():
        item = ProjectListItem.model_validate(p)
        item.quote_count = len(p.quotes)
        if p.quotes:
            latest = max(p.quotes, key=lambda q: (q.version, q.id))
            item.latest_total = latest.total
        item.kwp = active_layout_summary(p)["kwp"] or None
        out.append(item)
    return out


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = Project(number=_project_number(db), created_by=user.id, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project_out(db, p)


@router.get("/{pid}", response_model=ProjectOut)
def get_project(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _project_out(db, _get(db, pid))


@router.patch("/{pid}", response_model=ProjectOut)
def update_project(pid: int, body: ProjectUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = _get(db, pid)
    from ..services.site_kind import project_kind

    old_kind, old_roof = project_kind(db, p), p.roof_type
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    if p.roof_type != old_roof:
        new_kind = project_kind(db, p)
        if (new_kind == "fence") != (old_kind == "fence"):  # vertical fence ↔ roof/ground: reset the tilt of the planes
            roof = db.get(RoofTypeConfig, p.roof_type)
            for lay in p.layouts:
                lay.tilt_deg = 90.0 if new_kind == "fence" else float(roof.default_tilt_deg if roof else 20.0)
    db.commit()
    db.refresh(p)
    autosync.sync_project(db, p)  # the working (draft) quote follows the wizard automatically
    db.refresh(p)
    return _project_out(db, p)


class ProposalsIn(BaseModel):
    strategies: list[str] | None = None
    selections: dict[str, Any] | None = None  # base selections (defaults to project.params.selections)
    scope: str = "auto"  # auto | target (client's demand) | roof (every module of the layout, multi-inverter)


class ProposalApplyIn(BaseModel):
    selections: dict[str, Any]
    strategy: str | None = None


@router.get("/{pid}/compatibility")
def project_compatibility(pid: int, panel_item_id: int | None = None, inverter_item_id: int | None = None, inverter_qty: int = 1,
                          panel_qty: int = 0, battery_item_id: int | None = None, battery_qty: int = 0,
                          db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """ok / warn / blocked (with reasons) for every active inverter, panel and battery against the given selection."""
    from ..services import compat

    p = _get(db, pid)
    return compat.matrix(db, p, panel_item_id=panel_item_id, inverter_item_id=inverter_item_id, inverter_qty=max(1, inverter_qty),
                         panel_qty=max(0, panel_qty), battery_item_id=battery_item_id, battery_qty=max(0, battery_qty))


@router.post("/{pid}/proposals")
def project_proposals(pid: int, body: ProposalsIn | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Build and rank complete configurations (Economy / Balanced / Premium / Fastest delivery) for the project."""
    p = _get(db, pid)
    body = body or ProposalsIn()
    return proposals.generate(db, p, body.strategies, body.selections, body.scope)


@router.post("/{pid}/proposals/apply", response_model=ProjectOut)
def apply_proposal(pid: int, body: ProposalApplyIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Store a proposal's selections as the project's working selections (the Equipment/Materials/Quote steps use them)."""
    p = _get(db, pid)
    sel = {k: v for k, v in body.selections.items() if not k.startswith("_")}
    if body.strategy:
        sel["strategy"] = body.strategy
    fit = sel.pop("panel_fit", None)
    p.params = {**(p.params or {}), "selections": sel}
    db.commit()
    db.refresh(p)
    if isinstance(fit, dict) and sel.get("use_layout", True) and p.layouts and int(fit.get("panel_item_id") or 0) == int(sel.get("panel_item_id") or 0):
        # the proposal uses a module (or a module count) different from the drawn layout → re-place the modules
        from ..services import module_fit, visual

        scope = "roof" if fit.get("mode") == "roof" else "target"
        res = module_fit.apply(db, p, int(fit["panel_item_id"]), scope=scope)
        sel = dict((p.params or {}).get("selections") or {})
        sel.update({k: v for k, v in body.selections.items() if not k.startswith("_") and k not in ("panel_fit", "panel_qty", "use_layout", "panel_limit")})
        sel["panel_qty"] = res["count"]
        p.params = {**(p.params or {}), "selections": sel}
        db.commit()
        for lay in p.layouts:
            visual.render_all(db, lay)
        db.refresh(p)
    autosync.sync_project(db, p)
    db.refresh(p)
    return _project_out(db, p)


@router.delete("/{pid}", status_code=204)
def delete_project(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = _get(db, pid)
    from ..services import documents as _docs

    _docs.purge_project(db, p)
    db.delete(p)
    db.commit()
    return Response(status_code=204)


@router.post("/{pid}/duplicate", response_model=ProjectOut, status_code=201)
def duplicate_project(pid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    src = _get(db, pid)
    data = {c.name: getattr(src, c.name) for c in Project.__table__.columns if c.name not in ("id", "number", "created_at", "updated_at", "created_by", "status")}
    data["name"] = f"{src.name} (копие)"
    p = Project(number=_project_number(db), created_by=user.id, status="draft", **data)
    db.add(p)
    db.flush()
    for lay in src.layouts:
        ld = {c.name: getattr(lay, c.name) for c in Layout.__table__.columns if c.name not in ("id", "project_id", "created_at", "updated_at")}
        db.add(Layout(project_id=p.id, **ld))
    db.commit()
    db.refresh(p)
    return _project_out(db, p)


# ------------------------------------------------------------------ layouts
def _layout(db: Session, pid: int, lid: int) -> Layout:
    lay = db.get(Layout, lid)
    if not lay or lay.project_id != pid:
        raise HTTPException(404, "Layout not found")
    return lay


@router.get("/{pid}/layouts", response_model=list[LayoutOut])
def list_layouts(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get(db, pid).layouts


@router.post("/{pid}/layouts", response_model=LayoutOut, status_code=201)
def create_layout(pid: int, body: LayoutIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = _get(db, pid)
    roof = db.get(RoofTypeConfig, p.roof_type)
    from ..services.site_kind import kind_of

    kind = kind_of(p.roof_type, roof)
    base = {"fence": "Ограда", "ground": "Поле"}.get(kind, "Покрив")
    lay = Layout(project_id=p.id, name=body.name or f"{base} {len(p.layouts) + 1}", tilt_deg=roof.default_tilt_deg if roof else 20.0)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(lay, k, v)
    if lay.panel_item_id is None:
        first_panel = db.query(CatalogItem).filter(CatalogItem.category == "panel", CatalogItem.active.is_(True)).order_by(CatalogItem.sort_order).first()
        lay.panel_item_id = first_panel.id if first_panel else None
    db.add(lay)
    db.commit()
    db.refresh(lay)
    autosync.sync_project(db, p)
    db.refresh(lay)
    return lay


@router.patch("/{pid}/layouts/{lid}", response_model=LayoutOut)
def update_layout(pid: int, lid: int, body: LayoutIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lay = _layout(db, pid, lid)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(lay, k, v)
    _refresh_summary(db, lay)
    db.commit()
    db.refresh(lay)
    visual.render_all(db, lay)  # plan + photo overlay + 3D texture always follow the saved geometry
    autosync.sync_project(db, _get(db, pid))
    db.refresh(lay)
    return lay


@router.delete("/{pid}/layouts/{lid}", status_code=204)
def delete_layout(pid: int, lid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lay = _layout(db, pid, lid)
    db.delete(lay)
    db.commit()
    autosync.sync_project(db, _get(db, pid))
    return Response(status_code=204)


def _refresh_summary(db: Session, lay: Layout) -> None:
    panel = db.get(CatalogItem, lay.panel_item_id) if lay.panel_item_id else None
    wp = float((panel.specs or {}).get("wp", 0)) if panel else 0.0
    roof = db.get(RoofTypeConfig, lay.project.roof_type) if lay.project else None
    lay.summary = le.summarize(lay.panels or [], wp, lay.gap_x_m, roof.rails_per_module if roof else 2, lay.gap_y_m)


@router.post("/{pid}/layouts/{lid}/image", response_model=LayoutOut)
async def upload_layout_image(pid: int, lid: int, file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lay = _layout(db, pid, lid)
    s = get_settings()
    raw = await file.read()
    try:
        import io

        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        if max(img.size) > 2400:
            img.thumbnail((2400, 2400))
        name = f"layout_{lay.id}_{uuid.uuid4().hex[:8]}.jpg"
        dest = s.uploads_dir / name
        img.save(dest, "JPEG", quality=88)
        lay.image_path = f"uploads/{name}"
        lay.image_w, lay.image_h = img.size
        if not lay.corners:
            w, h = img.size
            lay.corners = [[w * 0.1, h * 0.1], [w * 0.9, h * 0.1], [w * 0.9, h * 0.9], [w * 0.1, h * 0.9]]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Невалидно изображение: {e}")
    db.commit()
    db.refresh(lay)
    return lay


@router.post("/{pid}/layouts/{lid}/render", response_model=LayoutOut)
async def upload_layout_render(pid: int, lid: int, body: dict[str, Any], db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Store a PNG (data URL) of the final layout for the PDF."""
    lay = _layout(db, pid, lid)
    data_url: str = body.get("png", "")
    if not data_url.startswith("data:image/png;base64,"):
        raise HTTPException(400, "Expected PNG data URL")
    s = get_settings()
    name = f"render_{lay.id}.png"
    (s.uploads_dir / name).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    lay.render_path = f"uploads/{name}"
    db.commit()
    db.refresh(lay)
    return lay


@router.post("/{pid}/layouts/{lid}/detect-roof", response_model=RoofDetectOut)
def detect_roof_endpoint(pid: int, lid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lay = _layout(db, pid, lid)
    if not lay.image_path:
        raise HTTPException(400, "Няма качена снимка")
    data = (get_settings().data_dir / lay.image_path).read_bytes()
    res = detect_roof(data)
    return RoofDetectOut(**res)


@router.post("/{pid}/layouts/{lid}/detect-obstacles")
def detect_obstacles_endpoint(pid: int, lid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lay = _layout(db, pid, lid)
    if not lay.image_path or not lay.corners or len(lay.corners) != 4:
        raise HTTPException(400, "Нужни са снимка и 4 ъгъла")
    data = (get_settings().data_dir / lay.image_path).read_bytes()
    w, h = lay.image_w or 1, lay.image_h or 1
    quad = [[c[0] / w, c[1] / h] for c in lay.corners]
    scale = 100  # px per metre in rectified space
    pw, ph = int(lay.plane_w_m * scale), int(lay.plane_h_m * scale)
    polys = detect_obstacles(data, quad, pw, ph)
    return {"obstacles": [[[x / scale, y / scale] for x, y in poly] for poly in polys]}


@router.post("/{pid}/layouts/{lid}/autofill", response_model=LayoutOut)
def autofill(pid: int, lid: int, body: dict[str, Any] | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    lay = _layout(db, pid, lid)
    body = body or {}
    panel = db.get(CatalogItem, body.get("panel_item_id") or lay.panel_item_id) if (body.get("panel_item_id") or lay.panel_item_id) else None
    if not panel:
        raise HTTPException(400, "Не е избран панел")
    sp = panel.specs or {}
    pw, ph = float(sp.get("width_mm", 1134)) / 1000, float(sp.get("height_mm", 2382)) / 1000
    roof_poly = [tuple(p) for p in (body.get("roof_polygon") or lay.roof_polygon or [])]
    if len(roof_poly) < 3:
        roof_poly = [(0, 0), (lay.plane_w_m, 0), (lay.plane_w_m, lay.plane_h_m), (0, lay.plane_h_m)]
    obstacles = [[tuple(p) for p in ob] for ob in (body.get("obstacles") or lay.obstacles or [])]
    params = le.FillParams(
        panel_w_m=pw,
        panel_h_m=ph,
        orientation=body.get("orientation") or lay.orientation,
        gap_x_m=float(body.get("gap_x_m", lay.gap_x_m)),
        gap_y_m=float(body.get("gap_y_m", lay.gap_y_m)),
        setback_m=float(body.get("setback_m", lay.setback_m)),
        row_spacing_m=float(body.get("row_spacing_m", lay.row_spacing_m)),
        max_panels=body.get("max_panels"),
    )
    res = le.auto_fill(roof_poly, obstacles, params)
    lay.panel_item_id = panel.id
    lay.roof_polygon = [list(p) for p in roof_poly]
    lay.obstacles = [[list(p) for p in ob] for ob in obstacles]
    lay.orientation = res.orientation
    lay.panels = [p.as_dict() for p in res.panels]
    for k in ("gap_x_m", "gap_y_m", "setback_m", "row_spacing_m"):
        setattr(lay, k, getattr(params, k))
    _refresh_summary(db, lay)
    db.commit()
    db.refresh(lay)
    visual.render_all(db, lay)
    autosync.sync_project(db, _get(db, pid))
    db.refresh(lay)
    return lay


# ----------------------------------------------------------------------------- module recommendation / visualisation / 3D
class ModuleRecIn(BaseModel):
    scope: str = "auto"  # auto | target | roof
    strategy: str = "balanced"
    orientation: str = "auto"
    top: int = 8


class ModuleApplyIn(BaseModel):
    panel_item_id: int
    scope: str = "auto"
    orientation: str = "auto"
    orientations: dict[int, str] | None = None  # per-layout override


@router.post("/{pid}/module-recommendations")
def module_recommendations(pid: int, body: ModuleRecIn | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Rank every catalog module by how it fits the drawn planes, the demand and the strategy (best-practice rules)."""
    p = _get(db, pid)
    body = body or ModuleRecIn()
    return module_fit.recommend(db, p, scope=body.scope, strategy=body.strategy, top=body.top, orientation=body.orientation)


@router.post("/{pid}/module-recommendations/apply", response_model=ProjectOut)
def module_recommendations_apply(pid: int, body: ModuleApplyIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Put the recommended module on every plane (re-placing the modules) and make it the project's selection."""
    p = _get(db, pid)
    try:
        module_fit.apply(db, p, body.panel_item_id, scope=body.scope, orientation=body.orientation, overrides=body.orientations)
    except ValueError as e:
        raise HTTPException(400, str(e))
    for lay in p.layouts:
        visual.render_all(db, lay)
    db.refresh(p)
    autosync.sync_project(db, p)
    db.refresh(p)
    return _project_out(db, p)


@router.post("/{pid}/layouts/{lid}/visualize", response_model=LayoutOut)
def visualize_layout(pid: int, lid: int, body: dict[str, Any] | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """(Re)generate the plan render, the photorealistic overlay and the rectified texture. ``{"frame": "black"|"silver"}``."""
    lay = _layout(db, pid, lid)
    frame = (body or {}).get("frame")
    if frame in ("black", "silver"):
        params = dict(lay.project.params or {})
        params["visual"] = {**(params.get("visual") or {}), "frame": frame}
        lay.project.params = params
        db.commit()
    visual.render_all(db, lay, frame=frame)
    return lay


@router.get("/{pid}/scene")
def project_scene(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """3D scene description (planes, modules, obstacles, building) for the viewer."""
    return scene.build_scene(db, _get(db, pid))


@router.post("/{pid}/render3d", response_model=ProjectOut)
def upload_render3d(pid: int, body: dict[str, Any], db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Store a screenshot of the 3D view (PNG data URL) for the documents."""
    p = _get(db, pid)
    data_url: str = body.get("png", "")
    if not data_url.startswith("data:image/png;base64,"):
        raise HTTPException(400, "Expected PNG data URL")
    s = get_settings()
    name = f"render3d_{p.id}.png"
    (s.uploads_dir / name).write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    params = dict(p.params or {})
    params["visual"] = {**(params.get("visual") or {}), "render3d_path": f"uploads/{name}"}
    p.params = params
    db.commit()
    db.refresh(p)
    return _project_out(db, p)
