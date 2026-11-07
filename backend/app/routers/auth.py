from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user, hash_password, require_admin, verify_password
from ..db import get_db
from ..models import User
from ..schemas import LoginIn, Token, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


def _login(db: Session, email: str, password: str) -> Token:
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash) or not user.active:
        raise HTTPException(401, "Грешен e-mail или парола")
    return Token(access_token=create_token(user), user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login_form(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return _login(db, form.username, form.password)


@router.post("/login-json", response_model=Token)
def login_json(body: LoginIn, db: Session = Depends(get_db)):
    return _login(db, body.email, body.password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Потребител с този e-mail вече съществува")
    u = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/users/{uid}", response_model=UserOut)
def update_user(uid: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404)
    if body.name is not None:
        u.name = body.name
    if body.role is not None:
        u.role = body.role
    if body.active is not None and uid != admin.id:
        u.active = body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(u)
    return u


@router.post("/change-password")
def change_password(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.get("old", ""), user.password_hash):
        raise HTTPException(400, "Грешна текуща парола")
    if len(body.get("new", "")) < 6:
        raise HTTPException(400, "Паролата трябва да е поне 6 символа")
    user.password_hash = hash_password(body["new"])
    db.commit()
    return {"ok": True}
