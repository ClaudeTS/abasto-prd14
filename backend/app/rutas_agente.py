"""Endpoints del inventario y del agente de compras (docs/AGENTE.md). Se montan en main.py.

Errores con la misma forma que el resto de la API: `{"error": "mensaje legible", "detalle": ...}`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import agente, inventario
from app.agente import Confirmacion, CorridaAgente, NuevaCorrida
from app.inventario import CambioInventario, Inventario, ItemInventario

router = APIRouter()


def _error(status: int, error: str, detalle: object = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "detalle": detalle})


def _del_agente(exc: agente.AgenteError) -> HTTPException:
    return _error(exc.status, exc.error, exc.detalle)


# ---------------------------------------------------------------- inventario
@router.get("/inventario", response_model=Inventario)
async def ver_inventario(
    horizonte_meses: int | None = Query(None, ge=1, le=6, description="Meses a cubrir con la reposición"),
) -> Inventario:
    return inventario.inventario(horizonte_meses)


@router.patch("/inventario/{producto_id}", response_model=ItemInventario)
async def cambiar_inventario(producto_id: str, cambio: CambioInventario) -> ItemInventario:
    try:
        return inventario.cambiar(producto_id, cambio)
    except inventario.InventarioError as exc:
        status = 404 if "No hay inventario" in str(exc) else 422
        raise _error(status, str(exc)) from exc


# ---------------------------------------------------------------- agente
@router.get("/agente/ejemplo")
async def ejemplo() -> dict[str, str]:
    return agente.ejemplo()


@router.get("/agente/actual", response_model=CorridaAgente)
async def corrida_actual() -> CorridaAgente:
    corrida = agente.actual()
    if corrida is None:
        raise _error(404, "Todavía no hay ninguna compra del agente")
    return agente.obtener(corrida.id)


@router.post("/agente", response_model=CorridaAgente, status_code=201)
async def iniciar(nueva: NuevaCorrida | None = None) -> CorridaAgente:
    try:
        return agente.iniciar(nueva or NuevaCorrida())
    except agente.AgenteError as exc:
        raise _del_agente(exc) from exc


@router.get("/agente/{corrida_id}", response_model=CorridaAgente)
async def corrida(corrida_id: str) -> CorridaAgente:
    try:
        return agente.obtener(corrida_id)
    except agente.AgenteError as exc:
        raise _del_agente(exc) from exc


@router.post("/agente/{corrida_id}/confirmar", response_model=CorridaAgente)
async def confirmar(corrida_id: str, confirmacion: Confirmacion | None = None) -> CorridaAgente:
    try:
        return agente.confirmar(corrida_id, confirmacion)
    except agente.AgenteError as exc:
        raise _del_agente(exc) from exc


@router.post("/agente/{corrida_id}/ordenes/{orden_id}/aprobar", response_model=CorridaAgente)
async def aprobar_orden(corrida_id: str, orden_id: str) -> CorridaAgente:
    try:
        return agente.aprobar_orden(corrida_id, orden_id)
    except agente.AgenteError as exc:
        raise _del_agente(exc) from exc


@router.post("/agente/{corrida_id}/ordenes/{orden_id}/rechazar", response_model=CorridaAgente)
async def rechazar_orden(corrida_id: str, orden_id: str) -> CorridaAgente:
    try:
        return agente.rechazar_orden(corrida_id, orden_id)
    except agente.AgenteError as exc:
        raise _del_agente(exc) from exc


@router.post("/agente/{corrida_id}/cancelar", response_model=CorridaAgente)
async def cancelar(corrida_id: str) -> CorridaAgente:
    try:
        return agente.cancelar(corrida_id)
    except agente.AgenteError as exc:
        raise _del_agente(exc) from exc
