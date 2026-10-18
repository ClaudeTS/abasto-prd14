"""Ingreso con usuario y contraseña; registro visible pero no funcional (RF-21). Ver docs/PRD-1.4.md.

POST /auth/login → {token, usuario} · GET /auth/yo · POST /auth/logout · POST /auth/registro (501)
· GET /auth/usuarios (lista de solo lectura para el panel de configuración; pide sesión).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app import auth
from app.auth import Ingreso, Sesion, Usuario, UsuarioListado

router = APIRouter(prefix="/auth", tags=["auth"])


def _error(exc: auth.AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error": exc.error, "detalle": None})


@router.post("/login", response_model=Sesion)
async def login(ingreso: Ingreso) -> Sesion:
    try:
        return auth.ingresar(ingreso)
    except auth.AuthError as exc:
        raise _error(exc) from exc


@router.get("/yo", response_model=Usuario)
async def yo(usuario: Usuario = Depends(auth.usuario_requerido)) -> Usuario:
    return usuario


@router.post("/logout", status_code=204, response_class=Response)
async def logout(token: str = Depends(auth.token_requerido)) -> Response:
    try:
        auth.salir(token)
    except auth.AuthError:
        pass  # ya vencida o inválida: igual queda afuera
    return Response(status_code=204)


@router.post("/registro", status_code=501)
async def registro() -> None:
    raise HTTPException(
        status_code=501,
        detail={"error": "El registro todavía no está disponible", "detalle": "PRD 1.4, RF-21: pantalla visible, no funcional"},
    )


@router.get("/usuarios", response_model=list[UsuarioListado])
async def listar_usuarios(_: Usuario = Depends(auth.usuario_requerido)) -> list[UsuarioListado]:
    return auth.usuarios()
