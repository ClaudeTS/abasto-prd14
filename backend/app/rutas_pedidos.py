"""Pedidos: listado, detalle, conversaciones por canal y PDF (RF-05, 10, 12, 18). Ver docs/PRD-1.4.md.

| Método | Ruta | Devuelve |
|---|---|---|
| GET | `/pedidos` | `ListadoPedidos`: `{pedidos: ResumenPedido[], conteos, total}`. Filtros: `q`, `estado` (uno o varios separados por coma), `cliente_interno`, `origen`, `desde`/`hasta` (fecha de creación, inclusive), `situacion` (`en_tramite` · `recibidos` · `todos`). |
| GET | `/pedidos/{id}/detalle` | `DetallePedido` (app/historial_pedidos.py) |
| POST | `/pedidos/{id}/recibir` | `DetallePedido` · 409 si no está pendiente de entrega |
| POST | `/pedidos/{id}/cerrar` | `DetallePedido` · 409 si no está recibido |
| GET | `/pedidos/{id}/informe.pdf?incluir=pedido,dialogo` | PDF (RF-18) |

`GET /pedidos/{id}` sigue siendo el de main.py (el pedido de la demo, con su catálogo).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app import historial_pedidos as hp
from app.historial_pedidos import ESTADOS, DetallePedido, ResumenPedido

router = APIRouter()


class Conteos(BaseModel):
    en_tramite: int
    recibidos: int
    todos: int


class ListadoPedidos(BaseModel):
    pedidos: list[ResumenPedido]
    conteos: Conteos  # con los mismos filtros, sin el de situación: para las pestañas
    total: int  # los de `pedidos`


def _error(status: int, error: str, detalle: object = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "detalle": detalle})


def _detalle(pedido_id: str) -> DetallePedido:
    try:
        return hp.detalle(pedido_id)
    except hp.PedidoNoEncontrado as exc:
        raise _error(404, f"No existe el pedido '{pedido_id}'") from exc


@router.get("/pedidos", response_model=ListadoPedidos)
async def listar_pedidos(
    q: str | None = Query(None, description="Busca en productos, proveedores y número de orden de compra"),
    estado: str | None = Query(None, description="Estado del PRD §6.2; varios separados por coma"),
    cliente_interno: Literal["ventas", "personal"] | None = Query(None),
    origen: Literal["solicitud_voz", "solicitud_email", "stock_minimo", "zafra", "demo"] | None = Query(None),
    desde: date | None = Query(None, description="Creados desde esta fecha (inclusive)"),
    hasta: date | None = Query(None, description="Creados hasta esta fecha (inclusive)"),
    situacion: Literal["en_tramite", "recibidos", "todos"] = Query("todos"),
) -> ListadoPedidos:
    estados = {e.strip() for e in (estado or "").split(",") if e.strip()}
    if desconocidos := estados - set(ESTADOS):
        raise _error(422, f"Estado desconocido: {', '.join(sorted(desconocidos))}", {"validos": list(ESTADOS)})
    if desde and hasta and desde > hasta:
        raise _error(422, "La fecha «desde» es posterior a «hasta»")
    candidatos = []
    for d in hp.todos():
        if q and q.strip() and not hp.coincide(d, q):
            continue
        if estados and d.estado not in estados:
            continue
        if cliente_interno and d.cliente_interno != cliente_interno:
            continue
        if origen and d.origen != origen:
            continue
        if desde and d.creado_en.date() < desde:
            continue
        if hasta and d.creado_en.date() > hasta:
            continue
        candidatos.append(d)
    en_tramite = [d for d in candidatos if d.estado not in hp.FUERA_DE_TRAMITE]
    recibidos = [d for d in candidatos if d.estado in hp.RECIBIDOS]
    elegidos = {"en_tramite": en_tramite, "recibidos": recibidos, "todos": candidatos}[situacion]
    return ListadoPedidos(
        pedidos=[hp.resumen(d) for d in elegidos],
        conteos=Conteos(en_tramite=len(en_tramite), recibidos=len(recibidos), todos=len(candidatos)),
        total=len(elegidos),
    )


@router.get("/pedidos/{pedido_id}/detalle", response_model=DetallePedido)
async def detalle_pedido(pedido_id: str) -> DetallePedido:
    return _detalle(pedido_id)


def _marcar(pedido_id: str, estado: Literal["recibido", "cerrado"]) -> DetallePedido:
    _detalle(pedido_id)  # 404
    try:
        return hp.marcar(pedido_id, estado)
    except hp.TransicionInvalida as exc:
        raise _error(409, str(exc)) from exc


@router.post("/pedidos/{pedido_id}/recibir", response_model=DetallePedido)
async def recibir_pedido(pedido_id: str) -> DetallePedido:
    """La mercadería ingresó (§6.2: pendiente de entrega → recibido)."""
    return _marcar(pedido_id, "recibido")


@router.post("/pedidos/{pedido_id}/cerrar", response_model=DetallePedido)
async def cerrar_pedido(pedido_id: str) -> DetallePedido:
    """El pedido terminó y queda para consulta (§6.2: recibido → cerrado)."""
    return _marcar(pedido_id, "cerrado")


@router.get("/pedidos/{pedido_id}/informe.pdf")
async def informe_pdf(
    pedido_id: str,
    incluir: str = Query("pedido,dialogo", description="pedido, dialogo o ambos, separados por coma"),
) -> Response:
    from app import informe_pdf as informe  # reportlab solo cuando hace falta

    partes = {p.strip() for p in incluir.split(",") if p.strip()}
    if not partes or partes - {"pedido", "dialogo"}:
        raise _error(422, "«incluir» acepta pedido, dialogo o ambos (separados por coma)", {"recibido": incluir})
    d = _detalle(pedido_id)
    contenido = informe.generar(d, incluir_pedido="pedido" in partes, incluir_dialogo="dialogo" in partes)
    sufijo = "completo" if len(partes) == 2 else ("pedido" if "pedido" in partes else "dialogo")
    nombre = f"{d.numero}-{sufijo}.pdf"
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
