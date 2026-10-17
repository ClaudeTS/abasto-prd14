"""Persistencia en archivos JSON (backend/data/runtime), o en Postgres si hay DATABASE_URL (Supabase).

- Datos semilla (solo lectura): pedido_demo.json, proveedores_sim.json, respuestas_fijas.json,
  extracciones_fijas.json. Siempre de archivos: vienen con el repo.
- Runtime (lectura/escritura): una colección por archivo, `{id: objeto}`; en Postgres, filas de
  `documentos (coleccion, id, datos)`. `reset()` la borra.
- Cache (sobrevive a `make reset`): respuestas generadas por el simulador y extracciones del LLM;
  en Postgres, la tabla `cache`.
- Archivos (PDF y fotos): siempre en disco (runtime/archivos), porque se leen por ruta. En Postgres
  además se suben a `archivos`, así sobreviven a un reinicio del server (el disco de Render se borra).
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import threading
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app import config

T = TypeVar("T", bound=BaseModel)
_lock = threading.RLock()
_seed_cache: dict[str, Any] = {}

COLECCIONES = (
    "pedidos", "mensajes", "cotizaciones", "extracciones", "planes", "negociaciones", "llamadas",
)


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


# ---------------------------------------------------------------- Postgres (si hay DATABASE_URL)
_ESQUEMA = """
create table if not exists documentos (
  coleccion text not null,
  id text not null,
  datos jsonb not null,
  creado_en timestamptz not null default now(),
  actualizado_en timestamptz not null default now(),
  primary key (coleccion, id)
);
create table if not exists archivos (
  nombre text primary key,
  tipo text not null,
  contenido bytea not null,
  creado_en timestamptz not null default now()
);
create table if not exists cache (
  clave text primary key,
  valor jsonb not null,
  creado_en timestamptz not null default now()
);
alter table documentos enable row level security;
alter table archivos   enable row level security;
alter table cache      enable row level security;
"""
# Sin políticas de RLS: la clave pública de Supabase no ve nada. El backend entra como dueño.

_conexion: Any = None
_dumps = partial(json.dumps, ensure_ascii=False, default=str)  # lo mismo que en los archivos


def _con_db() -> bool:
    return bool(config.settings.database_url)


def _db() -> Any:
    global _conexion
    if _conexion is None or _conexion.closed or _conexion.broken:
        import psycopg  # solo hace falta con DATABASE_URL

        _conexion = psycopg.connect(
            config.settings.database_url,
            autocommit=True,
            connect_timeout=10,
            prepare_threshold=None,  # el pooler de Supabase en modo transacción no los soporta
        )
        _conexion.execute(_ESQUEMA)
    return _conexion


def _sql(consulta: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Ejecuta con un reintento: el pooler corta las conexiones ociosas."""
    import psycopg

    global _conexion
    with _lock:  # una sola conexión, compartida
        for intento in range(2):
            try:
                cur = _db().execute(consulta, params)
                return cur.fetchall() if cur.description else []
            except psycopg.OperationalError:
                _conexion = None
                if intento:
                    raise
    return []


def _jsonb(valor: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(valor, dumps=_dumps)


# ---------------------------------------------------------------- runtime
def _ruta(coleccion: str) -> Path:
    return config.settings.runtime_dir / f"{coleccion}.json"


def _leer(coleccion: str) -> dict[str, Any]:
    if _con_db():  # en orden de creación, como las claves del archivo
        return dict(
            _sql(
                "select id, datos from documentos where coleccion = %s order by creado_en, id",
                (coleccion,),
            )
        )
    ruta = _ruta(coleccion)
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def _leer_uno(coleccion: str, clave: str) -> Any:
    if _con_db():
        filas = _sql(
            "select datos from documentos where coleccion = %s and id = %s", (coleccion, clave)
        )
        return filas[0][0] if filas else None
    return _leer(coleccion).get(clave)


def _escribir(coleccion: str, datos: dict[str, Any]) -> None:
    ruta = _ruta(coleccion)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    tmp.replace(ruta)  # atómico: el polling nunca lee un archivo a medio escribir


def guardar(coleccion: str, obj: BaseModel) -> None:
    guardar_dict(coleccion, obj.id, obj.model_dump(mode="json"))  # type: ignore[attr-defined]


def guardar_dict(coleccion: str, clave: str, valor: Any) -> None:
    if _con_db():
        _sql(
            "insert into documentos (coleccion, id, datos) values (%s, %s, %s) "
            "on conflict (coleccion, id) do update set datos = excluded.datos, actualizado_en = now()",
            (coleccion, clave, _jsonb(valor)),
        )
        return
    with _lock:
        datos = _leer(coleccion)
        datos[clave] = valor
        _escribir(coleccion, datos)


def obtener(coleccion: str, clave: str, modelo: type[T]) -> T | None:
    with _lock:
        valor = _leer_uno(coleccion, clave)
    return modelo.model_validate(valor) if valor is not None else None


def obtener_dict(coleccion: str, clave: str) -> Any:
    with _lock:
        return _leer_uno(coleccion, clave)


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


# ---------------------------------------------------------------- archivos
def subir_archivo(nombre: str) -> None:
    """Con Postgres, copia runtime/archivos/<nombre> a la tabla `archivos`. Sin base, no hace nada."""
    if not _con_db():
        return
    contenido = (config.settings.archivos_dir / nombre).read_bytes()
    tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    _sql(
        "insert into archivos (nombre, tipo, contenido) values (%s, %s, %s) "
        "on conflict (nombre) do update set tipo = excluded.tipo, contenido = excluded.contenido",
        (nombre, tipo, contenido),
    )


def asegurar_archivo(nombre: str) -> bool:
    """¿Está runtime/archivos/<nombre> en disco? Con Postgres lo baja si falta (server reiniciado)."""
    ruta = config.settings.archivos_dir / nombre
    if ruta.is_file():
        return True
    if not _con_db() or Path(nombre).name != nombre:
        return False
    filas = _sql("select contenido from archivos where nombre = %s", (nombre,))
    if not filas:
        return False
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(bytes(filas[0][0]))
    return True


# ---------------------------------------------------------------- cache
def cache_leer(clave: str) -> Any:
    if _con_db():
        filas = _sql("select valor from cache where clave = %s", (clave,))
        return filas[0][0] if filas else None
    ruta = config.settings.cache_dir / f"{clave}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def cache_guardar(clave: str, valor: Any) -> None:
    if _con_db():
        _sql(
            "insert into cache (clave, valor) values (%s, %s) "
            "on conflict (clave) do update set valor = excluded.valor, creado_en = now()",
            (clave, _jsonb(valor)),
        )
        return
    ruta = config.settings.cache_dir / f"{clave}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


# ---------------------------------------------------------------- reset
def reset(borrar_cache: bool = False) -> None:
    with _lock:
        if _con_db():
            _sql("delete from documentos")
            _sql("delete from archivos")
            if borrar_cache:
                _sql("delete from cache")
        shutil.rmtree(config.settings.runtime_dir, ignore_errors=True)
        if borrar_cache:
            shutil.rmtree(config.settings.cache_dir, ignore_errors=True)
        config.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        _seed_cache.clear()
