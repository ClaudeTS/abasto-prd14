"""Reglas por producto, historial y configuración general (RF-13, 14, 15, 20). Ver docs/PRD-1.4.md.

Lectura abierta (todos consultan); los cambios exigen token de administrador (401 sin sesión, 403 si
el rol es consulta). La lógica está en `app/reglas.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import reglas
from app.auth import Usuario, requiere_admin
from app.reglas import (
    CambioConfiguracion,
    CambioRegla,
    CambioReglas,
    Configuracion,
    PropuestaReglas,
    Revertir,
    VistaPrevia,
    VistaReglas,
)

router = APIRouter(tags=["reglas"])


def _error(exc: reglas.ReglasError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error": exc.error, "detalle": exc.detalle})


# ---------------------------------------------------------------- reglas por producto
@router.get("/reglas", response_model=list[VistaReglas])
async def listar() -> list[VistaReglas]:
    return reglas.todas()


@router.get("/reglas/{producto_id}", response_model=VistaReglas)
async def ver(producto_id: str) -> VistaReglas:
    try:
        return reglas.vista(producto_id)
    except reglas.ReglasError as exc:
        raise _error(exc) from exc


@router.patch("/reglas/{producto_id}", response_model=VistaReglas)
async def cambiar(producto_id: str, cambio: CambioReglas, usuario: Usuario = Depends(requiere_admin)) -> VistaReglas:
    try:
        return reglas.cambiar(producto_id, cambio, usuario)
    except reglas.ReglasError as exc:
        raise _error(exc) from exc


@router.post("/reglas/{producto_id}/vista-previa", response_model=VistaPrevia)
async def vista_previa(producto_id: str, propuesta: PropuestaReglas) -> VistaPrevia:
    try:
        return reglas.vista_previa(producto_id, propuesta)
    except reglas.ReglasError as exc:
        raise _error(exc) from exc


@router.get("/reglas/{producto_id}/historial", response_model=list[CambioRegla])
async def historial(producto_id: str) -> list[CambioRegla]:
    try:
        reglas.actuales(producto_id)  # 404 si no existe
    except reglas.ReglasError as exc:
        raise _error(exc) from exc
    return reglas.historial(producto_id)


@router.post("/reglas/{producto_id}/historial/{cambio_id}/revertir", response_model=VistaReglas)
async def revertir(
    producto_id: str,
    cambio_id: str,
    cuerpo: Revertir | None = None,
    usuario: Usuario = Depends(requiere_admin),
) -> VistaReglas:
    try:
        return reglas.revertir(producto_id, cambio_id, usuario, cuerpo.motivo if cuerpo else None)
    except reglas.ReglasError as exc:
        raise _error(exc) from exc


# ---------------------------------------------------------------- configuración general
@router.get("/configuracion", response_model=Configuracion)
async def ver_configuracion() -> Configuracion:
    return reglas.configuracion()


@router.patch("/configuracion", response_model=Configuracion)
async def cambiar_configuracion(
    cambio: CambioConfiguracion, usuario: Usuario = Depends(requiere_admin)
) -> Configuracion:
    try:
        return reglas.cambiar_configuracion(cambio, usuario)
    except reglas.ReglasError as exc:
        raise _error(exc) from exc


@router.get("/configuracion/historial", response_model=list[CambioRegla])
async def historial_configuracion() -> list[CambioRegla]:
    return reglas.historial(None, tabla="configuracion")
