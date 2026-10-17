"""Pedido de la demo en runtime: se seedea de data/pedido_demo.json y guarda su estado."""

from __future__ import annotations

from app import store
from app.models import Pedido, PedidoCompleto
from app.pipeline import catalogo, datos_pedido

PEDIDO_DEMO_ID = "pedido_demo_oct_2026"


def obtener(pedido_id: str) -> Pedido | None:
    pedido = store.obtener("pedidos", pedido_id, Pedido)
    if pedido is None and pedido_id == datos_pedido()["pedido"]["id"]:
        pedido = Pedido.model_validate(datos_pedido()["pedido"])
        store.guardar("pedidos", pedido)
    return pedido


def completo(pedido: Pedido) -> PedidoCompleto:
    datos = datos_pedido()
    return PedidoCompleto(
        **pedido.model_dump(),
        catalogo=catalogo(),
        conversiones=datos["conversiones"],
        tipo_cambio_usd=float(datos["config"]["tipo_cambio_usd"]),
        iva=float(datos["config"]["iva"]),
    )


def cambiar_estado(pedido_id: str, estado: str) -> None:
    pedido = obtener(pedido_id)
    if pedido is not None:
        pedido.estado = estado  # type: ignore[assignment]
        store.guardar("pedidos", pedido)
