"""Persistencia en archivos JSON (backend/data/runtime). Sin base de datos, a propósito.

- Datos semilla (solo lectura): pedido_demo.json, proveedores_sim.json, respuestas_fijas.json,
  extracciones_fijas.json.
- Runtime (lectura/escritura): una colección por archivo, `{id: objeto}`. `reset()` la borra.
- Cache (sobrevive a `make reset`): respuestas generadas por el simulador y extracciones del LLM.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app import config

T = TypeVar("T", bound=BaseModel)
_lock = threading.RLock()
_seed_cache: dict[str, Any] = {}

COLECCIONES = ("pedidos", "mensajes", "cotizaciones", "extracciones", "planes", "negociaciones")


# ---------------------------------------------------------------- semilla
def semilla(nombre: str) -> Any:
    """Lee un JSON semilla (cacheado en memoria). `nombre` sin extensión."""
    with _lock:
        if nombre not in _seed_cache:
            ruta = config.settings.seed_dir / f"{nombre}.json"
            if not ruta.exists():  # extracciones_fijas puede no estar en backend/data/
                ruta = config.REPO_DIR / "data" / f"{nombre}.json"
            _seed_cache[nombre] = json.loads(ruta.read_text(encoding="utf-8"))
        return _seed_cache[nombre]


# ---------------------------------------------------------------- runtime
def _ruta(coleccion: str) -> Path:
    return config.settings.runtime_dir / f"{coleccion}.json"


def _leer(coleccion: str) -> dict[str, Any]:
    ruta = _ruta(coleccion)
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir(coleccion: str, datos: dict[str, Any]) -> None:
    ruta = _ruta(coleccion)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(ruta)  # atómico: el polling nunca lee un archivo a medio escribir


def guardar(coleccion: str, obj: BaseModel) -> None:
    with _lock:
        datos = _leer(coleccion)
        datos[obj.id] = obj.model_dump(mode="json")  # type: ignore[attr-defined]
        _escribir(coleccion, datos)


def guardar_dict(coleccion: str, clave: str, valor: Any) -> None:
    with _lock:
        datos = _leer(coleccion)
        datos[clave] = valor
        _escribir(coleccion, datos)


def obtener(coleccion: str, clave: str, modelo: type[T]) -> T | None:
    with _lock:
        valor = _leer(coleccion).get(clave)
    return modelo.model_validate(valor) if valor is not None else None


def obtener_dict(coleccion: str, clave: str) -> Any:
    with _lock:
        return _leer(coleccion).get(clave)


def valores(coleccion: str) -> list[dict[str, Any]]:
    with _lock:
        return list(_leer(coleccion).values())


def listar(coleccion: str, modelo: type[T], **filtros: Any) -> list[T]:
    with _lock:
        valores = list(_leer(coleccion).values())
    return [
        modelo.model_validate(v)
        for v in valores
        if all(v.get(campo) == valor for campo, valor in filtros.items())
    ]


# ---------------------------------------------------------------- cache
def cache_leer(clave: str) -> Any:
    ruta = config.settings.cache_dir / f"{clave}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def cache_guardar(clave: str, valor: Any) -> None:
    ruta = config.settings.cache_dir / f"{clave}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


# ---------------------------------------------------------------- reset
def reset(borrar_cache: bool = False) -> None:
    with _lock:
        shutil.rmtree(config.settings.runtime_dir, ignore_errors=True)
        if borrar_cache:
            shutil.rmtree(config.settings.cache_dir, ignore_errors=True)
        config.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        _seed_cache.clear()
