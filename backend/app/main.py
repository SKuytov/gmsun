from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register tables)
from .config import get_settings
from .db import Base, SessionLocal, engine
from .routers import auth, catalog, projects, quotes, settings, sizing
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="gmsun API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (auth.router, catalog.router, settings.router, projects.router, quotes.router, sizing.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": s.app_name}

    # uploaded images / PDFs
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/api/files", StaticFiles(directory=str(s.data_dir)), name="files")

    # serve the built frontend if present (single-container deployment)
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


app = create_app()
