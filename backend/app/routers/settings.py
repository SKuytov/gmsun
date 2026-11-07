from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..schemas import SettingIn, SettingOut
from ..services.settings import DEFAULT_SETTINGS, get_setting, set_setting

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=list[SettingOut])
def all_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [SettingOut(key=k, value=get_setting(db, k)) for k in DEFAULT_SETTINGS]


@router.get("/{key}", response_model=SettingOut)
def one(key: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(404)
    return SettingOut(key=key, value=get_setting(db, key))


@router.put("/{key}", response_model=SettingOut)
def update(key: str, body: SettingIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if key not in DEFAULT_SETTINGS:
        raise HTTPException(404)
    return SettingOut(key=key, value=set_setting(db, key, body.value))


@router.post("/company/logo", response_model=SettingOut)
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = get_settings()
    ext = Path(file.filename or "logo.png").suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        raise HTTPException(400, "Unsupported image type")
    name = f"logo_{uuid.uuid4().hex[:8]}{ext}"
    dest = s.uploads_dir / name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return SettingOut(key="company", value=set_setting(db, "company", {"logo_path": f"uploads/{name}"}))
