"""Proveedores: listado, perfil de negociación, alta por el agente, ranking (RF-07, 16, 17, 19).

Ver docs/PRD-1.4.md §11.1, §11.5 y §11.6. `GET /proveedores` (main.py) no se toca: estas son rutas
nuevas. Las rutas fijas (`/proveedores/listado`, `/proveedores/alta…`) van antes que las de `{id}`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app import perfiles, ranking
from app.auth import Usuario, requiere_admin
from app.perfiles import AltaAgente, AltaManual, AprobacionAlta, PerfilEdicion

router = APIRouter()


def _error(status: int, error: str, detalle: object = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "detalle": detalle})


def _proveedor(proveedor_id: str) -> None:
    if not perfiles.existe(proveedor_id):
        raise _error(404, f"No existe el proveedor '{proveedor_id}'")


# ---------------------------------------------------------------- RF-17: listado y perfil
@router.get("/proveedores/listado")
async def listado() -> dict:
    return {
        "proveedores": perfiles.listado(),
        "datos_ejemplo": ranking.DATOS_EJEMPLO + ["negociaciones históricas"],
        "umbrales_confianza": {
            "alta_pp": perfiles.CONFIANZA_ALTA_PP,
            "media_pp": perfiles.CONFIANZA_MEDIA_PP,
            "min_negociaciones": perfiles.MIN_NEGOCIACIONES,
        },
    }


@router.get("/proveedores/{proveedor_id}/perfil")
async def ver_perfil(proveedor_id: str) -> dict:
    _proveedor(proveedor_id)
    return perfiles.perfil(proveedor_id)


@router.patch("/proveedores/{proveedor_id}/perfil")
async def editar_perfil(
    proveedor_id: str, cambios: PerfilEdicion, usuario: Usuario = Depends(requiere_admin)
) -> dict:
    """Solo el administrador: 401 sin sesión, 403 con rol consulta. Quién editó sale de la sesión."""
    _proveedor(proveedor_id)
    return perfiles.editar(proveedor_id, cambios.model_copy(update={"usuario": usuario.nombre}))


# ---------------------------------------------------------------- RF-19: altas
@router.post("/proveedores/alta", status_code=201)
async def alta_manual(datos: AltaManual) -> dict:
    return perfiles.alta_manual(datos)


@router.post("/proveedores/alta-agente", status_code=201)
async def alta_agente(datos: AltaAgente) -> dict:
    """Simulado: el agente contacta al proveedor, le pide los datos y lo deja en revisión."""
    return perfiles.alta_por_agente(datos)


@router.post("/proveedores/{proveedor_id}/aprobar-alta")
async def aprobar_alta(
    proveedor_id: str, datos: AprobacionAlta | None = None, usuario: Usuario = Depends(requiere_admin)
) -> dict:
    """Solo el administrador aprueba o rechaza el alta que dejó el agente."""
    try:
        datos = (datos or AprobacionAlta()).model_copy(update={"usuario": usuario.nombre})
        return perfiles.aprobar_alta(proveedor_id, datos)
    except KeyError as exc:
        raise _error(404, f"No hay un alta pendiente para '{proveedor_id}'") from exc
    except ValueError as exc:
        raise _error(409, str(exc)) from exc


# ---------------------------------------------------------------- RF-07 y RF-16
@router.get("/pedidos/{pedido_id}/ranking")
async def ranking_pedido(
    pedido_id: str, producto_id: str | None = Query(None, description="Un solo producto del pedido")
) -> dict:
    try:
        return ranking.ranking(pedido_id, producto_id)
    except ranking.NoEncontrado as exc:
        raise _error(404, exc.args[0]) from exc


@router.get("/negociaciones/{negociacion_id}/evaluacion")
async def evaluacion(negociacion_id: str) -> dict:
    try:
        return ranking.evaluacion(negociacion_id)
    except ranking.NoEncontrado as exc:
        raise _error(404, exc.args[0]) from exc
