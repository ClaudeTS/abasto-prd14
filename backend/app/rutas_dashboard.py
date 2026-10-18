"""Dashboard: KPI y recomendaciones de la IA (RF-09). Ver docs/PRD-1.4.md §4 y §11.3.

Errores con la forma de siempre: `{"error": "mensaje legible", "detalle": ...}`.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app import kpi, recomendaciones
from app.kpi import ClienteInterno, Dashboard
from app.recomendaciones import Recomendacion, Recomendaciones

router = APIRouter()


def _error(status: int, error: str, detalle: object = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "detalle": detalle})


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    desde: date | None = Query(None, description="Inicio del período (por defecto, 30 días antes de «hasta»)"),
    hasta: date | None = Query(None, description="Fin del período, inclusive (por defecto, hoy)"),
    cliente_interno: ClienteInterno | None = Query(None, description="ventas | personal; vacío: todos"),
) -> Dashboard:
    try:
        periodo = kpi.periodo(desde, hasta, cliente_interno)
    except ValueError as exc:
        raise _error(422, str(exc)) from exc
    return kpi.dashboard(periodo)


@router.get("/dashboard/recomendaciones", response_model=Recomendaciones)
async def listar_recomendaciones(
    umbral_alza_pct: float | None = Query(None, ge=0, le=100, description="Alza sobre el promedio que dispara la alerta (default 8)"),
    incluir_descartadas: bool = Query(False),
) -> Recomendaciones:
    return recomendaciones.listar(umbral_pct=umbral_alza_pct, incluir_descartadas=incluir_descartadas)


@router.post("/dashboard/recomendaciones/{reco_id}/descartar", response_model=Recomendacion)
async def descartar_recomendacion(reco_id: str) -> Recomendacion:
    try:
        return recomendaciones.descartar(reco_id)
    except recomendaciones.RecomendacionNoEncontrada as exc:
        raise _error(404, f"No existe la recomendación '{reco_id}' (o ya no aplica)") from exc
