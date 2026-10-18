"""Ingreso con usuario y contraseña (RF-21, PRD 1.4 §3 y §11.3 tabla `usuario`).

- Usuarios de ejemplo en data/usuarios_demo.json, con la contraseña en hash PBKDF2-SHA256 de
  `hashlib` (formato `pbkdf2_sha256$iteraciones$sal_hex$hash_hex`). Sin dependencias nuevas.
- Token firmado con HMAC-SHA256 y sin estado (`AUTH_SECRET`): sobrevive al botón de reset de la
  demo y a un reinicio del server. Vence a las 12 horas. Salir lo agrega a la colección
  "sesiones_revocadas" (se borra con el reset; el token igual vence).
- Los permisos por rol aplican solo a la edición de reglas y configuración (`requiere_admin`); el
  resto de la API queda abierta para no romper la demo guiada ni los tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Any, Literal

from fastapi import Header, HTTPException
from pydantic import BaseModel

from app import store

log = logging.getLogger("abasto.auth")

Rol = Literal["administrador", "consulta"]
ClienteInterno = Literal["ventas", "personal"]
DURACION_S = 12 * 3600
ITERACIONES = 120_000
_SECRETO_DEMO = "abasto-demo-no-usar-en-produccion"  # sin AUTH_SECRET: tokens de la demo


class Usuario(BaseModel):
    """Lo que ve la app (sin el hash)."""

    id: str
    nombre: str
    email: str
    rol: Rol
    cliente_interno: ClienteInterno


class UsuarioListado(Usuario):
    activo: bool
    ultimo_ingreso: datetime | None = None


class Ingreso(BaseModel):
    usuario: str  # email o nombre de usuario ("lucia")
    contrasena: str


class Sesion(BaseModel):
    token: str
    usuario: Usuario


class AuthError(Exception):
    def __init__(self, status: int, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


def _http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error": exc.error, "detalle": None})


# ---------------------------------------------------------------- contraseñas
def hash_contrasena(contrasena: str, *, sal: bytes | None = None, iteraciones: int = ITERACIONES) -> str:
    sal = sal or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, iteraciones)
    return f"pbkdf2_sha256${iteraciones}${sal.hex()}${dk.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        algoritmo, iteraciones, sal, esperado = guardado.split("$")
    except ValueError:
        return False
    if algoritmo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), bytes.fromhex(sal), int(iteraciones))
    return hmac.compare_digest(dk.hex(), esperado)


# ---------------------------------------------------------------- usuarios
def _registros() -> list[dict[str, Any]]:
    return store.semilla("usuarios_demo")["usuarios"]


def _publico(registro: dict[str, Any]) -> Usuario:
    return Usuario.model_validate(registro)


def usuarios() -> list[UsuarioListado]:
    ingresos = {k: v for k, v in ((r["id"], store.obtener_dict("ingresos", r["id"])) for r in _registros()) if v}
    return [
        UsuarioListado(**_publico(r).model_dump(), activo=r.get("activo", True), ultimo_ingreso=ingresos.get(r["id"]))
        for r in _registros()
    ]


def _buscar(identificador: str) -> dict[str, Any] | None:
    clave = identificador.strip().lower()
    return next(
        (r for r in _registros() if clave in (r["email"].lower(), r.get("usuario", "").lower())),
        None,
    )


# ---------------------------------------------------------------- tokens
def _secreto() -> bytes:
    return (os.environ.get("AUTH_SECRET") or _SECRETO_DEMO).encode("utf-8")


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _firmar(carga: str) -> str:
    return _b64(hmac.new(_secreto(), carga.encode("ascii"), hashlib.sha256).digest())


def emitir_token(usuario_id: str, *, ahora: float | None = None) -> str:
    ahora = time.time() if ahora is None else ahora
    carga = _b64(json.dumps({"u": usuario_id, "exp": int(ahora + DURACION_S), "n": secrets.token_hex(8)}).encode())
    return f"{carga}.{_firmar(carga)}"


def _leer_token(token: str) -> dict[str, Any]:
    try:
        carga, firma = token.split(".")
        datos = json.loads(_de_b64(carga))
    except (ValueError, json.JSONDecodeError):
        raise AuthError(401, "La sesión no es válida: ingresá de nuevo") from None
    if not hmac.compare_digest(firma, _firmar(carga)):
        raise AuthError(401, "La sesión no es válida: ingresá de nuevo")
    if datos.get("exp", 0) < time.time():
        raise AuthError(401, "La sesión venció: ingresá de nuevo")
    if store.obtener_dict("sesiones_revocadas", datos.get("n", "")):
        raise AuthError(401, "Cerraste esta sesión: ingresá de nuevo")
    return datos


def usuario_de_token(token: str) -> Usuario:
    datos = _leer_token(token)
    registro = next((r for r in _registros() if r["id"] == datos.get("u")), None)
    if registro is None or not registro.get("activo", True):
        raise AuthError(401, "El usuario no existe o está inactivo")
    return _publico(registro)


# ---------------------------------------------------------------- casos de uso
def ingresar(ingreso: Ingreso) -> Sesion:
    registro = _buscar(ingreso.usuario)
    if registro is None or not verificar_contrasena(ingreso.contrasena, registro["contrasena_hash"]):
        raise AuthError(401, "Usuario o contraseña incorrectos")
    if not registro.get("activo", True):
        raise AuthError(403, "El usuario está inactivo")
    store.guardar_dict("ingresos", registro["id"], datetime.now().astimezone().isoformat())
    log.info("Ingresó %s (%s)", registro["email"], registro["rol"])
    return Sesion(token=emitir_token(registro["id"]), usuario=_publico(registro))


def salir(token: str) -> None:
    datos = _leer_token(token)
    store.guardar_dict("sesiones_revocadas", datos["n"], {"usuario_id": datos["u"], "exp": datos["exp"]})


# ---------------------------------------------------------------- dependencias de FastAPI
def _token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    tipo, _, valor = authorization.partition(" ")
    return valor.strip() if tipo.lower() == "bearer" and valor.strip() else None


def token_requerido(authorization: str | None = Header(None)) -> str:
    token = _token(authorization)
    if token is None:
        raise _http(AuthError(401, "Tenés que ingresar con tu usuario"))
    return token


def usuario_requerido(authorization: str | None = Header(None)) -> Usuario:
    try:
        return usuario_de_token(token_requerido(authorization))
    except AuthError as exc:
        raise _http(exc) from exc


def requiere_admin(authorization: str | None = Header(None)) -> Usuario:
    """401 sin token o con uno inválido; 403 si el usuario no es administrador."""
    usuario = usuario_requerido(authorization)
    if usuario.rol != "administrador":
        raise _http(AuthError(403, "Solo el administrador de compras puede editar reglas y configuración"))
    return usuario
