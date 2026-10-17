"""Configuración por variables de entorno (backend/.env). Sin dependencias: parser mínimo de .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


def _cargar_env(ruta: Path) -> None:
    """Carga KEY=VALOR de un .env sin pisar variables ya definidas en el entorno."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = valor.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(clave.strip(), valor)


_cargar_env(BACKEND_DIR / ".env")


def _float(nombre: str, defecto: float) -> float:
    try:
        return float(os.environ.get(nombre, "") or defecto)
    except ValueError:
        return defecto


@dataclass(frozen=True)
class Settings:
    llm_model: str
    anthropic_api_key: str
    enable_audio: bool
    sim_delay_seconds: float  # base 4: las demoras de los fixtures escalan con esto
    sim_mode: str  # "fijo" (fixtures, determinístico) | "llm" (genera con el LLM y cachea)
    extraccion_mode: str  # "auto" (LLM si está la Capa 1 y hay API key) | "fijo" | "llm"
    data_dir: Path  # backend/data: seed + runtime + cache
    seed_dir: Path  # de dónde se seedea: backend/data si `make seed` corrió, si no data/
    cors_origins: list[str]
    database_url: str  # Postgres (Supabase); vacío: archivos JSON en data_dir

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def archivos_dir(self) -> Path:
        return self.runtime_dir / "archivos"


def cargar_settings() -> Settings:
    data_dir = Path(os.environ.get("ABASTO_DATA_DIR", BACKEND_DIR / "data"))
    seed_dir = data_dir if (data_dir / "pedido_demo.json").exists() else REPO_DIR / "data"
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        llm_model=os.environ.get("LLM_MODEL", "claude-sonnet-5-5"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        enable_audio=os.environ.get("ENABLE_AUDIO", "0") == "1",
        sim_delay_seconds=_float("SIM_DELAY_SECONDS", 4.0),
        sim_mode=os.environ.get("SIM_MODE", "fijo"),
        extraccion_mode=os.environ.get("EXTRACCION_MODE", "auto"),
        data_dir=data_dir,
        seed_dir=seed_dir,
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
        database_url=os.environ.get("DATABASE_URL", "").strip(),
    )


settings = cargar_settings()
