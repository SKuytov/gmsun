from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "gmsun"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./gmsun.db")
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@gmsun.local")
    admin_password: str = os.getenv("ADMIN_PASSWORD", "admin1234")
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
    ]
    seed_demo: bool = os.getenv("SEED_DEMO", "true").lower() in ("1", "true", "yes")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pdf_dir(self) -> Path:
        return self.data_dir / "pdf"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    s.pdf_dir.mkdir(parents=True, exist_ok=True)
    return s
