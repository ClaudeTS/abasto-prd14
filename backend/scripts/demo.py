"""Datos de la demo armados con el pipeline real de C, para los scripts y los tests de A.

- `cotizaciones_fijas()`: data/extracciones_fijas.json normalizadas con `app.normalizacion`
  (Compuservice con el IVA confirmado, como hace Lucía en la demo).
- `contexto_demo(proveedor_id)`: lo mismo que recibe `ensayar` desde POST /negociar: solver de C
  sobre esas cotizaciones y `integracion_a.construir_contexto`.
"""

from app import integracion_a, optimizacion, pipeline, store
from app.models import ContextoNegociacion, Cotizacion, Pedido, Plan
from app.normalizacion import normalizar_cotizacion

CONFIRMAN_IVA = {"compuservice"}  # el "un clic" del guion


def pedido() -> Pedido:
    return Pedido.model_validate(pipeline.datos_pedido()["pedido"])


def normalizar(proveedor_id: str, crudo: dict) -> Cotizacion:
    datos = pipeline.datos_pedido()
    return normalizar_cotizacion(
        crudo,
        cotizacion_id=f"cot_{proveedor_id}",
        pedido_id=datos["pedido"]["id"],
        mensaje_id=f"msg_{proveedor_id}",
        proveedor_id=proveedor_id,
        catalogo={p.id: p.unidad_canonica for p in pipeline.catalogo()},
        conversiones=datos["conversiones"],
        tipo_cambio_usd=float(datos["config"]["tipo_cambio_usd"]),
        iva=float(datos["config"]["iva"]),
        incluye_iva_forzado=True if proveedor_id in CONFIRMAN_IVA else None,
    )


def cotizaciones_fijas() -> list[Cotizacion]:
    fijas = store.semilla("extracciones_fijas")["extracciones"]
    return [normalizar(pid, crudo) for pid, crudo in sorted(fijas.items())]


def plan_demo(cotizaciones: list[Cotizacion]) -> Plan:
    return optimizacion.optimizar(
        pedido(),
        cotizaciones,
        pipeline.proveedores(),
        tipo_cambio_usd=float(pipeline.datos_pedido()["config"]["tipo_cambio_usd"]),
        nombres_productos={p.id: p.nombre for p in pipeline.catalogo()},
    )


def contexto_demo(proveedor_id: str = "ofisillas") -> ContextoNegociacion:
    cotizaciones = cotizaciones_fijas()
    return integracion_a.construir_contexto(
        pedido(),
        plan_demo(cotizaciones),
        cotizaciones,
        pipeline.proveedores(),
        pipeline.perfil_privado(proveedor_id),
        proveedor_id,
        {p.id: p.nombre for p in pipeline.catalogo()},
    )
