"""Puntos de integración con el rol A (IA). Ver docs/CONTRATO_BACKEND.md §"Para A".

El backend no depende de que A haya terminado: si una función de A no existe todavía, el endpoint
devuelve un error claro (negociación) o usa un fallback determinístico (explicación del plan).

Funciones que A implementa y este módulo llama:
- app.extraccion.extraer_crudo(...)             -> dict   (lo llama app/pipeline.py)
- app.explicacion.explicar_plan(datos)          -> str
- app.negociacion.ensayar(contexto)             -> dict con estrategias, elegida, mensaje_propuesto
- app.llm.completar(system, user, temperature=…, max_tokens=…) -> str  (simulador en SIM_MODE=llm)
"""

from __future__ import annotations

import importlib
import logging
import uuid
from decimal import Decimal
from typing import Any

from app import config
from app.models import (
    ContextoNegociacion,
    Cotizacion,
    EstrategiaNegociacion,
    ItemNegociable,
    Negociacion,
    Pedido,
    Plan,
    Proveedor,
)
from app.normalizacion import CENTAVO, fmt

log = logging.getLogger("abasto.integracion_a")


class CapaNoDisponible(RuntimeError):
    """La función del rol A todavía no existe o no hay API key."""


def _funcion(modulo: str, nombre: str):
    try:
        return getattr(importlib.import_module(modulo), nombre, None)
    except ImportError:
        return None


# ---------------------------------------------------------------- explicación del plan
async def explicar(datos: dict[str, str]) -> str | None:
    """Texto del LLM o None (el caller usa la plantilla). Nunca rompe el /optimizar."""
    fn = _funcion("app.explicacion", "explicar_plan")
    if fn is None or not config.settings.anthropic_api_key:
        return None
    try:
        texto = await fn(datos)
    except Exception as exc:  # noqa: BLE001
        log.warning("explicar_plan falló (%s); uso la plantilla", exc)
        return None
    return texto.strip() or None


# ---------------------------------------------------------------- negociación
def construir_contexto(
    pedido: Pedido,
    plan: Plan,
    cotizaciones: list[Cotizacion],
    proveedores: dict[str, Proveedor],
    perfil_privado: dict[str, Any],
    proveedor_id: str,
    nombres_productos: dict[str, str],
) -> ContextoNegociacion:
    """Todo lo que el ensayo de negociación necesita, con números del plan (no del LLM)."""
    cot = next((c for c in cotizaciones if c.proveedor_id == proveedor_id), None)
    asignado = [a for a in plan.asignaciones if a.proveedor_id == proveedor_id]
    if cot is None or not asignado:
        raise ValueError(f"{proveedor_id} no tiene ítems en el plan de compra")
    demanda = {l.producto_id: l for l in pedido.lineas}
    items: list[ItemNegociable] = []
    for a in asignado:
        alternativas = [
            (c, i)
            for c in cotizaciones
            if c.proveedor_id != proveedor_id
            for i in c.items
            if i.producto_id == a.producto_id
        ]
        mejor = min(alternativas, key=lambda ci: ci[1].precio_unitario_sin_iva, default=None)
        condicion = None
        if mejor is not None:
            c_alt, i_alt = mejor
            linea = demanda[a.producto_id]
            dias = (linea.necesario_para - pedido.fecha).days
            if i_alt.cantidad_minima and i_alt.cantidad_minima > linea.cantidad:
                condicion = (
                    f"exige mínimo {fmt(i_alt.cantidad_minima)} unidades "
                    f"y el pedido es de {fmt(linea.cantidad)}"
                )
            elif c_alt.lead_time_dias > dias:
                condicion = f"entrega en {c_alt.lead_time_dias} días y se necesita en {dias}"
        items.append(
            ItemNegociable(
                producto_id=a.producto_id,
                cantidad=a.cantidad,
                precio_cotizado_sin_iva=a.precio_unitario_sin_iva,
                mejor_alternativa_proveedor_id=mejor[0].proveedor_id if mejor else None,
                mejor_alternativa_nombre=proveedores[mejor[0].proveedor_id].nombre if mejor else None,
                mejor_alternativa_precio=mejor[1].precio_unitario_sin_iva if mejor else None,
                mejor_alternativa_condicion=condicion,
            )
        )
    valor = sum((a.subtotal for a in asignado), Decimal(0))
    return ContextoNegociacion(
        pedido_id=pedido.id,
        negocio=pedido.negocio,
        comprador=pedido.comprador,
        proveedor=proveedores[proveedor_id],
        perfil_privado=perfil_privado,
        cotizacion=cot,
        items=items,
        valor_en_juego_uyu=valor.quantize(CENTAVO),
    )


def _elegir(estrategias: list[EstrategiaNegociacion]) -> str:
    """ARQUITECTURA §7: mayor ganancia con riesgo ≠ alto; si todas son altas, la de mayor ganancia."""
    candidatas = [e for e in estrategias if e.riesgo != "alto"] or estrategias
    return max(candidatas, key=lambda e: e.ganancia_esperada_uyu).nombre


async def negociar(contexto: ContextoNegociacion) -> Negociacion:
    fn = _funcion("app.negociacion", "ensayar")
    if fn is None:
        raise CapaNoDisponible("La negociación ensayada (Capa 5, rol A) todavía no está implementada")
    if not config.settings.anthropic_api_key:
        raise CapaNoDisponible("Falta ANTHROPIC_API_KEY en backend/.env para ensayar la negociación")
    resultado = await fn(contexto)
    estrategias = []
    for e in resultado["estrategias"]:
        e = dict(e)
        # El número lo pone el código: concesión × valor en juego (ARQUITECTURA §7.3).
        e["ganancia_esperada_uyu"] = (
            contexto.valor_en_juego_uyu * Decimal(str(e["concesion_obtenida_pct"])) / 100
        ).quantize(CENTAVO)
        estrategias.append(EstrategiaNegociacion.model_validate(e))
    elegida = _elegir(estrategias)
    if resultado.get("elegida") and resultado["elegida"] != elegida:
        log.warning("A eligió %s; por la regla de §7 corresponde %s", resultado["elegida"], elegida)
    return Negociacion(
        id=f"neg_{contexto.proveedor.id}_{uuid.uuid4().hex[:6]}",
        pedido_id=contexto.pedido_id,
        proveedor_id=contexto.proveedor.id,
        estrategias=estrategias,
        elegida=elegida,
        mensaje_propuesto=resultado["mensaje_propuesto"],
        estado="simulada",
    )
