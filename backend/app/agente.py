"""Agente de compras: hace la compra entera (docs/AGENTE.md).

Una corrida por pedido, con estos pasos: entender (LLM, `app/interpretacion.py`) → inventario
(`app/inventario.py`) → confirmar (Lucía) → cotizar (simulador de siempre) → insistir (llama al que
no responde) → revisar (Lucía confirma lo dudoso) → optimizar (solver) → negociar (gemelo) → órdenes.

El agente manda solo la orden de un proveedor si todos sus productos están en modo automático y
ninguno supera su tope (sin IVA); el resto espera el OK de Lucía. Nada sale de verdad: las órdenes
quedan en "enviada_simulada".

Corre en una tarea de asyncio y guarda la corrida en la colección "agentes" en cada cambio; la UI
hace polling. Para no pisar lo que cambian los endpoints (confirmar, aprobar), la corrida se relee
después de cada `await`. Los pasos son idempotentes: si el server se reinicia, `obtener` relanza la
tarea y cada paso se fija en lo que ya está hecho (pedido, cotizaciones, plan, negociación).
Optimizar y negociar llaman a los handlers de `main.py`: mismas validaciones y mismos estados que
las pantallas de detalle.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app import config, interpretacion, inventario, llamadas, pedidos, pipeline, simulador, store
from app.interpretacion import Interpretacion, ItemInterpretado
from app.inventario import ItemInventario, Modo
from app.models import Cotizacion, LineaPedido, Llamada, MensajeCrudo, Monto, Negociacion, Plan
from app.normalizacion import fmt

log = logging.getLogger("abasto.agente")

SEGUNDOS_PARA_INSISTIR = 25.0  # como el Feed; se escala con SIM_DELAY_SECONDS (base 4)
UMBRAL_MINIMO_S = 10.0  # con SIM_DELAY_SECONDS=0 la escala es 0, y con SIM_MODE=llm generar tarda
ESPERA_MAXIMA_S = 120.0  # sin respuesta ni llamada en curso: el plan se arma sin ese proveedor
ESPERA_MAXIMA_MINIMA_S = 30.0
LLAMADA_MAXIMA_S = 600.0  # una llamada no se reanuda si el server se reinicia: no esperarla para siempre
INTERVALO_S = 1.0
DIAS_SIN_FECHA = 7  # equipamiento pedido sin fecha

EstadoCorrida = Literal[
    "en_curso",
    "esperando_confirmacion",
    "esperando_revision",
    "esperando_aprobacion",
    "completada",
    "error",
    "cancelada",
]
TERMINADAS = ("completada", "error", "cancelada")
CON_TAREA = ("en_curso", "esperando_confirmacion", "esperando_revision")
PASOS = (
    ("entender", "Entender el pedido"),
    ("inventario", "Revisar el inventario"),
    ("confirmar", "Tu OK para cotizar"),
    ("cotizar", "Pedir cotizaciones"),
    ("insistir", "Llamar a quien no responde"),
    ("revisar", "Revisar respuestas dudosas"),
    ("optimizar", "Armar el plan de compra"),
    ("negociar", "Ensayar la negociación"),
    ("ordenes", "Órdenes de compra"),
)


# ---------------------------------------------------------------- modelos
class PasoAgente(BaseModel):
    id: str
    titulo: str
    estado: Literal["pendiente", "en_curso", "esperando", "hecho", "omitido", "error"] = "pendiente"
    detalle: str | None = None
    inicio: datetime | None = None
    fin: datetime | None = None


class LineaPropuesta(BaseModel):
    producto_id: str
    nombre: str
    nombre_corto: str
    unidad: str
    cantidad: float
    necesario_para: date
    origen: Literal["pedido", "reposicion"]  # lo pidió Lucía | lo calculó el inventario
    modo: Modo
    tope_automatico_uyu: Monto | None
    stock_actual: float
    evidencia: str
    dudas: list[str] = Field(default_factory=list)


class RevisionPendiente(BaseModel):
    cotizacion_id: str
    proveedor_id: str
    proveedor_nombre: str
    campos_dudosos: list[str]
    pide_iva: bool  # sí: botones "incluye IVA" / "es + IVA"; no: "está bien así"
    pregunta: str


class LineaOrden(BaseModel):
    producto_id: str
    nombre: str
    nombre_corto: str
    unidad: str
    cantidad: float
    precio_unitario_sin_iva: Monto
    subtotal: Monto
    aprobacion: Literal["automatica", "manual", "supera_tope"]
    motivo: str
    cotizacion_id: str | None
    evidencia: str | None  # de la cotización: de dónde sale el precio


class OrdenCompra(BaseModel):
    id: str
    numero: str  # OC-1001
    proveedor_id: str
    proveedor_nombre: str
    lineas: list[LineaOrden]
    envio: Monto
    total_sin_iva: Monto
    total_con_iva: Monto
    requiere_aprobacion: bool
    motivos: list[str]
    estado: Literal["esperando_aprobacion", "enviada_simulada", "rechazada"]
    aprobada_por: Literal["agente", "lucia"] | None = None
    negociacion_id: str | None = None
    mensaje: str
    enviada_en: datetime | None = None


class OpcionesCorrida(BaseModel):
    horizonte_meses: int | None = Field(None, ge=1, le=6)  # None: el que diga Lucía o el de siempre
    esperar_confirmacion: bool = True
    llamar_si_no_responde: bool = True
    negociar: bool = True


class NuevaCorrida(OpcionesCorrida):
    texto: str | None = None


class LineaConfirmada(BaseModel):
    producto_id: str
    cantidad: float


class Confirmacion(BaseModel):
    lineas: list[LineaConfirmada] | None = None  # None: la propuesta tal cual


class CorridaAgente(BaseModel):
    id: str
    pedido_id: str
    texto: str | None
    horizonte_meses: int
    opciones: OpcionesCorrida
    estado: EstadoCorrida
    pasos: list[PasoAgente]
    interpretacion: Interpretacion | None = None
    propuesta: list[LineaPropuesta] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    revision: list[RevisionPendiente] = Field(default_factory=list)
    llamada_ids: list[str] = Field(default_factory=list)
    sin_respuesta: list[str] = Field(default_factory=list)  # proveedores que nunca respondieron
    negociacion_id: str | None = None
    ordenes: list[OrdenCompra] = Field(default_factory=list)
    resumen: str | None = None
    error: str | None = None
    creada_en: datetime
    actualizada_en: datetime


class AgenteError(Exception):
    """Error para devolver tal cual: status y mensaje legible (los endpoints lo pasan a HTTP)."""

    def __init__(self, status: int, error: str, detalle: object = None) -> None:
        super().__init__(error)
        self.status, self.error, self.detalle = status, error, detalle


class _Detenida(Exception):
    """La corrida se canceló o se borró (reset): la tarea termina sin tocar nada."""


class _Fallo(Exception):
    def __init__(self, paso: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.paso = paso


class _NadaQueComprar(Exception):
    pass


# ---------------------------------------------------------------- estado
_tareas: dict[str, asyncio.Task] = {}


def _ahora() -> datetime:
    return datetime.now()


def _cargar(corrida_id: str) -> CorridaAgente | None:
    return store.obtener("agentes", corrida_id, CorridaAgente)


def _vigente(corrida_id: str) -> CorridaAgente:
    corrida = _cargar(corrida_id)
    if corrida is None or corrida.estado == "cancelada":
        raise _Detenida
    return corrida


def _guardar(corrida: CorridaAgente) -> None:
    corrida.actualizada_en = _ahora()
    store.guardar("agentes", corrida)


def _paso(corrida: CorridaAgente, paso_id: str) -> PasoAgente:
    return next(p for p in corrida.pasos if p.id == paso_id)


def _marcar(corrida: CorridaAgente, paso_id: str, estado: str, detalle: str | None = None) -> None:
    paso = _paso(corrida, paso_id)
    ahora = _ahora()
    paso.inicio = paso.inicio or ahora
    if estado in ("hecho", "omitido", "error"):
        paso.fin = ahora
    paso.estado = estado  # type: ignore[assignment]
    if detalle is not None:
        paso.detalle = detalle


def _escala() -> float:
    return max(config.settings.sim_delay_seconds, 0.0) / 4.0


def _proveedores() -> dict[str, str]:
    return {pid: p.nombre for pid, p in pipeline.proveedores().items()}


def _cotizaciones(pedido_id: str) -> list[Cotizacion]:
    return sorted(store.listar("cotizaciones", Cotizacion, pedido_id=pedido_id), key=lambda c: c.proveedor_id)


def _cotizaciones_usadas(pedido_id: str) -> dict[str, Cotizacion]:
    """Por proveedor, la última que no está para revisar: la que usa el solver."""
    return {c.proveedor_id: c for c in _cotizaciones(pedido_id) if c.estado != "revisar"}


def _enumerar(partes: list[str]) -> str:
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _cantidad(cantidad: float, nombre_corto: str, unidad: str) -> str:
    return f"{fmt(cantidad)} L de {nombre_corto}" if unidad == "l" else f"{fmt(cantidad)} {nombre_corto}"


def _mensaje_http(exc: HTTPException) -> str:
    return exc.detail.get("error", str(exc.detail)) if isinstance(exc.detail, dict) else str(exc.detail)


# ---------------------------------------------------------------- API (la usan los endpoints)
def ejemplo() -> dict[str, str]:
    return {"texto": interpretacion.frase_demo()}


def actual() -> CorridaAgente | None:
    return max(store.listar("agentes", CorridaAgente), key=lambda c: c.creada_en, default=None)


def obtener(corrida_id: str) -> CorridaAgente:
    corrida = _cargar(corrida_id)
    if corrida is None:
        raise AgenteError(404, f"No existe la corrida '{corrida_id}'")
    if corrida.estado in CON_TAREA:
        _lanzar(corrida.id)  # p. ej. el server se reinició a mitad de la corrida
    return corrida


def iniciar(nueva: NuevaCorrida) -> CorridaAgente:
    previa = actual()
    if previa is not None and previa.estado not in TERMINADAS:
        raise AgenteError(409, "Ya hay una compra en curso", {"corrida_id": previa.id})
    pedido = pedidos.obtener(pedidos.PEDIDO_DEMO_ID)
    if pedido is None or pedido.estado != "nuevo":
        raise AgenteError(
            409,
            "Este pedido ya se cotizó. Para empezar otra compra, reseteá la demo.",
            {"estado_pedido": pedido.estado if pedido else None},
        )
    ahora = _ahora()
    corrida = CorridaAgente(
        id=f"ag_{uuid.uuid4().hex[:6]}",
        pedido_id=pedido.id,
        texto=(nueva.texto or "").strip() or None,
        horizonte_meses=nueva.horizonte_meses or inventario.horizonte_por_defecto(),
        opciones=OpcionesCorrida.model_validate(nueva.model_dump(exclude={"texto"})),
        estado="en_curso",
        pasos=[PasoAgente(id=i, titulo=t) for i, t in PASOS],
        creada_en=ahora,
        actualizada_en=ahora,
    )
    _guardar(corrida)
    _lanzar(corrida.id)
    log.info("Corrida %s: %r", corrida.id, corrida.texto)
    return corrida


def confirmar(corrida_id: str, confirmacion: Confirmacion | None) -> CorridaAgente:
    corrida = obtener(corrida_id)
    if corrida.estado != "esperando_confirmacion":
        raise AgenteError(409, "La compra no está esperando tu confirmación", {"estado": corrida.estado})
    if confirmacion and confirmacion.lineas is not None:
        nuevas = {l.producto_id: l.cantidad for l in confirmacion.lineas}
        ajenas = set(nuevas) - {l.producto_id for l in corrida.propuesta}
        if ajenas:
            raise AgenteError(422, "Hay productos que no están en la propuesta", {"producto_ids": sorted(ajenas)})
        for linea in corrida.propuesta:
            cantidad = nuevas.get(linea.producto_id, 0)
            if cantidad > 0 and cantidad != linea.cantidad:
                linea.evidencia += f" Lo cambiaste de {fmt(linea.cantidad)} a {fmt(cantidad)}."
                linea.dudas = [d for d in linea.dudas if not d.startswith("Falta la cantidad")]
            linea.cantidad = cantidad
    for linea in corrida.propuesta:
        if linea.cantidad <= 0:
            corrida.avisos.append(f"Saqué {linea.nombre_corto}: quedó sin cantidad.")
    corrida.propuesta = [l for l in corrida.propuesta if l.cantidad > 0]
    corrida.estado = "en_curso"
    _marcar(corrida, "confirmar", "hecho", f"Confirmaste {_enumerar([_cantidad(l.cantidad, l.nombre_corto, l.unidad) for l in corrida.propuesta]) or 'nada'}.")
    _guardar(corrida)
    _lanzar(corrida.id)
    return corrida


def aprobar_orden(corrida_id: str, orden_id: str) -> CorridaAgente:
    return _resolver_orden(corrida_id, orden_id, "enviada_simulada")


def rechazar_orden(corrida_id: str, orden_id: str) -> CorridaAgente:
    return _resolver_orden(corrida_id, orden_id, "rechazada")


def cancelar(corrida_id: str) -> CorridaAgente:
    corrida = obtener(corrida_id)
    if corrida.estado in TERMINADAS:
        raise AgenteError(409, f"La compra ya terminó ({corrida.estado})")
    corrida.estado = "cancelada"
    for paso in corrida.pasos:
        if paso.estado in ("pendiente", "en_curso", "esperando"):
            _marcar(corrida, paso.id, "omitido", "Cancelaste la compra.")
    for orden in corrida.ordenes:
        if orden.estado == "esperando_aprobacion":
            orden.estado = "rechazada"
    _guardar(corrida)
    if (tarea := _tareas.pop(corrida_id, None)) is not None:
        tarea.cancel()
    return corrida


def cancelar_todo() -> None:
    for tarea in _tareas.values():
        tarea.cancel()
    _tareas.clear()


# ---------------------------------------------------------------- tarea
def _lanzar(corrida_id: str) -> None:
    tarea = _tareas.get(corrida_id)
    if tarea is None or tarea.done():
        _tareas[corrida_id] = asyncio.create_task(_correr(corrida_id))


async def _correr(corrida_id: str) -> None:
    try:
        await _entender(corrida_id)
        _revisar_inventario(corrida_id)
        await _esperar_confirmacion(corrida_id)
        await _cotizar(corrida_id)
        await _esperar_revision(corrida_id)
        await _optimizar(corrida_id)
        await _negociar(corrida_id)
        _emitir_ordenes(corrida_id)
    except _Detenida:
        log.info("Corrida %s detenida", corrida_id)
    except asyncio.CancelledError:
        raise
    except _NadaQueComprar as exc:
        corrida = _cargar(corrida_id)
        if corrida is None or corrida.estado == "cancelada":
            return
        for paso in corrida.pasos:
            if paso.estado == "pendiente":
                _marcar(corrida, paso.id, "omitido")
        corrida.estado, corrida.resumen = "completada", str(exc)
        _guardar(corrida)
    except _Fallo as exc:
        _fallar(corrida_id, exc.paso, str(exc))
    except Exception as exc:  # noqa: BLE001 — la corrida queda en error con el motivo, la UI lo muestra
        log.exception("Falló la corrida %s", corrida_id)
        _fallar(corrida_id, None, f"Error inesperado: {exc}")


def _fallar(corrida_id: str, paso_id: str | None, mensaje: str) -> None:
    corrida = _cargar(corrida_id)
    if corrida is None or corrida.estado == "cancelada":
        return
    if paso_id is None:
        paso_id = next((p.id for p in corrida.pasos if p.estado in ("en_curso", "esperando")), None)
    if paso_id is not None:
        _marcar(corrida, paso_id, "error", mensaje)
    corrida.estado, corrida.error = "error", mensaje
    _guardar(corrida)


# ---------------------------------------------------------------- 1. entender
async def _entender(corrida_id: str) -> None:
    corrida = _vigente(corrida_id)
    if _paso(corrida, "entender").estado in ("hecho", "omitido"):
        return
    if not corrida.texto:
        _marcar(corrida, "entender", "omitido", "No pediste nada puntual: reviso el inventario.")
        _guardar(corrida)
        return
    _marcar(corrida, "entender", "en_curso", "Entendiendo lo que pediste…")
    _guardar(corrida)
    pedido = pedidos.obtener(corrida.pedido_id)
    try:
        leido = await interpretacion.interpretar(
            corrida.texto, catalogo=pipeline.catalogo(), fecha=inventario.fecha_hoy(), negocio=pedido.negocio
        )
    except Exception as exc:  # noqa: BLE001 — sin LLM, LLM caído, JSON inválido: se muestra el motivo
        raise _Fallo("entender", f"No pude entender el pedido: {exc}") from exc
    corrida = _vigente(corrida_id)
    corrida.interpretacion = leido
    _marcar(corrida, "entender", "hecho", _texto_entendido(leido))
    _guardar(corrida)


def _texto_entendido(leido: Interpretacion) -> str:
    cortos = {p.producto_id: (p.nombre_corto, p.unidad) for p in inventario.inventario().productos}
    partes = []
    for item in leido.items:
        corto, unidad = cortos[item.producto_id]
        que = _cantidad(item.cantidad, corto, unidad) if item.cantidad else f"{corto} (sin cantidad)"
        partes.append(que + (f" para el {item.necesario_para:%d/%m}" if item.necesario_para else ""))
    texto = f"Pediste {_enumerar(partes)}." if partes else "No pediste productos puntuales: reviso el inventario."
    if leido.excluir:
        texto += f" Que no compre {_enumerar([cortos[p][0] for p in leido.excluir])}."
    if leido.horizonte_meses:
        texto += f" Reposición para {leido.horizonte_meses} {'mes' if leido.horizonte_meses == 1 else 'meses'}."
    if leido.no_entendido:
        texto += f" No tengo en el catálogo: {_enumerar(leido.no_entendido)}."
    return texto


# ---------------------------------------------------------------- 2. inventario
def _revisar_inventario(corrida_id: str) -> None:
    corrida = _vigente(corrida_id)
    if _paso(corrida, "inventario").estado == "hecho":
        return
    leido = corrida.interpretacion
    horizonte = (
        corrida.opciones.horizonte_meses
        or (leido.horizonte_meses if leido else None)
        or inventario.horizonte_por_defecto()
    )
    inv = inventario.inventario(horizonte)
    items = {p.producto_id: p for p in inv.productos}
    lineas = [_linea_pedida(i, items[i.producto_id], inv.fecha, inv.plazo_minimo_dias) for i in (leido.items if leido else [])]
    avisos = list(leido.dudas) if leido else []
    excluir = set(leido.excluir) if leido else set()
    for item in inv.productos:
        repo = item.reposicion
        if any(l.producto_id == item.producto_id for l in lineas) or repo is None or repo.cantidad <= 0:
            continue
        if item.producto_id in excluir:
            avisos.append(f"Sacaste {item.nombre_corto}: no lo repongo, aunque el inventario pide {fmt(repo.cantidad)}.")
            continue
        lineas.append(
            _linea(item, cantidad=repo.cantidad, necesario_para=repo.necesario_para, origen="reposicion",
                   evidencia=f"{item.pronostico.evidencia} {repo.evidencia}")
        )
    avisos += [f"No tengo «{d}» en el catálogo: no lo cotizo." for d in (leido.no_entendido if leido else [])]
    avisos += [f"No hay proveedores habilitados para {items[l.producto_id].nombre_corto}." for l in lineas if not items[l.producto_id].proveedores]
    corrida.horizonte_meses = horizonte
    corrida.propuesta = lineas
    corrida.avisos = avisos
    _marcar(corrida, "inventario", "hecho", _texto_inventario(lineas, inv.meses_pronostico))
    _guardar(corrida)


def _linea(item: ItemInventario, *, cantidad: float, necesario_para: date, origen: str, evidencia: str, dudas: list[str] | None = None) -> LineaPropuesta:
    return LineaPropuesta(
        producto_id=item.producto_id,
        nombre=item.nombre,
        nombre_corto=item.nombre_corto,
        unidad=item.unidad,
        cantidad=cantidad,
        necesario_para=necesario_para,
        origen=origen,  # type: ignore[arg-type]
        modo=item.modo,
        tope_automatico_uyu=item.tope_automatico_uyu,
        stock_actual=item.stock_actual,
        evidencia=evidencia,
        dudas=dudas or [],
    )


def _linea_pedida(pedido: ItemInterpretado, item: ItemInventario, hoy: date, plazo_minimo: int) -> LineaPropuesta:
    """Lo que pidió Lucía, validado contra el inventario: stock, cuenta de reposición y plazo."""
    dudas: list[str] = []
    evidencia = f"Lo pediste: «{pedido.evidencia}»."
    repo = item.reposicion
    cantidad = pedido.cantidad
    if cantidad is None and repo is not None and repo.cantidad > 0:
        cantidad = repo.cantidad
        evidencia += f" No dijiste cuántos: uso la cuenta del inventario. {repo.evidencia}"
    elif cantidad is None:
        cantidad = 0
        dudas.append(f"Falta la cantidad de {item.nombre_corto}.")
    elif repo is not None and repo.cantidad != cantidad:
        evidencia += f" El inventario sugería {fmt(repo.cantidad)}."
    evidencia += f" En depósito: {fmt(item.stock_actual)}."
    if item.tipo == "equipamiento" and item.stock_actual > 0:
        dudas.append(f"Hay {fmt(item.stock_actual)} {item.nombre_corto} en depósito: ¿comprás {fmt(cantidad)} igual?")
    lo_antes = hoy + timedelta(days=plazo_minimo)
    necesario = pedido.necesario_para or (repo.necesario_para if repo else None)
    if necesario is None:
        necesario = hoy + timedelta(days=DIAS_SIN_FECHA)
        dudas.append(f"No dijiste para cuándo las {item.nombre_corto}: puse el {necesario:%d/%m}.")
    elif necesario < lo_antes:
        dudas.append(f"Pediste {item.nombre_corto} para el {necesario:%d/%m}, pero lo antes posible es el {lo_antes:%d/%m}.")
        necesario = lo_antes
    return _linea(item, cantidad=cantidad, necesario_para=necesario, origen="pedido", evidencia=evidencia, dudas=dudas)


def _texto_inventario(lineas: list[LineaPropuesta], meses: list[str]) -> str:
    if not lineas:
        return "No hay nada para comprar: el stock alcanza y no pediste productos."
    nombres_meses = [inventario.MESES_LARGOS[int(m[-2:]) - 1] for m in meses]
    repos = [_cantidad(l.cantidad, l.nombre_corto, l.unidad) for l in lineas if l.origen == "reposicion"]
    pedidas = [l for l in lineas if l.origen == "pedido"]
    partes = []
    if repos:
        partes.append(
            f"Para cubrir {_enumerar(nombres_meses)} hay que reponer {_enumerar(repos)} "
            "(pronóstico con estacionalidad + stock mínimo − stock actual)."
        )
    else:
        partes.append("El stock de consumibles alcanza.")
    if pedidas:
        sin_stock = [l.nombre_corto for l in pedidas if l.stock_actual == 0]
        if sin_stock:
            partes.append(f"De {_enumerar(sin_stock)} no hay nada en depósito.")
    return " ".join(partes)


# ---------------------------------------------------------------- 3. confirmar
async def _esperar_confirmacion(corrida_id: str) -> None:
    corrida = _vigente(corrida_id)
    if _paso(corrida, "confirmar").estado in ("hecho", "omitido"):
        if not corrida.propuesta:
            raise _NadaQueComprar("No había nada para comprar.")
        return
    if not corrida.propuesta:
        raise _NadaQueComprar(_paso(corrida, "inventario").detalle or "No hay nada para comprar.")
    dudas = any(l.dudas or l.cantidad <= 0 for l in corrida.propuesta) or bool(
        corrida.interpretacion and corrida.interpretacion.dudas
    )
    if not corrida.opciones.esperar_confirmacion and not dudas:
        _marcar(corrida, "confirmar", "omitido", "Sin dudas: sigo sin esperar tu OK.")
        _guardar(corrida)
        return
    if corrida.estado != "esperando_confirmacion":
        corrida.estado = "esperando_confirmacion"
        _marcar(corrida, "confirmar", "esperando", "Revisá la propuesta y confirmá para pedir cotizaciones.")
        _guardar(corrida)
    while _paso(_vigente(corrida_id), "confirmar").estado != "hecho":
        await asyncio.sleep(INTERVALO_S)
    if not _vigente(corrida_id).propuesta:
        raise _NadaQueComprar("Sacaste todo: no hay nada para comprar.")


# ---------------------------------------------------------------- 4 y 5. cotizar e insistir
async def _cotizar(corrida_id: str) -> None:
    corrida = _vigente(corrida_id)
    if _paso(corrida, "cotizar").estado == "hecho":
        return
    nombres = _proveedores()
    if _paso(corrida, "cotizar").estado == "pendiente":
        pedido = pedidos.obtener(corrida.pedido_id)
        if pedido.estado == "nuevo":
            pedido.lineas = [
                LineaPedido(producto_id=l.producto_id, cantidad=l.cantidad, necesario_para=l.necesario_para)
                for l in corrida.propuesta
            ]
            store.guardar("pedidos", pedido)
        else:
            corrida.avisos.append("El pedido ya se estaba cotizando desde otra pantalla: sigo con ese.")
        _marcar(corrida, "cotizar", "en_curso", f"Pidiendo cotización a {len(nombres)} proveedores…")
        _guardar(corrida)
        await simulador.iniciar(corrida.pedido_id)
    umbral = max(SEGUNDOS_PARA_INSISTIR * _escala(), UMBRAL_MINIMO_S)
    maximo = max(ESPERA_MAXIMA_S * _escala(), ESPERA_MAXIMA_MINIMA_S)
    while True:
        corrida = _vigente(corrida_id)
        transcurrido = (_ahora() - _paso(corrida, "cotizar").inicio).total_seconds()
        esperando = [e for e in simulador.estado_proveedores(corrida.pedido_id) if e.estado == "esperando"]
        mensajes = store.listar("mensajes", MensajeCrudo, pedido_id=corrida.pedido_id)
        leyendo = [m for m in mensajes if m.estado in ("pendiente", "leyendo")]
        todas = store.listar("llamadas", Llamada, pedido_id=corrida.pedido_id)
        activas = [l for l in todas if l.estado in llamadas.ACTIVAS]
        _seguir_llamadas(corrida, todas, umbral)
        if not esperando and not leyendo and not activas:
            break
        vencido = transcurrido >= maximo and not activas and not leyendo
        colgado = transcurrido >= maximo + LLAMADA_MAXIMA_S  # p. ej. una llamada que cortó un reinicio
        if vencido or colgado:
            corrida.sin_respuesta = [e.proveedor_id for e in esperando]
            break
        respondieron = len(nombres) - len(esperando)
        faltan = f": falta {_enumerar([e.nombre for e in esperando])}" if esperando else ""
        _marcar(corrida, "cotizar", "en_curso", f"Respondieron {respondieron} de {len(nombres)}{faltan}.")
        _guardar(corrida)
        llamados = {l.proveedor_id for l in todas}
        a_llamar = [e for e in esperando if e.proveedor_id not in llamados]
        if corrida.opciones.llamar_si_no_responde and transcurrido >= umbral and a_llamar:
            await _llamar(corrida_id, a_llamar)
        await asyncio.sleep(INTERVALO_S)
    # sin await desde la última lectura: `corrida` está al día, con lo que marcó _seguir_llamadas
    errores = [m for m in mensajes if m.estado == "error"]
    corrida.avisos += [f"No pude leer la respuesta de {nombres[m.proveedor_id]}: {m.error}" for m in errores]
    if corrida.sin_respuesta:
        sin = _enumerar([nombres[p] for p in corrida.sin_respuesta])
        corrida.avisos.append(f"{sin} no respondió: armo el plan sin sus precios.")
        detalle = f"Respondieron {len(nombres) - len(corrida.sin_respuesta)} de {len(nombres)}: {sin} no contestó."
    else:
        detalle = f"Respondieron los {len(nombres)} proveedores."
    insistir = _paso(corrida, "insistir").estado
    if insistir == "pendiente":
        _marcar(corrida, "insistir", "omitido", "No hizo falta llamar a nadie." if not corrida.sin_respuesta else "Llamar está desactivado para esta compra.")
    elif insistir == "en_curso":
        _marcar(corrida, "insistir", "error", "La llamada no terminó: sigo sin esa cotización.")
    _marcar(corrida, "cotizar", "hecho", detalle)
    _guardar(corrida)


async def _llamar(corrida_id: str, a_llamar: list) -> None:
    """Llama (simulado salvo LLAMADAS_MODO=real) a los que no respondieron, una vez a cada uno."""
    pedido = pedidos.obtener(_vigente(corrida_id).pedido_id)
    for estado in a_llamar:
        nota = None
        try:
            llamada = await llamadas.iniciar(
                pedido_id=pedido.id,
                proveedor_id=estado.proveedor_id,
                tipo="cotizacion",
                variables=llamadas.instrucciones_cotizacion(pedido, estado.proveedor_id),
            )
        except llamadas.LlamadaNoPosible as exc:  # modo real sin config o sin teléfono: respaldo simulado
            nota = f"No pude llamar de verdad ({exc}): hice la llamada simulada."
            llamada = await llamadas.iniciar(
                pedido_id=pedido.id,
                proveedor_id=estado.proveedor_id,
                tipo="cotizacion",
                variables=llamadas.instrucciones_cotizacion(pedido, estado.proveedor_id),
                simulada=True,
            )
        corrida = _vigente(corrida_id)
        corrida.llamada_ids.append(llamada.id)
        if nota:
            corrida.avisos.append(nota)
        _guardar(corrida)
        log.info("Corrida %s: llamo a %s (%s)", corrida_id, estado.proveedor_id, llamada.id)


def _seguir_llamadas(corrida: CorridaAgente, todas: list[Llamada], umbral: float) -> None:
    mias = [l for l in todas if l.id in corrida.llamada_ids]
    if not mias:
        return
    nombres = _proveedores()
    activas = [l for l in mias if l.estado in llamadas.ACTIVAS]
    if activas:
        quienes = _enumerar([nombres[l.proveedor_id] for l in activas])
        modo = "simulada" if all(l.modo == "simulada" for l in activas) else "real"
        _marcar(corrida, "insistir", "en_curso", f"{quienes} no respondió en {fmt(umbral)} s: lo estoy llamando (llamada {modo}).")
        return
    partes = []
    for l in mias:
        if l.estado == "terminada" and l.mensaje_id:
            partes.append(f"{nombres[l.proveedor_id]} cotizó por teléfono")
        else:
            partes.append(f"{nombres[l.proveedor_id]}: {l.error or 'la llamada terminó sin cotización'}")
    _marcar(corrida, "insistir", "hecho", "; ".join(partes) + ".")


# ---------------------------------------------------------------- 6. revisar
async def _esperar_revision(corrida_id: str) -> None:
    corrida = _vigente(corrida_id)
    if _paso(corrida, "revisar").estado in ("hecho", "omitido"):
        return
    nombres = _proveedores()
    revisadas: list[str] = []
    while True:
        corrida = _vigente(corrida_id)
        dudosas = [c for c in _cotizaciones(corrida.pedido_id) if c.estado == "revisar"]
        if not dudosas:
            break
        revisadas = list(dict.fromkeys(revisadas + [nombres[c.proveedor_id] for c in dudosas]))
        pendientes = [_revision(c, nombres[c.proveedor_id]) for c in dudosas]
        if corrida.estado != "esperando_revision" or corrida.revision != pendientes:
            corrida.estado, corrida.revision = "esperando_revision", pendientes
            _marcar(corrida, "revisar", "esperando", " ".join(p.pregunta for p in pendientes))
            _guardar(corrida)
        await asyncio.sleep(INTERVALO_S)
    corrida.estado, corrida.revision = "en_curso", []
    if revisadas:
        _marcar(corrida, "revisar", "hecho", f"Confirmaste lo dudoso de {_enumerar(revisadas)}.")
    else:
        _marcar(corrida, "revisar", "omitido", "Todas las respuestas se leyeron sin dudas.")
    _guardar(corrida)


def _revision(cotizacion: Cotizacion, nombre: str) -> RevisionPendiente:
    pide_iva = "iva" in cotizacion.campos_dudosos
    pregunta = (
        f"{nombre} no aclaró si sus precios incluyen IVA: ¿los incluyen?"
        if pide_iva
        else f"La lectura de {nombre} tiene dudas ({', '.join(cotizacion.campos_dudosos) or 'confianza baja'}): ¿está bien así?"
    )
    return RevisionPendiente(
        cotizacion_id=cotizacion.id,
        proveedor_id=cotizacion.proveedor_id,
        proveedor_nombre=nombre,
        campos_dudosos=cotizacion.campos_dudosos,
        pide_iva=pide_iva,
        pregunta=pregunta,
    )


# ---------------------------------------------------------------- 7. optimizar
async def _optimizar(corrida_id: str) -> None:
    from app import main as api  # import local: main importa las rutas del agente

    corrida = _vigente(corrida_id)
    if _paso(corrida, "optimizar").estado == "hecho":
        return
    _marcar(corrida, "optimizar", "en_curso", "Buscando la combinación más barata que cumple plazos y mínimos…")
    _guardar(corrida)
    guardado = store.obtener_dict("planes", corrida.pedido_id)
    if guardado is not None:  # alguien optimizó desde la pantalla del plan
        plan = Plan.model_validate(guardado)
    else:
        try:
            plan = await api.optimizar(corrida.pedido_id, forzar=bool(corrida.sin_respuesta))
        except HTTPException as exc:
            raise _Fallo("optimizar", f"No pude armar el plan: {_mensaje_http(exc)}") from exc
    corrida = _vigente(corrida_id)
    corrida.avisos += [r for r in plan.relajaciones if r not in corrida.avisos]
    _marcar(corrida, "optimizar", "hecho", _texto_plan(plan, pedidos.obtener(corrida.pedido_id).proveedor_habitual_id))
    _guardar(corrida)


def _texto_plan(plan: Plan, habitual_id: str) -> str:
    nombres = _proveedores()
    usados = _enumerar([nombres[p] for p in plan.proveedores_usados])
    texto = f"Plan: $ {fmt(plan.costo_total)} + IVA, comprando a {usados}."
    if plan.ahorro > 0:
        texto += (
            f" Ahorro: $ {fmt(plan.ahorro)} ({fmt(plan.ahorro_pct, 1)} %) contra comprarle todo a "
            f"{nombres.get(habitual_id, habitual_id)}."
        )
    return texto


# ---------------------------------------------------------------- 8. negociar
async def _negociar(corrida_id: str) -> None:
    from app import main as api

    corrida = _vigente(corrida_id)
    if _paso(corrida, "negociar").estado in ("hecho", "omitido", "error"):
        return
    plan = Plan.model_validate(store.obtener_dict("planes", corrida.pedido_id))
    proveedor_id = plan.oportunidad_negociacion
    if not proveedor_id or not corrida.opciones.negociar:
        detalle = "No hay margen para negociar en este plan." if not proveedor_id else "Negociar está desactivado para esta compra."
        _marcar(corrida, "negociar", "omitido", detalle)
        _guardar(corrida)
        return
    nombre = _proveedores()[proveedor_id]
    previas = store.listar("negociaciones", Negociacion, pedido_id=corrida.pedido_id, proveedor_id=proveedor_id)
    if previas:
        negociacion = previas[-1]
    else:
        brecha = f" (le paga $ {fmt(plan.brecha_oportunidad)} más que al más barato)" if plan.brecha_oportunidad else ""
        _marcar(corrida, "negociar", "en_curso", f"Ensayo 3 estrategias con el gemelo de {nombre}{brecha}…")
        _guardar(corrida)
        try:
            negociacion = await api.negociar(corrida.pedido_id, proveedor_id)
        except HTTPException as exc:
            corrida = _vigente(corrida_id)
            _marcar(corrida, "negociar", "error", f"No pude ensayar la negociación con {nombre}: {_mensaje_http(exc)}")
            _guardar(corrida)
            return
    corrida = _vigente(corrida_id)
    corrida.negociacion_id = negociacion.id
    elegida = next((e for e in negociacion.estrategias if e.nombre == negociacion.elegida), None)
    detalle = f"Con el gemelo de {nombre} conviene «{negociacion.elegida}»"
    if elegida is not None:
        detalle += f": −{fmt(elegida.concesion_obtenida_pct, 1)} %, unos $ {fmt(elegida.ganancia_esperada_uyu)}"
    _marcar(corrida, "negociar", "hecho", detalle + ". El mensaje está listo para que lo apruebes.")
    _guardar(corrida)


# ---------------------------------------------------------------- 9. órdenes
def _emitir_ordenes(corrida_id: str) -> None:
    corrida = _vigente(corrida_id)
    if _paso(corrida, "ordenes").estado in ("hecho", "esperando"):
        return
    plan = Plan.model_validate(store.obtener_dict("planes", corrida.pedido_id))
    corrida.ordenes = armar_ordenes(corrida, plan)
    pendientes = [o for o in corrida.ordenes if o.estado == "esperando_aprobacion"]
    if pendientes:
        corrida.estado = "esperando_aprobacion"
        _marcar(corrida, "ordenes", "esperando", _texto_ordenes(corrida.ordenes))
    else:
        _marcar(corrida, "ordenes", "hecho", _texto_ordenes(corrida.ordenes))
        _completar(corrida)
    _guardar(corrida)


def _aprobacion(item: ItemInventario, subtotal: Decimal) -> tuple[str, str]:
    if item.modo == "manual":
        return "manual", "Está en modo manual, la aprobás vos."
    tope = item.tope_automatico_uyu
    if tope is not None and subtotal > tope:
        return "supera_tope", f"$ {fmt(subtotal)} supera el tope automático de $ {fmt(tope)}."
    if tope is None:
        return "automatica", f"Modo automático y sin tope: $ {fmt(subtotal)}."
    return "automatica", f"Modo automático y $ {fmt(subtotal)} no supera el tope de $ {fmt(tope)}."


def armar_ordenes(corrida: CorridaAgente, plan: Plan) -> list[OrdenCompra]:
    """Una orden por proveedor del plan. Va sola si ninguna línea necesita a Lucía."""
    iva = Decimal(str(pipeline.datos_pedido()["config"]["iva"]))
    nombres = _proveedores()
    items = {p.producto_id: p for p in inventario.inventario(corrida.horizonte_meses).productos}
    cotizaciones = _cotizaciones_usadas(corrida.pedido_id)
    por_producto: dict[str, Decimal] = {}
    for a in plan.asignaciones:
        por_producto[a.producto_id] = por_producto.get(a.producto_id, Decimal(0)) + a.subtotal
    negociado = None
    if corrida.negociacion_id:
        neg = store.obtener("negociaciones", corrida.negociacion_id, Negociacion)
        negociado = neg.proveedor_id if neg else None
    ordenes = []
    for n, proveedor_id in enumerate(dict.fromkeys(a.proveedor_id for a in plan.asignaciones)):
        cot = cotizaciones.get(proveedor_id)
        lineas = []
        for a in (a for a in plan.asignaciones if a.proveedor_id == proveedor_id):
            item = items[a.producto_id]
            aprobacion, motivo = _aprobacion(item, por_producto[a.producto_id])
            evidencia = next((i.evidencia for i in cot.items if i.producto_id == a.producto_id), None) if cot else None
            lineas.append(
                LineaOrden(
                    producto_id=a.producto_id,
                    nombre=item.nombre,
                    nombre_corto=item.nombre_corto,
                    unidad=item.unidad,
                    cantidad=a.cantidad,
                    precio_unitario_sin_iva=a.precio_unitario_sin_iva,
                    subtotal=a.subtotal,
                    aprobacion=aprobacion,  # type: ignore[arg-type]
                    motivo=motivo,
                    cotizacion_id=cot.id if cot else None,
                    evidencia=evidencia,
                )
            )
        envio = Decimal(str(cot.costo_envio)) if cot else Decimal(0)
        sin_iva = sum((l.subtotal for l in lineas), Decimal(0)) + envio
        requiere = any(l.aprobacion != "automatica" for l in lineas)
        orden = OrdenCompra(
            id=f"oc_{proveedor_id}",
            numero=f"OC-{1001 + n}",
            proveedor_id=proveedor_id,
            proveedor_nombre=nombres[proveedor_id],
            lineas=lineas,
            envio=envio,
            total_sin_iva=sin_iva,
            total_con_iva=(sin_iva * (1 + iva)).quantize(Decimal("0.01")),
            requiere_aprobacion=requiere,
            motivos=[
                f"{l.nombre_corto.capitalize()}: {l.motivo[0].lower()}{l.motivo[1:]}"
                for l in lineas
                if l.aprobacion != "automatica"
            ],
            estado="esperando_aprobacion" if requiere else "enviada_simulada",
            aprobada_por=None if requiere else "agente",
            negociacion_id=corrida.negociacion_id if proveedor_id == negociado else None,
            mensaje="",
            enviada_en=None if requiere else _ahora(),
        )
        orden.mensaje = _mensaje_orden(orden, corrida)
        ordenes.append(orden)
    return ordenes


def _mensaje_orden(orden: OrdenCompra, corrida: CorridaAgente) -> str:
    pedido = pedidos.obtener(corrida.pedido_id)
    fechas = {l.producto_id: l.necesario_para for l in corrida.propuesta}
    renglones = [
        f"- {_cantidad(l.cantidad, l.nombre, l.unidad)} a $ {fmt(l.precio_unitario_sin_iva, 2)} + IVA "
        + ("el litro" if l.unidad == "l" else "c/u")
        for l in orden.lineas
    ]
    entrega = min((fechas[l.producto_id] for l in orden.lineas if l.producto_id in fechas), default=None)
    total = f"Total: $ {fmt(orden.total_sin_iva)} + IVA" + (f", con $ {fmt(orden.envio)} de envío" if orden.envio else "") + "."
    firma = (pedido.comprador or "Compras").split(" (")[0]
    return "\n".join(
        [f"Hola, ¿cómo va? Te confirmo la orden de compra {orden.numero} de {pedido.negocio}:", *renglones, total]
        + ([f"Entrega: para el {entrega:%d/%m}."] if entrega else [])
        + [f"Gracias, {firma}."]
    )


def _texto_ordenes(ordenes: list[OrdenCompra]) -> str:
    solas = [o for o in ordenes if o.aprobada_por == "agente"]
    pendientes = [o for o in ordenes if o.estado == "esperando_aprobacion"]
    partes = []
    if solas:
        partes.append(
            "Mandé solo "
            + _enumerar([f"la orden a {o.proveedor_nombre} ($ {fmt(o.total_sin_iva)} + IVA)" for o in solas])
            + "."
        )
    if pendientes:
        razones = []
        for o in pendientes:
            cortas = [
                f"{l.nombre_corto} en modo manual" if l.aprobacion == "manual" else f"{l.nombre_corto} supera el tope"
                for l in o.lineas
                if l.aprobacion != "automatica"
            ]
            razones.append(f"{o.proveedor_nombre} ({'; '.join(cortas)})")
        partes.append(f"Esperan tu OK: {_enumerar(razones)}.")
    resueltas = [o for o in ordenes if o.aprobada_por == "lucia" or o.estado == "rechazada"]
    if resueltas and not pendientes:
        aprobadas = [o.proveedor_nombre for o in resueltas if o.estado == "enviada_simulada"]
        rechazadas = [o.proveedor_nombre for o in resueltas if o.estado == "rechazada"]
        if aprobadas:
            partes.append(f"Aprobaste {_enumerar(aprobadas)}.")
        if rechazadas:
            partes.append(f"Rechazaste {_enumerar(rechazadas)}.")
    return " ".join(partes) or "No hay órdenes."


def _las_de(ordenes: list[OrdenCompra]) -> str:
    return ("la de " if len(ordenes) == 1 else "las de ") + _enumerar([o.proveedor_nombre for o in ordenes])


def _resolver_orden(corrida_id: str, orden_id: str, estado: str) -> CorridaAgente:
    corrida = obtener(corrida_id)
    orden = next((o for o in corrida.ordenes if o.id == orden_id), None)
    if orden is None:
        raise AgenteError(404, f"No existe la orden '{orden_id}' en esta compra")
    if orden.estado != "esperando_aprobacion":
        raise AgenteError(409, f"La orden {orden.numero} ya no espera aprobación ({orden.estado})")
    orden.estado = estado  # type: ignore[assignment]
    if estado == "enviada_simulada":
        orden.aprobada_por, orden.enviada_en = "lucia", _ahora()
    if not any(o.estado == "esperando_aprobacion" for o in corrida.ordenes):
        _marcar(corrida, "ordenes", "hecho", _texto_ordenes(corrida.ordenes))
        _completar(corrida)
    _guardar(corrida)
    log.info("Corrida %s: orden %s → %s", corrida_id, orden.numero, estado)
    return corrida


def _completar(corrida: CorridaAgente) -> None:
    corrida.estado = "completada"
    enviadas = [o for o in corrida.ordenes if o.estado == "enviada_simulada"]
    rechazadas = [o for o in corrida.ordenes if o.estado == "rechazada"]
    if not enviadas:
        corrida.resumen = "No se mandó ninguna orden."
        return
    total = sum((o.total_sin_iva for o in enviadas), Decimal(0))
    partes = [f"Compra cerrada: {len(enviadas)} {'orden' if len(enviadas) == 1 else 'órdenes'} por $ {fmt(total)} + IVA."]
    solas = [o for o in enviadas if o.aprobada_por == "agente"]
    tuyas = [o for o in enviadas if o.aprobada_por == "lucia"]
    if solas:
        partes.append(f"El agente mandó solo {_las_de(solas)}.")
    if tuyas:
        partes.append(f"Vos aprobaste {_las_de(tuyas)}.")
    if rechazadas:
        partes.append(f"Rechazaste {_las_de(rechazadas)}.")
    plan = store.obtener_dict("planes", corrida.pedido_id)
    if plan and not rechazadas and Decimal(str(plan["ahorro"])) > 0:
        habitual = pedidos.obtener(corrida.pedido_id).proveedor_habitual_id
        partes.append(
            f"Ahorro: $ {fmt(plan['ahorro'])} ({fmt(plan['ahorro_pct'], 1)} %) contra comprarle todo a "
            f"{_proveedores().get(habitual, habitual)}."
        )
    neg = store.obtener("negociaciones", corrida.negociacion_id, Negociacion) if corrida.negociacion_id else None
    if neg is not None and neg.estado == "simulada":
        partes.append(f"Queda la negociación con {_proveedores()[neg.proveedor_id]}: el mensaje está listo para aprobar.")
    corrida.resumen = " ".join(partes)
    pedidos.cambiar_estado(corrida.pedido_id, "aprobado")
