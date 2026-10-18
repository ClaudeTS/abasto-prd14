"""Pedidos para el listado y el detalle (PRD 1.4: RF-05, RF-10, RF-12, §6.2, §11.3).

Dos fuentes, con la misma forma (`DetallePedido`):

- **Vivos:** los pedidos del store (hoy, el de la demo: `pedido_demo_oct_2026`) con lo que hicieron el
  agente (corrida, órdenes, llamadas), el simulador (mensajes y cotizaciones), el solver (plan) y el
  gemelo (negociación). Se arman al leer: no se guarda nada nuevo, salvo las marcas de recibido y
  cerrado.
- **De ejemplo:** `data/pedidos_historicos.json` (`ejemplo: true`), para que el listado tenga historia.

El estado del PRD (§6.2) se calcula a partir del estado interno del pedido (`Pedido.estado`, que no se
toca) y de la corrida del agente. Recibido y cerrado los marca una persona: se guardan en la colección
propia `estados_pedido` (`{pedido_id: {"eventos": [{estado, en, detalle}]}}`).

Conversaciones (RF-10): cada mensaje con canal, sentido, participante, fecha y hora y texto o
transcripción. Los enviados que el backend no guarda como mensaje se reconstruyen: la solicitud de
cotización (el simulador le pide lo mismo a cada proveedor) y el mensaje de negociación aprobado. Lo que
escriba el Bloque 5 en la colección compartida `contactos` tiene prioridad sobre lo reconstruido.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app import pedidos, pipeline, store
from app.models import Cotizacion, Llamada, MensajeCrudo, Monto, Negociacion, Pedido, Plan
from app.normalizacion import fmt

log = logging.getLogger("abasto.pedidos")

ESTADOS = (
    "nuevo",
    "datos_incompletos",
    "cotizando",
    "cotizado",
    "negociando",
    "pendiente_aprobacion",
    "aprobado",
    "pendiente_entrega",
    "recibido",
    "cerrado",
    "cancelado",
)
EstadoPRD = Literal[
    "nuevo",
    "datos_incompletos",
    "cotizando",
    "cotizado",
    "negociando",
    "pendiente_aprobacion",
    "aprobado",
    "pendiente_entrega",
    "recibido",
    "cerrado",
    "cancelado",
]
RECIBIDOS = ("recibido", "cerrado")
FUERA_DE_TRAMITE = ("recibido", "cerrado", "cancelado")
ClienteInterno = Literal["ventas", "personal"]
Origen = Literal["solicitud_voz", "solicitud_email", "stock_minimo", "zafra", "demo"]
CanalMensaje = Literal["whatsapp", "email", "pdf", "foto", "audio", "llamada", "nota_voz"]
Proposito = Literal["solicitud", "cotizacion", "negociacion", "orden"]
ResultadoLlamada = Literal["atendida", "no_atendida", "buzon", "fallida", "en_curso"]

DIAS_AUDIO = 60  # RF-06: el audio se conserva 60 días; la transcripción, siempre
VIGENCIA_POR_DEFECTO = 30  # §11.1: si el proveedor no la indica
NUMEROS_VIVOS = {pedidos.PEDIDO_DEMO_ID: "PED-0142"}
CANAL_DEL_SIMULADOR: dict[str, CanalMensaje] = {
    "whatsapp_texto": "whatsapp",
    "whatsapp_audio": "audio",
    "pdf": "pdf",
    "foto": "foto",
    "llamada": "llamada",
}
_DOS = Decimal("0.01")


# ---------------------------------------------------------------- modelos de respuesta
class EventoEstado(BaseModel):
    estado: EstadoPRD
    en: datetime | None = None
    detalle: str | None = None


class LineaDetalle(BaseModel):
    producto_id: str
    nombre: str
    nombre_corto: str
    unidad: str
    cantidad: float
    necesario_para: date | None = None
    proveedor_id: str | None = None  # a quién se le compra, según el plan
    proveedor_nombre: str | None = None


class ItemCotizacionDetalle(BaseModel):
    producto_id: str
    nombre: str
    precio_original: Monto
    moneda_original: str
    incluye_iva_original: bool
    unidad_original: str
    precio_unitario_sin_iva: Monto  # costo comparable: sin IVA, en pesos, por unidad del producto
    conversion_aplicada: str | None = None
    cantidad_minima: float | None = None
    evidencia: str


class CotizacionDetalle(BaseModel):
    id: str
    proveedor_id: str
    proveedor_nombre: str
    canal: CanalMensaje | None
    recibida_en: datetime | None
    items: list[ItemCotizacionDetalle]
    costo_envio: Monto = Decimal(0)
    plazo_pago_dias: int = 0
    lead_time_dias: int | None = None
    validez_dias: int | None = None  # la que indicó el proveedor
    vigencia_dias: int  # la que vale: la indicada o 30
    vence_el: date | None = None
    estado: str = "valida"
    observaciones: list[str] = Field(default_factory=list)


class AsignacionDetalle(BaseModel):
    producto_id: str
    nombre: str
    proveedor_id: str
    proveedor_nombre: str
    cantidad: float
    precio_unitario_sin_iva: Monto
    subtotal: Monto


class PlanDetalle(BaseModel):
    costo_total: Monto  # sin IVA, con envíos
    costo_baseline: Monto | None = None  # todo al proveedor habitual, si cotizó todo
    ahorro: Monto | None = None
    ahorro_pct: float | None = None
    proveedores_usados: list[str]  # nombres
    explicacion: str | None = None
    asignaciones: list[AsignacionDetalle]


class LineaOrdenDetalle(BaseModel):
    producto_id: str
    nombre: str
    cantidad: float
    unidad: str
    precio_unitario_sin_iva: Monto
    subtotal: Monto
    aprobacion: str | None = None  # automatica | manual | supera_tope
    motivo: str | None = None
    evidencia: str | None = None


class OrdenDetalle(BaseModel):
    """Tabla orden_compra (§11.3). `corrida_id` + `id` sirven para aprobar o rechazar (docs/AGENTE.md)."""

    id: str
    numero: str
    proveedor_id: str
    proveedor_nombre: str
    estado: Literal["pendiente_aprobacion", "emitida", "pendiente_entrega", "recibida", "cancelada"]
    estado_agente: str | None = None  # esperando_aprobacion | enviada_simulada | rechazada
    requiere_aprobacion: bool
    motivos: list[str] = Field(default_factory=list)
    emitida_por: Literal["agente", "usuario"] | None = None
    aprobada_por: str | None = None  # agente | lucia
    emitida_en: datetime | None = None
    recibida_en: datetime | None = None
    envio: Monto = Decimal(0)
    total_sin_iva: Monto
    total_con_iva: Monto
    lineas: list[LineaOrdenDetalle]
    negociacion_id: str | None = None
    negociada: bool = False
    corrida_id: str | None = None
    mensaje: str | None = None


class EstrategiaResumen(BaseModel):
    nombre: str
    descripcion: str
    concesion_obtenida_pct: float
    ganancia_esperada_uyu: Monto | None = None
    riesgo: str


class NegociacionDetalle(BaseModel):
    id: str
    proveedor_id: str
    proveedor_nombre: str
    estado: str  # simulada | aprobada | enviada_simulada
    elegida: str
    mensaje_propuesto: str
    estrategias: list[EstrategiaResumen]
    llamada_id: str | None = None
    resultado: str | None = None


class TurnoTranscripcion(BaseModel):
    rol: Literal["abasto", "proveedor", "cliente_interno"]
    quien: str
    texto: str
    segundo: int | None = None


class InfoLlamada(BaseModel):
    """Tabla llamada (§11.3). El audio se borra a los 60 días; la transcripción se conserva."""

    tipo: str | None = None  # cotizacion | negociacion
    intento: int | None = None
    resultado: ResultadoLlamada
    duracion_segundos: int | None = None
    modo: str | None = None  # real | simulada (None en los de ejemplo)
    audio_disponible_hasta: datetime | None = None
    resumen: str | None = None
    acuerdo: bool | None = None
    precio_acordado: Monto | None = None
    telefono: str | None = None


class Mensaje(BaseModel):
    """Tabla mensaje (§11.3): base del informe PDF."""

    id: str
    conversacion_id: str
    canal: CanalMensaje
    sentido: Literal["recibido", "enviado"]
    de: str
    para: str
    participante: str  # la contraparte: proveedor o cliente interno
    fecha: datetime | None
    texto: str | None = None
    transcripcion: list[TurnoTranscripcion] | None = None
    duracion_segundos: int | None = None  # notas de voz y audios
    archivo_url: str | None = None
    llamada: InfoLlamada | None = None
    etiqueta: str | None = None  # "Cotización leída", "OC-1003", …
    motivo: str | None = None  # solicitud_cotizacion | reintento | aviso_no_atendio | negociacion | orden | …
    nota: str | None = None  # aclaraciones honestas: "reconstruido a partir del pedido"


class Conversacion(BaseModel):
    """Tabla conversacion (§11.3)."""

    id: str
    contraparte: str
    contraparte_tipo: Literal["proveedor", "cliente_interno"]
    proveedor_id: str | None = None
    proposito: Proposito
    canales: list[CanalMensaje]
    inicio: datetime | None
    mensajes: list[Mensaje]


class ProductoResumen(BaseModel):
    producto_id: str
    nombre: str
    nombre_corto: str
    cantidad: float
    unidad: str


class DetallePedido(BaseModel):
    id: str
    numero: str
    titulo: str
    descripcion: str | None = None
    ejemplo: bool  # datos de ejemplo (data/pedidos_historicos.json)
    demo: bool  # el pedido de la demo guiada
    negocio: str
    cliente_interno: ClienteInterno
    origen: Origen
    solicitante: str | None = None
    creado_en: datetime
    actualizado_en: datetime
    necesario_desde: date | None = None
    necesario_hasta: date | None = None
    estado: EstadoPRD
    historial_estados: list[EventoEstado]
    motivo_cancelacion: str | None = None
    acciones: list[Literal["recibir", "cerrar"]] = Field(default_factory=list)
    lineas: list[LineaDetalle]
    cotizaciones: list[CotizacionDetalle] = Field(default_factory=list)
    plan: PlanDetalle | None = None
    ordenes: list[OrdenDetalle] = Field(default_factory=list)
    negociaciones: list[NegociacionDetalle] = Field(default_factory=list)
    conversaciones: list[Conversacion] = Field(default_factory=list)
    corrida_id: str | None = None
    avisos: list[str] = Field(default_factory=list)


class ResumenPedido(BaseModel):
    id: str
    numero: str
    titulo: str
    productos: list[ProductoResumen]
    cliente_interno: ClienteInterno
    origen: Origen
    proveedores: list[str]  # nombres: los de las órdenes, si no los del plan, si no los contactados
    ordenes: list[str]  # números de orden de compra
    estado: EstadoPRD
    creado_en: datetime
    actualizado_en: datetime
    ejemplo: bool
    demo: bool


class PedidoNoEncontrado(KeyError):
    pass


class TransicionInvalida(ValueError):
    pass


# ---------------------------------------------------------------- datos de referencia
def _productos() -> dict[str, dict[str, str]]:
    cortos = {p["producto_id"]: p["nombre_corto"] for p in store.semilla("inventario_demo")["productos"]}
    return {
        p.id: {"nombre": p.nombre, "corto": cortos.get(p.id, p.nombre.lower()), "unidad": p.unidad_canonica}
        for p in pipeline.catalogo()
    }


def _producto(producto_id: str) -> dict[str, str]:
    return _productos().get(producto_id, {"nombre": producto_id, "corto": producto_id, "unidad": "unidad"})


def _nombre_proveedor(proveedor_id: str) -> str:
    prov = pipeline.proveedores().get(proveedor_id)
    return prov.nombre if prov else proveedor_id


def _iva() -> Decimal:
    return Decimal(str(pipeline.datos_pedido()["config"]["iva"]))


def _negocio() -> str:
    return pipeline.datos_pedido()["pedido"]["negocio"]


def _dec(valor: Any) -> Decimal:
    return Decimal(str(valor))


def _cantidad(cantidad: float, producto_id: str) -> str:
    p = _producto(producto_id)
    return f"{fmt(cantidad)} L de {p['corto']}" if p["unidad"] == "l" else f"{fmt(cantidad)} {p['corto']}"


def _firma(solicitante: str | None) -> str:
    return (solicitante or "Compras").split(" (")[0]


def canal_de_solicitud(proveedor_id: str) -> CanalMensaje:
    """Por dónde se le pide cotización: email al que cotiza en PDF formal, WhatsApp al resto."""
    prov = pipeline.proveedores().get(proveedor_id)
    return "email" if prov is not None and prov.canal_preferido == "pdf" else "whatsapp"


def texto_solicitud(lineas: list[dict[str, Any]], negocio: str, firma: str) -> str:
    """La solicitud de cotización, armada con las líneas del pedido."""
    renglones = []
    for l in lineas:
        p = _producto(l["producto_id"])
        cuanto = f"{fmt(l['cantidad'])} L de" if p["unidad"] == "l" else f"{fmt(l['cantidad'])} ×"
        fecha = l.get("necesario_para")
        cuando = f", para el {fecha:%d/%m}" if isinstance(fecha, date) else ""
        renglones.append(f"- {cuanto} {p['nombre']}{cuando}")
    return "\n".join(
        [f"Hola, ¿cómo va? Les escribe el asistente de compras con IA de {negocio} para pedirles cotización de:"]
        + renglones
        + [
            "Por favor indiquen precio unitario, si incluye IVA, plazo de entrega, forma de pago y costo de envío.",
            f"Gracias, {firma}.",
        ]
    )


def _texto_orden(orden: OrdenDetalle, negocio: str, firma: str, entrega: date | None) -> str:
    renglones = [
        f"- {_cantidad(l.cantidad, l.producto_id)} a $ {fmt(l.precio_unitario_sin_iva, 2)} + IVA "
        + ("el litro" if l.unidad == "l" else "c/u")
        for l in orden.lineas
    ]
    total = f"Total: $ {fmt(orden.total_sin_iva)} + IVA" + (
        f", con $ {fmt(orden.envio)} de envío" if orden.envio else ""
    )
    return "\n".join(
        [f"Hola, ¿cómo va? Te confirmo la orden de compra {orden.numero} de {negocio}:", *renglones, total + "."]
        + ([f"Entrega: para el {entrega:%d/%m}."] if entrega else [])
        + [f"Gracias, {firma}."]
    )


def _audio_hasta(inicio: datetime | None, duracion: int | None, resultado: str) -> datetime | None:
    if inicio is None or resultado != "atendida":
        return None
    return inicio + timedelta(seconds=duracion or 0) + timedelta(days=DIAS_AUDIO)


def _orden_fecha(fecha: datetime | None) -> tuple[bool, datetime]:
    return (fecha is None, fecha or datetime.max)


def _agrupar(
    pedido_id: str, crudos: list[tuple[str, str, str, str | None, Proposito, Mensaje]]
) -> list[Conversacion]:
    """(clave contraparte, nombre, tipo, proveedor_id, propósito, mensaje) → conversaciones ordenadas."""
    grupos: dict[tuple[str, str], Conversacion] = {}
    for clave, nombre, tipo, proveedor_id, proposito, mensaje in crudos:
        conv_id = f"{pedido_id}:{clave}:{proposito}"
        conv = grupos.get((clave, proposito))
        if conv is None:
            conv = grupos[(clave, proposito)] = Conversacion(
                id=conv_id,
                contraparte=nombre,
                contraparte_tipo=tipo,  # type: ignore[arg-type]
                proveedor_id=proveedor_id,
                proposito=proposito,
                canales=[],
                inicio=None,
                mensajes=[],
            )
        mensaje.conversacion_id = conv_id
        conv.mensajes.append(mensaje)
    salida = []
    for conv in grupos.values():
        conv.mensajes.sort(key=lambda m: _orden_fecha(m.fecha))
        conv.canales = list(dict.fromkeys(m.canal for m in conv.mensajes))
        conv.inicio = next((m.fecha for m in conv.mensajes if m.fecha), None)
        for n, m in enumerate(conv.mensajes, 1):
            m.id = f"{conv.id}:{n}"
        salida.append(conv)
    return sorted(salida, key=lambda c: _orden_fecha(c.inicio))


# ---------------------------------------------------------------- marcas de recibido y cerrado
def _marcas(pedido_id: str) -> list[EventoEstado]:
    registro = store.obtener_dict("estados_pedido", pedido_id) or {}
    return [EventoEstado.model_validate(e) for e in registro.get("eventos", [])]


def marcar(pedido_id: str, estado: Literal["recibido", "cerrado"]) -> DetallePedido:
    """Recibido (desde pendiente de entrega) y cerrado (desde recibido), según §6.2."""
    actual = detalle(pedido_id)
    desde = {"recibido": "pendiente_entrega", "cerrado": "recibido"}[estado]
    if actual.estado != desde:
        raise TransicionInvalida(
            f"El pedido {actual.numero} está «{etiqueta_estado(actual.estado)}»: solo se puede marcar "
            f"«{etiqueta_estado(estado)}» desde «{etiqueta_estado(desde)}»."
        )
    detalle_txt = (
        "Marcaste la mercadería como recibida." if estado == "recibido" else "Cerraste el pedido: queda para consulta."
    )
    registro = store.obtener_dict("estados_pedido", pedido_id) or {"pedido_id": pedido_id, "eventos": []}
    registro["eventos"].append(
        EventoEstado(estado=estado, en=datetime.now(), detalle=detalle_txt).model_dump(mode="json")
    )
    store.guardar_dict("estados_pedido", pedido_id, registro)
    return detalle(pedido_id)


def _aplicar_marcas(d: DetallePedido) -> DetallePedido:
    for evento in _marcas(d.id):
        d.historial_estados.append(evento)
        d.estado = evento.estado
        if evento.en and evento.en > d.actualizado_en:
            d.actualizado_en = evento.en
    if d.estado in RECIBIDOS:
        recibido = next((e.en for e in d.historial_estados if e.estado == "recibido"), None)
        for orden in d.ordenes:
            if orden.estado in ("pendiente_entrega", "emitida"):
                orden.estado, orden.recibida_en = "recibida", orden.recibida_en or recibido
    d.acciones = {"pendiente_entrega": ["recibir"], "recibido": ["cerrar"]}.get(d.estado, [])  # type: ignore[assignment]
    return d


ETIQUETAS = {
    "nuevo": "Nuevo",
    "datos_incompletos": "Datos incompletos",
    "cotizando": "Cotizando",
    "cotizado": "Cotizado",
    "negociando": "Negociando",
    "pendiente_aprobacion": "Pendiente de aprobación",
    "aprobado": "Aprobado",
    "pendiente_entrega": "Pendiente de entrega",
    "recibido": "Recibido",
    "cerrado": "Cerrado",
    "cancelado": "Cancelado",
}


def etiqueta_estado(estado: str) -> str:
    return ETIQUETAS.get(estado, estado)


# ---------------------------------------------------------------- pedidos de ejemplo
def _historicos() -> dict[str, Any]:
    try:
        return store.semilla("pedidos_historicos")
    except FileNotFoundError:
        log.warning("No está data/pedidos_historicos.json: el listado solo muestra los pedidos vivos")
        return {"pedidos": []}


def _precio_comparable(item: dict[str, Any], tc: Decimal) -> tuple[Decimal, str]:
    """Lo mismo que hace normalizacion.py con una cotización: moneda, IVA y unidad, en código."""
    precio = _dec(item["precio_original"])
    pasos = []
    if item["moneda_original"] == "USD":
        pasos.append(f"USD {fmt(precio, 2)} × {fmt(tc, 2)} = UYU {fmt(precio * tc, 2)}")
        precio = precio * tc
    if item["incluye_iva_original"]:
        sin = precio / (1 + _iva())
        pasos.append(f"con IVA: {fmt(precio, 2)} / {fmt(1 + _iva(), 2)} = {fmt(sin, 2)}")
        precio = sin
    factor = _dec(item.get("factor", 1))
    if factor != 1:
        pasos.append(f"{item['unidad_original']} → {fmt(factor)}: {fmt(precio, 2)} / {fmt(factor)} = {fmt(precio / factor, 2)}")
        precio = precio / factor
    return precio.quantize(_DOS, rounding=ROUND_HALF_UP), " · ".join(pasos)


def _detalle_ejemplo(raw: dict[str, Any], datos: dict[str, Any]) -> DetallePedido:
    tc = _dec(datos.get("tipo_cambio_usd", pipeline.datos_pedido()["config"]["tipo_cambio_usd"]))
    habitual = datos.get("proveedor_habitual_id")
    pid = raw["id"]
    negocio = _negocio()
    firma = "Lucía"
    lineas_raw = [
        {**l, "necesario_para": date.fromisoformat(l["necesario_para"]) if l.get("necesario_para") else None}
        for l in raw["lineas"]
    ]
    # cotizaciones
    cotizaciones: list[CotizacionDetalle] = []
    precios: dict[tuple[str, str], Decimal] = {}
    evidencias: dict[tuple[str, str], str] = {}
    for n, c in enumerate(raw.get("cotizaciones", []), 1):
        items = []
        for it in c["items"]:
            precio, conversion = _precio_comparable(it, tc)
            precios[(c["proveedor_id"], it["producto_id"])] = precio
            evidencias[(c["proveedor_id"], it["producto_id"])] = it["evidencia"]
            items.append(
                ItemCotizacionDetalle(
                    producto_id=it["producto_id"],
                    nombre=_producto(it["producto_id"])["nombre"],
                    precio_original=_dec(it["precio_original"]),
                    moneda_original=it["moneda_original"],
                    incluye_iva_original=it["incluye_iva_original"],
                    unidad_original=it["unidad_original"],
                    precio_unitario_sin_iva=precio,
                    conversion_aplicada=conversion or None,
                    cantidad_minima=it.get("cantidad_minima"),
                    evidencia=it["evidencia"],
                )
            )
        recibida = datetime.fromisoformat(c["recibida_en"]) if c.get("recibida_en") else None
        vigencia = c.get("validez_dias") or VIGENCIA_POR_DEFECTO
        cotizaciones.append(
            CotizacionDetalle(
                id=f"{pid}:cot:{n}",
                proveedor_id=c["proveedor_id"],
                proveedor_nombre=_nombre_proveedor(c["proveedor_id"]),
                canal=c.get("canal"),
                recibida_en=recibida,
                items=items,
                costo_envio=_dec(c.get("costo_envio", 0)),
                plazo_pago_dias=c.get("plazo_pago_dias", 0),
                lead_time_dias=c.get("lead_time_dias"),
                validez_dias=c.get("validez_dias"),
                vigencia_dias=vigencia,
                vence_el=(recibida.date() + timedelta(days=vigencia)) if recibida else None,
                estado=c.get("estado", "valida"),
            )
        )
    envios = {c.proveedor_id: c.costo_envio for c in cotizaciones}
    # plan
    plan = None
    if raw.get("plan"):
        asignaciones = []
        for a in raw["plan"]["asignaciones"]:
            precio = _dec(a["precio_unitario_sin_iva"]) if "precio_unitario_sin_iva" in a else precios[(a["proveedor_id"], a["producto_id"])]
            asignaciones.append(
                AsignacionDetalle(
                    producto_id=a["producto_id"],
                    nombre=_producto(a["producto_id"])["nombre"],
                    proveedor_id=a["proveedor_id"],
                    proveedor_nombre=_nombre_proveedor(a["proveedor_id"]),
                    cantidad=a["cantidad"],
                    precio_unitario_sin_iva=precio,
                    subtotal=(precio * _dec(a["cantidad"])).quantize(_DOS),
                )
            )
        usados = list(dict.fromkeys(a.proveedor_id for a in asignaciones))
        costo = sum((a.subtotal for a in asignaciones), Decimal(0)) + sum((envios.get(p, Decimal(0)) for p in usados), Decimal(0))
        baseline = None
        if habitual and all((habitual, a.producto_id) in precios for a in asignaciones):
            baseline = sum((precios[(habitual, a.producto_id)] * _dec(a.cantidad) for a in asignaciones), Decimal(0)) + envios.get(habitual, Decimal(0))
            baseline = baseline.quantize(_DOS)
        ahorro = (baseline - costo) if baseline is not None else None
        plan = PlanDetalle(
            costo_total=costo,
            costo_baseline=baseline,
            ahorro=ahorro,
            ahorro_pct=float((ahorro / baseline * 100).quantize(Decimal("0.1"))) if ahorro is not None and baseline else None,
            proveedores_usados=[_nombre_proveedor(p) for p in usados],
            explicacion=raw["plan"].get("explicacion"),
            asignaciones=asignaciones,
        )
    # órdenes
    ordenes: list[OrdenDetalle] = []
    entregas = {l["producto_id"]: l["necesario_para"] for l in lineas_raw}
    for o in raw.get("ordenes", []):
        lineas = []
        for l in o["lineas"]:
            precio = _dec(l["precio_unitario_sin_iva"]) if "precio_unitario_sin_iva" in l else precios[(o["proveedor_id"], l["producto_id"])]
            lineas.append(
                LineaOrdenDetalle(
                    producto_id=l["producto_id"],
                    nombre=_producto(l["producto_id"])["nombre"],
                    cantidad=l["cantidad"],
                    unidad=_producto(l["producto_id"])["unidad"],
                    precio_unitario_sin_iva=precio,
                    subtotal=(precio * _dec(l["cantidad"])).quantize(_DOS),
                    aprobacion=l.get("aprobacion"),
                    motivo=l.get("motivo"),
                    evidencia=evidencias.get((o["proveedor_id"], l["producto_id"])),
                )
            )
        envio = _dec(o.get("envio", 0))
        sin_iva = sum((l.subtotal for l in lineas), Decimal(0)) + envio
        ordenes.append(
            OrdenDetalle(
                id=f"{pid}:{o['numero']}",
                numero=o["numero"],
                proveedor_id=o["proveedor_id"],
                proveedor_nombre=_nombre_proveedor(o["proveedor_id"]),
                estado=o["estado"],
                requiere_aprobacion=o.get("requiere_aprobacion", False),
                motivos=o.get("motivos", []),
                emitida_por=o.get("emitida_por"),
                aprobada_por=o.get("aprobada_por"),
                emitida_en=datetime.fromisoformat(o["emitida_en"]) if o.get("emitida_en") else None,
                recibida_en=datetime.fromisoformat(o["recibida_en"]) if o.get("recibida_en") else None,
                envio=envio,
                total_sin_iva=sin_iva,
                total_con_iva=(sin_iva * (1 + _iva())).quantize(_DOS),
                lineas=lineas,
                negociada=bool(o.get("negociada")),
            )
        )
    for orden in ordenes:
        entrega = min((entregas[l.producto_id] for l in orden.lineas if entregas.get(l.producto_id)), default=None)
        orden.mensaje = _texto_orden(orden, negocio, firma, entrega)
    por_numero = {o.numero: o for o in ordenes}
    # negociaciones
    negociaciones = []
    for n, neg in enumerate(raw.get("negociaciones", []), 1):
        valor = sum(
            (precios.get((neg["proveedor_id"], l["producto_id"]), Decimal(0)) * _dec(l["cantidad"]) for l in lineas_raw),
            Decimal(0),
        )
        negociaciones.append(
            NegociacionDetalle(
                id=f"{pid}:neg:{n}",
                proveedor_id=neg["proveedor_id"],
                proveedor_nombre=_nombre_proveedor(neg["proveedor_id"]),
                estado=neg.get("estado", "enviada_simulada"),
                elegida=neg["elegida"],
                mensaje_propuesto=neg["mensaje_propuesto"],
                estrategias=[
                    EstrategiaResumen(
                        nombre=e["nombre"],
                        descripcion=e["descripcion"],
                        concesion_obtenida_pct=e["concesion_obtenida_pct"],
                        ganancia_esperada_uyu=(valor * _dec(e["concesion_obtenida_pct"]) / 100).quantize(Decimal(1)),
                        riesgo=e["riesgo"],
                    )
                    for e in neg.get("estrategias", [])
                ],
                resultado=neg.get("resultado"),
            )
        )
    # conversaciones
    solicitante = raw.get("solicitante")
    crudos = []
    for conv in raw.get("conversaciones", []):
        interno = conv["contraparte"] == "interno"
        nombre = _firma(solicitante) if interno else _nombre_proveedor(conv["contraparte"])
        participante = (solicitante or "Cliente interno") if interno else nombre
        clave = "interno" if interno else conv["contraparte"]
        intentos = 0
        for m in conv["mensajes"]:
            fecha = datetime.fromisoformat(m["fecha"]) if m.get("fecha") else None
            texto = m.get("texto")
            nota = None
            if texto is None and m.get("motivo") == "solicitud_cotizacion":
                texto = texto_solicitud(lineas_raw, negocio, firma)
            elif texto is None and m.get("motivo") == "orden" and m.get("orden") in por_numero:
                texto = por_numero[m["orden"]].mensaje
            llamada = None
            transcripcion = None
            if m["canal"] == "llamada":
                info = m.get("llamada", {})
                intentos += 1
                resultado = info.get("resultado", "atendida")
                llamada = InfoLlamada(
                    tipo=info.get("tipo", "cotizacion" if conv["proposito"] == "cotizacion" else conv["proposito"]),
                    intento=info.get("intento", intentos),
                    resultado=resultado,
                    duracion_segundos=info.get("duracion_segundos"),
                    audio_disponible_hasta=_audio_hasta(fecha, info.get("duracion_segundos"), resultado),
                    resumen=info.get("resumen"),
                    acuerdo=info.get("acuerdo"),
                    precio_acordado=_dec(info["precio_acordado"]) if info.get("precio_acordado") is not None else None,
                )
                transcripcion = [
                    TurnoTranscripcion(
                        rol=t["rol"], quien="Abasto" if t["rol"] == "abasto" else nombre, texto=t["texto"], segundo=t.get("segundo")
                    )
                    for t in m.get("transcripcion", [])
                ] or None
            enviado = m["sentido"] == "enviado"
            crudos.append(
                (
                    clave,
                    participante,
                    "cliente_interno" if interno else "proveedor",
                    None if interno else conv["contraparte"],
                    conv["proposito"],
                    Mensaje(
                        id="",
                        conversacion_id="",
                        canal=m["canal"],
                        sentido=m["sentido"],
                        de="Abasto" if enviado else nombre,
                        para=nombre if enviado else "Abasto",
                        participante=participante,
                        fecha=fecha,
                        texto=texto,
                        transcripcion=transcripcion,
                        duracion_segundos=m.get("duracion_segundos"),
                        llamada=llamada,
                        etiqueta=m.get("etiqueta") or m.get("orden"),
                        motivo=m.get("motivo"),
                        nota=nota,
                    ),
                )
            )
    historial = [EventoEstado.model_validate(e) for e in raw["historial_estados"]]
    fechas = [e.en for e in historial if e.en] + [datetime.fromisoformat(raw["creado_en"])]
    plan_por_producto = {a.producto_id: a for a in (plan.asignaciones if plan else [])}
    necesarios = [l["necesario_para"] for l in lineas_raw if l["necesario_para"]]
    d = DetallePedido(
        id=pid,
        numero=raw["numero"],
        titulo=raw["titulo"],
        descripcion=raw.get("descripcion"),
        ejemplo=True,
        demo=False,
        negocio=negocio,
        cliente_interno=raw["cliente_interno"],
        origen=raw["origen"],
        solicitante=solicitante,
        creado_en=datetime.fromisoformat(raw["creado_en"]),
        actualizado_en=max(fechas),
        necesario_desde=min(necesarios, default=None),
        necesario_hasta=max(necesarios, default=None),
        estado=historial[-1].estado,
        historial_estados=historial,
        motivo_cancelacion=raw.get("motivo_cancelacion"),
        lineas=[
            LineaDetalle(
                producto_id=l["producto_id"],
                nombre=_producto(l["producto_id"])["nombre"],
                nombre_corto=_producto(l["producto_id"])["corto"],
                unidad=_producto(l["producto_id"])["unidad"],
                cantidad=l["cantidad"],
                necesario_para=l["necesario_para"],
                proveedor_id=plan_por_producto[l["producto_id"]].proveedor_id if l["producto_id"] in plan_por_producto else None,
                proveedor_nombre=plan_por_producto[l["producto_id"]].proveedor_nombre if l["producto_id"] in plan_por_producto else None,
            )
            for l in lineas_raw
        ],
        cotizaciones=cotizaciones,
        plan=plan,
        ordenes=ordenes,
        negociaciones=negociaciones,
        conversaciones=_agrupar(pid, crudos),
    )
    return d


def _ejemplos() -> list[DetallePedido]:
    datos = _historicos()
    salida = []
    for raw in datos.get("pedidos", []):
        try:
            salida.append(_detalle_ejemplo(raw, datos))
        except (KeyError, ValueError, ValidationError) as exc:  # un ejemplo roto no tira el listado
            log.warning("Pedido de ejemplo %s inválido: %s", raw.get("id"), exc)
    return salida


# ---------------------------------------------------------------- pedidos vivos
def _corrida(pedido_id: str) -> tuple[Any, dict[str, Any]] | tuple[None, None]:
    """La última corrida del agente sobre el pedido, y su dict crudo (por campos que agreguen otros bloques)."""
    from app.agente import CorridaAgente  # import local: agente importa media app

    crudas = [c for c in store.valores("agentes") if c and c.get("pedido_id") == pedido_id]
    if not crudas:
        return None, None
    cruda = max(crudas, key=lambda c: str(c.get("creada_en") or ""))
    try:
        return CorridaAgente.model_validate(cruda), cruda
    except ValidationError as exc:
        log.warning("Corrida %s ilegible: %s", cruda.get("id"), exc)
        return None, None


def _cliente_interno(corrida: Any, cruda: dict[str, Any] | None) -> ClienteInterno:
    """RF-05. El Bloque 2 agrega `cliente_interno` a la corrida; mientras no esté, es Personal."""
    valor = getattr(corrida, "cliente_interno", None) or (cruda or {}).get("cliente_interno") or "personal"
    return valor if valor in ("ventas", "personal") else "personal"  # type: ignore[return-value]


def _origen(corrida: Any, cruda: dict[str, Any] | None) -> Origen:
    if corrida is None:
        return "demo"
    cruda = cruda or {}
    canal = getattr(corrida, "canal", None) or cruda.get("canal") or cruda.get("origen")
    if canal in ("email", "solicitud_email"):
        return "solicitud_email"
    if canal in ("stock_minimo", "zafra", "solicitud_voz"):
        return canal  # type: ignore[return-value]
    return "solicitud_voz" if corrida.texto else "stock_minimo"  # sin texto: reposición del inventario


def _paso(corrida: Any, paso_id: str) -> Any:
    return next((p for p in corrida.pasos if p.id == paso_id), None)


def _hubo_dudas(corrida: Any) -> bool:
    return any(l.dudas or l.cantidad <= 0 for l in corrida.propuesta) or bool(
        corrida.interpretacion and corrida.interpretacion.dudas
    )


def _historial_corrida(corrida: Any, origen: Origen) -> tuple[list[EventoEstado], str | None]:
    """Estados §6.2 a partir de los pasos de la corrida del agente (docs/AGENTE.md)."""
    quien = {"solicitud_voz": "nota de voz", "solicitud_email": "email", "stock_minimo": "reposición del inventario"}
    eventos = [EventoEstado(estado="nuevo", en=corrida.creada_en, detalle=f"Pedido creado por {quien.get(origen, 'el agente')}.")]
    motivo = None
    confirmar = _paso(corrida, "confirmar")
    if confirmar and confirmar.inicio and _hubo_dudas(corrida):
        dudas = [d for l in corrida.propuesta for d in l.dudas] + list(corrida.interpretacion.dudas if corrida.interpretacion else [])
        eventos.append(
            EventoEstado(estado="datos_incompletos", en=confirmar.inicio, detalle=" ".join(dudas) or confirmar.detalle)
        )
    cotizar = _paso(corrida, "cotizar")
    if cotizar and cotizar.inicio:
        eventos.append(EventoEstado(estado="cotizando", en=cotizar.inicio, detalle=cotizar.detalle))
    optimizar = _paso(corrida, "optimizar")
    if optimizar and optimizar.estado == "hecho":
        eventos.append(EventoEstado(estado="cotizado", en=optimizar.fin, detalle=optimizar.detalle))
    negociar = _paso(corrida, "negociar")
    if negociar and negociar.estado in ("en_curso", "hecho"):
        eventos.append(EventoEstado(estado="negociando", en=negociar.inicio, detalle=negociar.detalle))
    ordenes = _paso(corrida, "ordenes")
    if ordenes and ordenes.inicio and any(o.requiere_aprobacion for o in corrida.ordenes):
        eventos.append(EventoEstado(estado="pendiente_aprobacion", en=ordenes.inicio, detalle=ordenes.detalle))
    if corrida.estado == "completada" and corrida.ordenes:
        enviadas = [o for o in corrida.ordenes if o.estado == "enviada_simulada"]
        if enviadas:
            fin = (ordenes.fin if ordenes else None) or max((o.enviada_en for o in enviadas if o.enviada_en), default=None)
            nums = ", ".join(o.numero for o in enviadas)
            eventos.append(EventoEstado(estado="aprobado", en=fin, detalle=f"Se emitieron las órdenes: {nums}."))
            eventos.append(
                EventoEstado(estado="pendiente_entrega", en=fin, detalle="Órdenes enviadas a los proveedores (envío simulado).")
            )
        else:
            motivo = "Se rechazaron todas las órdenes de compra."
            eventos.append(EventoEstado(estado="cancelado", en=ordenes.fin if ordenes else corrida.actualizada_en, detalle=motivo))
    elif corrida.estado == "cancelada":
        motivo = "Se canceló la compra desde el agente."
        eventos.append(EventoEstado(estado="cancelado", en=corrida.actualizada_en, detalle=motivo))
    return eventos, motivo


def _historial_sin_corrida(pedido: Pedido, inicio_cotizacion: datetime | None) -> list[EventoEstado]:
    """La demo guiada (/pedido → /feed → /plan → /negociacion), sin agente: del estado interno."""
    camino = {
        "nuevo": ["nuevo"],
        "cotizando": ["nuevo", "cotizando"],
        "cotizado": ["nuevo", "cotizando", "cotizado"],
        "optimizado": ["nuevo", "cotizando", "cotizado"],
        "negociando": ["nuevo", "cotizando", "cotizado", "negociando"],
        "aprobado": ["nuevo", "cotizando", "cotizado", "negociando", "aprobado"],
    }[pedido.estado]
    detalles = {
        "cotizando": "Pedí cotización a los proveedores.",
        "cotizado": "Hay cotizaciones normalizadas.",
        "negociando": "Ensayo de la negociación con el gemelo.",
        "aprobado": "Aprobaste la negociación en la demo guiada.",
    }
    return [
        EventoEstado(
            estado=e,  # type: ignore[arg-type]
            en=inicio_cotizacion if e == "cotizando" else None,
            detalle=detalles.get(e),
        )
        for e in camino
    ]


def _resultado_llamada(llamada: Llamada) -> ResultadoLlamada:
    if llamada.estado == "terminada":
        return "atendida"
    if llamada.estado == "fallida":
        error = (llamada.error or "").lower()
        if "no atendió" in error or "ocupado" in error:
            return "no_atendida"
        return "fallida"
    return "en_curso"


def _contactos(pedido_id: str) -> list[dict[str, Any]]:
    """Colección compartida `contactos` (la escribe el Bloque 5). Se ignora lo que no tenga la forma."""
    salida = []
    for c in store.valores("contactos"):
        if not isinstance(c, dict) or c.get("pedido_id") != pedido_id:
            continue
        if not c.get("proveedor_id") or c.get("canal") not in ("whatsapp", "email", "llamada"):
            continue
        try:
            fecha = datetime.fromisoformat(str(c["enviado_en"])) if c.get("enviado_en") else None
        except ValueError:
            fecha = None
        salida.append({**c, "_fecha": fecha})
    return salida


def _plan_vivo(pedido: Pedido) -> PlanDetalle | None:
    guardado = store.obtener_dict("planes", pedido.id)
    if not guardado:
        return None
    plan = Plan.model_validate(guardado)
    return PlanDetalle(
        costo_total=plan.costo_total,
        costo_baseline=plan.costo_baseline,
        ahorro=plan.ahorro,
        ahorro_pct=plan.ahorro_pct,
        proveedores_usados=[_nombre_proveedor(p) for p in plan.proveedores_usados],
        explicacion=plan.explicacion,
        asignaciones=[
            AsignacionDetalle(
                producto_id=a.producto_id,
                nombre=_producto(a.producto_id)["nombre"],
                proveedor_id=a.proveedor_id,
                proveedor_nombre=_nombre_proveedor(a.proveedor_id),
                cantidad=a.cantidad,
                precio_unitario_sin_iva=a.precio_unitario_sin_iva,
                subtotal=a.subtotal,
            )
            for a in plan.asignaciones
        ],
    )


def _cotizaciones_vivas(pedido_id: str, mensajes: dict[str, MensajeCrudo]) -> list[CotizacionDetalle]:
    salida = []
    for c in sorted(store.listar("cotizaciones", Cotizacion, pedido_id=pedido_id), key=lambda c: c.proveedor_id):
        mensaje = mensajes.get(c.mensaje_id)
        recibida = mensaje.recibido_en if mensaje else None
        vigencia = c.validez_dias or VIGENCIA_POR_DEFECTO
        salida.append(
            CotizacionDetalle(
                id=c.id,
                proveedor_id=c.proveedor_id,
                proveedor_nombre=_nombre_proveedor(c.proveedor_id),
                canal=CANAL_DEL_SIMULADOR.get(mensaje.canal) if mensaje else None,
                recibida_en=recibida,
                items=[
                    ItemCotizacionDetalle(
                        producto_id=i.producto_id,
                        nombre=_producto(i.producto_id)["nombre"],
                        precio_original=i.precio_original,
                        moneda_original=i.moneda_original,
                        incluye_iva_original=i.incluye_iva_original,
                        unidad_original=i.unidad_original,
                        precio_unitario_sin_iva=i.precio_unitario_sin_iva,
                        conversion_aplicada=i.conversion_aplicada,
                        cantidad_minima=i.cantidad_minima,
                        evidencia=i.evidencia,
                    )
                    for i in c.items
                ],
                costo_envio=c.costo_envio,
                plazo_pago_dias=c.plazo_pago_dias,
                lead_time_dias=c.lead_time_dias,
                validez_dias=c.validez_dias,
                vigencia_dias=vigencia,
                vence_el=(recibida.date() + timedelta(days=vigencia)) if recibida else None,
                estado=c.estado,
                observaciones=c.observaciones,
            )
        )
    return salida


def _ordenes_vivas(corrida: Any) -> list[OrdenDetalle]:
    if corrida is None:
        return []
    estados = {"esperando_aprobacion": "pendiente_aprobacion", "enviada_simulada": "pendiente_entrega", "rechazada": "cancelada"}
    salida = []
    for o in corrida.ordenes:
        salida.append(
            OrdenDetalle(
                id=o.id,
                numero=o.numero,
                proveedor_id=o.proveedor_id,
                proveedor_nombre=o.proveedor_nombre,
                estado=estados[o.estado],  # type: ignore[arg-type]
                estado_agente=o.estado,
                requiere_aprobacion=o.requiere_aprobacion,
                motivos=o.motivos,
                emitida_por="agente" if o.estado == "enviada_simulada" else None,
                aprobada_por=o.aprobada_por,
                emitida_en=o.enviada_en,
                envio=o.envio,
                total_sin_iva=o.total_sin_iva,
                total_con_iva=o.total_con_iva,
                lineas=[
                    LineaOrdenDetalle(
                        producto_id=l.producto_id,
                        nombre=l.nombre,
                        cantidad=l.cantidad,
                        unidad=l.unidad,
                        precio_unitario_sin_iva=l.precio_unitario_sin_iva,
                        subtotal=l.subtotal,
                        aprobacion=l.aprobacion,
                        motivo=l.motivo,
                        evidencia=l.evidencia,
                    )
                    for l in o.lineas
                ],
                negociacion_id=o.negociacion_id,
                corrida_id=corrida.id,
                mensaje=o.mensaje,
            )
        )
    return salida


def _negociaciones_vivas(pedido_id: str, llamadas: list[Llamada]) -> list[NegociacionDetalle]:
    por_id = {l.id: l for l in llamadas}
    salida = []
    for neg in store.listar("negociaciones", Negociacion, pedido_id=pedido_id):
        llamada = por_id.get(neg.llamada_id or "")
        salida.append(
            NegociacionDetalle(
                id=neg.id,
                proveedor_id=neg.proveedor_id,
                proveedor_nombre=_nombre_proveedor(neg.proveedor_id),
                estado=neg.estado,
                elegida=neg.elegida,
                mensaje_propuesto=neg.mensaje_propuesto,
                estrategias=[
                    EstrategiaResumen(
                        nombre=e.nombre,
                        descripcion=e.descripcion,
                        concesion_obtenida_pct=e.concesion_obtenida_pct,
                        ganancia_esperada_uyu=e.ganancia_esperada_uyu,
                        riesgo=e.riesgo,
                    )
                    for e in neg.estrategias
                ],
                llamada_id=neg.llamada_id,
                resultado=(llamada.resultado.resumen if llamada and llamada.resultado else None),
            )
        )
    return salida


def _conversaciones_vivas(
    pedido: Pedido,
    corrida: Any,
    origen: Origen,
    mensajes: list[MensajeCrudo],
    llamadas: list[Llamada],
    cotizaciones: dict[str, Cotizacion],
    inicio_cotizacion: datetime | None,
    proveedores_pedidos: list[str],
) -> list[Conversacion]:
    negocio = pedido.negocio
    solicitante = pedido.comprador or "Compras"
    firma = _firma(solicitante)
    crudos: list[tuple[str, str, str, str | None, Proposito, Mensaje]] = []

    def de_proveedor(pid: str, proposito: Proposito, mensaje: Mensaje) -> None:
        crudos.append((pid, _nombre_proveedor(pid), "proveedor", pid, proposito, mensaje))

    def msj(**kw: Any) -> Mensaje:
        return Mensaje(id="", conversacion_id="", **kw)

    # 1. la solicitud interna
    if corrida is not None and corrida.texto:
        canal: CanalMensaje = "email" if origen == "solicitud_email" else "nota_voz"
        crudos.append(
            (
                "interno",
                solicitante,
                "cliente_interno",
                None,
                "solicitud",
                msj(
                    canal=canal,
                    sentido="recibido",
                    de=firma,
                    para="Abasto",
                    participante=solicitante,
                    fecha=corrida.creada_en,
                    texto=corrida.texto,
                    nota="Dictado o escrito en la pantalla del agente." if canal == "nota_voz" else None,
                ),
            )
        )
    # 2. lo que registró el Bloque 5 (secuencia de contacto)
    contactos = _contactos(pedido.id)
    con_solicitud = {c["proveedor_id"] for c in contactos if c.get("motivo") == "solicitud_cotizacion"}
    con_negociacion = {c["proveedor_id"] for c in contactos if c.get("motivo") == "negociacion"}
    for c in contactos:
        pid = c["proveedor_id"]
        nombre = _nombre_proveedor(pid)
        de_proveedor(
            pid,
            "negociacion" if c.get("motivo") == "negociacion" else "cotizacion",
            msj(
                canal=c["canal"],
                sentido="enviado",
                de="Abasto",
                para=nombre,
                participante=nombre,
                fecha=c["_fecha"],
                texto=c.get("texto"),
                motivo=c.get("motivo"),
            ),
        )
    # 3. la solicitud de cotización: el simulador le pide lo mismo a cada proveedor
    if inicio_cotizacion is not None:
        lineas = [l.model_dump() for l in pedido.lineas]
        texto = texto_solicitud(lineas, negocio, firma)
        for pid in proveedores_pedidos:
            if pid in con_solicitud:
                continue
            nombre = _nombre_proveedor(pid)
            de_proveedor(
                pid,
                "cotizacion",
                msj(
                    canal=canal_de_solicitud(pid),
                    sentido="enviado",
                    de="Abasto",
                    para=nombre,
                    participante=nombre,
                    fecha=inicio_cotizacion,
                    texto=texto,
                    motivo="solicitud_cotizacion",
                    nota="Reconstruido a partir del pedido: el envío es simulado.",
                ),
            )
    # 4. lo que respondieron los proveedores
    de_llamada = {l.mensaje_id for l in llamadas if l.mensaje_id}
    for m in mensajes:
        if m.id in de_llamada:
            continue  # la transcripción va con la llamada
        nombre = _nombre_proveedor(m.proveedor_id)
        de_proveedor(
            m.proveedor_id,
            "cotizacion",
            msj(
                canal=CANAL_DEL_SIMULADOR.get(m.canal, "whatsapp"),
                sentido="recibido",
                de=nombre,
                para="Abasto",
                participante=nombre,
                fecha=m.recibido_en,
                texto=m.contenido_texto,
                archivo_url=m.archivo_url,
                etiqueta=_etiqueta_mensaje(m, cotizaciones),
            ),
        )
    # 5. las llamadas
    intentos: dict[tuple[str, str], int] = {}
    por_mensaje = {m.id: m for m in mensajes}
    for l in sorted(llamadas, key=lambda l: l.iniciada_en):
        nombre = _nombre_proveedor(l.proveedor_id)
        intentos[(l.proveedor_id, l.tipo)] = intentos.get((l.proveedor_id, l.tipo), 0) + 1
        resultado = _resultado_llamada(l)
        mensaje_cot = por_mensaje.get(l.mensaje_id or "")
        de_proveedor(
            l.proveedor_id,
            "negociacion" if l.tipo == "negociacion" else "cotizacion",
            msj(
                canal="llamada",
                sentido="enviado",
                de="Abasto",
                para=nombre,
                participante=nombre,
                fecha=l.iniciada_en,
                transcripcion=[
                    TurnoTranscripcion(rol=t.rol, quien="Abasto" if t.rol == "abasto" else nombre, texto=t.texto, segundo=t.segundo)
                    for t in l.transcripcion
                ]
                or None,
                llamada=InfoLlamada(
                    tipo=l.tipo,
                    intento=intentos[(l.proveedor_id, l.tipo)],
                    resultado=resultado,
                    duracion_segundos=l.duracion_segundos,
                    modo=l.modo,
                    audio_disponible_hasta=_audio_hasta(l.iniciada_en, l.duracion_segundos, resultado),
                    resumen=(l.resultado.resumen if l.resultado else None) or l.error,
                    acuerdo=l.resultado.acuerdo if l.resultado else None,
                    precio_acordado=l.resultado.precio_acordado if l.resultado else None,
                    telefono=l.telefono,
                ),
                etiqueta=_etiqueta_mensaje(mensaje_cot, cotizaciones) if mensaje_cot else None,
                motivo="negociacion" if l.tipo == "negociacion" else "reintento",
            ),
        )
    # 6. el mensaje de negociación aprobado (envío simulado, sin hora registrada)
    for neg in store.listar("negociaciones", Negociacion, pedido_id=pedido.id):
        if neg.estado != "enviada_simulada" or neg.proveedor_id in con_negociacion:
            continue
        nombre = _nombre_proveedor(neg.proveedor_id)
        de_proveedor(
            neg.proveedor_id,
            "negociacion",
            msj(
                canal="whatsapp",
                sentido="enviado",
                de="Abasto",
                para=nombre,
                participante=nombre,
                fecha=None,
                texto=neg.mensaje_propuesto,
                motivo="negociacion",
                nota="Mensaje aprobado (envío simulado): el backend no registra la hora del envío.",
            ),
        )
    # 7. las órdenes de compra enviadas
    if corrida is not None:
        for o in corrida.ordenes:
            if o.estado != "enviada_simulada":
                continue
            de_proveedor(
                o.proveedor_id,
                "orden",
                msj(
                    canal="whatsapp",
                    sentido="enviado",
                    de="Abasto",
                    para=o.proveedor_nombre,
                    participante=o.proveedor_nombre,
                    fecha=o.enviada_en,
                    texto=o.mensaje,
                    etiqueta=o.numero,
                    motivo="orden",
                    nota="Envío simulado.",
                ),
            )
    return _agrupar(pedido.id, crudos)


def _etiqueta_mensaje(m: MensajeCrudo | None, cotizaciones: dict[str, Cotizacion]) -> str | None:
    if m is None:
        return None
    if m.estado in ("pendiente", "leyendo"):
        return "Leyendo…"
    if m.estado == "error":
        return "No se pudo leer"
    cot = cotizaciones.get(m.cotizacion_id or "")
    if cot is None:
        return None
    return {"valida": "Cotización leída", "revisar": "Para revisar", "confirmada": "Confirmada"}.get(cot.estado)


def _detalle_vivo(pedido: Pedido) -> DetallePedido:
    corrida, cruda = _corrida(pedido.id)
    origen = _origen(corrida, cruda)
    mensajes = sorted(store.listar("mensajes", MensajeCrudo, pedido_id=pedido.id), key=lambda m: m.recibido_en)
    llamadas = sorted(store.listar("llamadas", Llamada, pedido_id=pedido.id), key=lambda l: l.iniciada_en)
    cotizaciones = {c.id: c for c in store.listar("cotizaciones", Cotizacion, pedido_id=pedido.id)}
    simulacion = store.obtener_dict("simulaciones", pedido.id)
    inicio_cotizacion = datetime.fromtimestamp(simulacion["inicio"]) if simulacion and simulacion.get("inicio") else None
    proveedores_pedidos = list((simulacion or {}).get("proveedores", {}))
    if corrida is not None:
        historial, motivo = _historial_corrida(corrida, origen)
        creado = corrida.creada_en
    else:
        historial, motivo = _historial_sin_corrida(pedido, inicio_cotizacion), None
        creado = inicio_cotizacion or datetime.combine(pedido.fecha, time())
    plan = _plan_vivo(pedido)
    plan_por_producto = {a.producto_id: a for a in (plan.asignaciones if plan else [])}
    avisos = list(corrida.avisos) if corrida is not None else []
    if corrida is not None and corrida.estado == "error" and corrida.error:
        avisos.insert(0, f"La compra del agente se detuvo: {corrida.error}")
    momentos = [creado, *(m.recibido_en for m in mensajes), *(l.iniciada_en for l in llamadas)]
    if corrida is not None:
        momentos.append(corrida.actualizada_en)
    necesarios = [l.necesario_para for l in pedido.lineas]
    descripcion = pedido.descripcion
    return DetallePedido(
        id=pedido.id,
        numero=NUMEROS_VIVOS.get(pedido.id, f"PED-{pedido.id[-4:].upper()}"),
        titulo=descripcion or f"Pedido de {pedido.negocio}",
        descripcion=(corrida.resumen if corrida is not None and corrida.resumen else None),
        ejemplo=False,
        demo=pedido.id == pedidos.PEDIDO_DEMO_ID,
        negocio=pedido.negocio,
        cliente_interno=_cliente_interno(corrida, cruda),
        origen=origen,
        solicitante=pedido.comprador,
        creado_en=creado,
        actualizado_en=max(momentos),
        necesario_desde=min(necesarios, default=None),
        necesario_hasta=max(necesarios, default=None),
        estado=historial[-1].estado,
        historial_estados=historial,
        motivo_cancelacion=motivo,
        lineas=[
            LineaDetalle(
                producto_id=l.producto_id,
                nombre=_producto(l.producto_id)["nombre"],
                nombre_corto=_producto(l.producto_id)["corto"],
                unidad=_producto(l.producto_id)["unidad"],
                cantidad=l.cantidad,
                necesario_para=l.necesario_para,
                proveedor_id=plan_por_producto[l.producto_id].proveedor_id if l.producto_id in plan_por_producto else None,
                proveedor_nombre=plan_por_producto[l.producto_id].proveedor_nombre if l.producto_id in plan_por_producto else None,
            )
            for l in pedido.lineas
        ],
        cotizaciones=_cotizaciones_vivas(pedido.id, {m.id: m for m in mensajes}),
        plan=plan,
        ordenes=_ordenes_vivas(corrida),
        negociaciones=_negociaciones_vivas(pedido.id, llamadas),
        conversaciones=_conversaciones_vivas(
            pedido, corrida, origen, mensajes, llamadas, cotizaciones, inicio_cotizacion, proveedores_pedidos
        ),
        corrida_id=corrida.id if corrida is not None else None,
        avisos=avisos,
    )


def _pedidos_vivos() -> list[Pedido]:
    demo = pedidos.obtener(pedidos.PEDIDO_DEMO_ID)  # lo seedea si hace falta
    vivos = {demo.id: demo} if demo else {}
    for valor in store.valores("pedidos"):
        try:
            p = Pedido.model_validate(valor)
        except ValidationError:
            continue
        vivos.setdefault(p.id, p)
    return list(vivos.values())


# ---------------------------------------------------------------- API del módulo
def todos() -> list[DetallePedido]:
    detalles = [_aplicar_marcas(_detalle_vivo(p)) for p in _pedidos_vivos()]
    detalles += [_aplicar_marcas(d) for d in _ejemplos()]
    return sorted(detalles, key=lambda d: d.actualizado_en, reverse=True)


def detalle(pedido_id: str) -> DetallePedido:
    pedido = pedidos.obtener(pedido_id)
    if pedido is not None:
        return _aplicar_marcas(_detalle_vivo(pedido))
    for d in _ejemplos():
        if d.id == pedido_id or d.numero.lower() == pedido_id.lower():
            return _aplicar_marcas(d)
    raise PedidoNoEncontrado(pedido_id)


def resumen(d: DetallePedido) -> ResumenPedido:
    if d.ordenes:
        proveedores = list(dict.fromkeys(o.proveedor_nombre for o in d.ordenes))
    elif d.plan:
        proveedores = d.plan.proveedores_usados
    else:
        proveedores = list(dict.fromkeys(c.contraparte for c in d.conversaciones if c.contraparte_tipo == "proveedor"))
    return ResumenPedido(
        id=d.id,
        numero=d.numero,
        titulo=d.titulo,
        productos=[
            ProductoResumen(
                producto_id=l.producto_id, nombre=l.nombre, nombre_corto=l.nombre_corto, cantidad=l.cantidad, unidad=l.unidad
            )
            for l in d.lineas
        ],
        cliente_interno=d.cliente_interno,
        origen=d.origen,
        proveedores=proveedores,
        ordenes=[o.numero for o in d.ordenes],
        estado=d.estado,
        creado_en=d.creado_en,
        actualizado_en=d.actualizado_en,
        ejemplo=d.ejemplo,
        demo=d.demo,
    )


def sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def coincide(d: DetallePedido, q: str) -> bool:
    """RF-12: busca por producto, proveedor y orden de compra (y por número y título del pedido)."""
    textos = [d.numero, d.titulo]
    textos += [t for l in d.lineas for t in (l.nombre, l.nombre_corto)]
    textos += [o.numero for o in d.ordenes]
    textos += [o.proveedor_nombre for o in d.ordenes]
    textos += [c.proveedor_nombre for c in d.cotizaciones]
    textos += [c.contraparte for c in d.conversaciones if c.contraparte_tipo == "proveedor"]
    if d.plan:
        textos += d.plan.proveedores_usados
    pajar = sin_tildes(" | ".join(textos))
    return all(palabra in pajar for palabra in sin_tildes(q).split())
