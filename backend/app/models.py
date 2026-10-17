"""Contrato de datos de Abasto (rol C).

Fuente: docs/ARQUITECTURA.md §3. Las extensiones respecto de ese documento están marcadas con
`# ext:` y explicadas en docs/CONTRATO_BACKEND.md.

Montos: `Decimal` en el código para no perder centavos; se serializan como número en el JSON
para que el frontend no reciba strings.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

Monto = Annotated[
    Decimal,
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]

UnidadCanonica = Literal["unidad", "l", "kg"]
Canal = Literal["whatsapp_texto", "whatsapp_audio", "pdf", "foto", "llamada"]
Moneda = Literal["UYU", "USD"]


# ---------------------------------------------------------------- pedido y catálogo
class Producto(BaseModel):
    id: str
    nombre: str
    unidad_canonica: UnidadCanonica


class LineaPedido(BaseModel):
    producto_id: str
    cantidad: float
    necesario_para: date


class Pedido(BaseModel):
    id: str
    negocio: str
    comprador: str | None = None  # ext
    descripcion: str | None = None  # ext
    fecha: date  # ext: fecha del pedido, referencia para los plazos de entrega
    lineas: list[LineaPedido]
    proveedor_habitual_id: str
    estado: Literal["nuevo", "cotizando", "cotizado", "optimizado", "negociando", "aprobado"]


class Conversion(BaseModel):
    factor: float
    a: UnidadCanonica


class PedidoCompleto(Pedido):
    """Respuesta de GET /pedidos/demo: el pedido más lo que la UI necesita para mostrarlo."""

    catalogo: list[Producto]
    conversiones: dict[str, Conversion]
    tipo_cambio_usd: float
    iva: float


# ---------------------------------------------------------------- proveedores
class Proveedor(BaseModel):
    id: str
    nombre: str
    rubro: str
    canal_preferido: Canal
    confiabilidad: float


class EstadoProveedor(BaseModel):  # ext: para que la UI muestre "no respondió todavía"
    proveedor_id: str
    nombre: str
    canal: Canal
    estado: Literal["esperando", "respondio", "sin_pedido"]
    responde_en_segundos: float | None = None


# ---------------------------------------------------------------- mensajes y cotizaciones
class MensajeCrudo(BaseModel):
    id: str
    pedido_id: str
    proveedor_id: str
    canal: Canal
    contenido_texto: str | None = None
    archivo: str | None = None  # nombre de archivo en runtime/archivos/
    archivo_url: str | None = None  # ext: ruta servida por GET /archivos/{nombre}
    recibido_en: datetime
    estado: Literal["pendiente", "leyendo", "extraido", "error"]
    error: str | None = None  # ext
    cotizacion_id: str | None = None  # ext: link directo a la tarjeta


class ItemCotizado(BaseModel):
    producto_id: str
    descripcion_original: str | None = None  # ext
    precio_unitario_sin_iva: Monto  # UYU por unidad canónica, ya convertido
    precio_original: Monto
    moneda_original: Moneda
    incluye_iva_original: bool
    unidad_original: str
    conversion_aplicada: str | None = None
    cantidad_minima: float | None = None  # en unidad canónica
    evidencia: str


class Cotizacion(BaseModel):
    id: str
    pedido_id: str  # ext
    mensaje_id: str
    proveedor_id: str
    items: list[ItemCotizado]
    costo_envio: Monto = Decimal(0)
    pedido_minimo_total: Monto | None = None
    plazo_pago_dias: int = 0
    lead_time_dias: int
    validez_dias: int | None = None
    observaciones: list[str] = Field(default_factory=list)
    confianza: float
    campos_dudosos: list[str] = Field(default_factory=list)
    estado: Literal["valida", "revisar", "confirmada"] = "valida"  # ext
    items_sin_mapear: list[str] = Field(default_factory=list)  # ext: no entran al solver
    tipo_cambio_usd: float | None = None  # ext: el usado en la conversión


class ConfirmacionCotizacion(BaseModel):  # ext: el "un clic" de Lucía
    model_config = ConfigDict(extra="forbid")  # "incluyeIva" mal escrito → 422, no confirma en silencio

    incluye_iva: bool | None = None
    # Forma genérica que usa el frontend: {"campo": "iva", "valor": true}
    campo: str | None = None
    valor: bool | None = None

    def iva(self) -> bool | None:
        """Lo que se confirmó sobre el IVA, venga en la forma que venga."""
        if self.campo == "iva":
            return self.valor
        return self.incluye_iva


# ---------------------------------------------------------------- plan
class Asignacion(BaseModel):
    producto_id: str
    proveedor_id: str
    cantidad: float
    precio_unitario_sin_iva: Monto
    subtotal: Monto


class NoMasBarato(BaseModel):  # ext: el caso de las sillas
    producto_id: str
    mas_barato_id: str
    precio_mas_barato: Monto
    elegido_id: str
    precio_elegido: Monto
    motivo: str


class Plan(BaseModel):
    pedido_id: str
    asignaciones: list[Asignacion]
    costo_total: Monto  # sin IVA, con envíos
    costo_baseline: Monto  # todo al proveedor habitual
    ahorro: Monto
    ahorro_pct: float
    ahorro_comparable: Monto  # ext: solo sobre lo que vende el habitual
    ahorro_pct_comparable: float  # ext
    proveedores_usados: list[str]
    restricciones_activas: list[str]
    relajaciones: list[str]
    no_mas_barato: list[NoMasBarato] = Field(default_factory=list)  # ext
    explicacion: str
    explicacion_origen: Literal["llm", "plantilla"] = "plantilla"  # ext
    oportunidad_negociacion: str | None = None
    brecha_oportunidad: Monto | None = None  # ext
    tipo_cambio_usd: float  # ext
    cotizaciones_excluidas: list[str] = Field(default_factory=list)  # ext


# ---------------------------------------------------------------- negociación
class EstrategiaNegociacion(BaseModel):
    nombre: Literal["competencia", "volumen", "plazo"]
    descripcion: str
    transcripcion: list[dict[str, Any]]
    concesion_obtenida_pct: float
    ganancia_esperada_uyu: Monto
    riesgo: Literal["bajo", "medio", "alto"]


class Negociacion(BaseModel):
    id: str
    pedido_id: str
    proveedor_id: str
    estrategias: list[EstrategiaNegociacion]
    elegida: str
    mensaje_propuesto: str
    estado: Literal["simulada", "aprobada", "enviada_simulada"]
    llamada_id: str | None = None  # si se aprobó para negociar por teléfono (docs/LLAMADAS.md)


class AprobacionNegociacion(BaseModel):  # ext: el mensaje es editable antes de aprobar
    mensaje: str | None = None


class ItemNegociable(BaseModel):
    producto_id: str
    cantidad: float
    precio_cotizado_sin_iva: Monto
    mejor_alternativa_proveedor_id: str | None = None
    mejor_alternativa_nombre: str | None = None
    mejor_alternativa_precio: Monto | None = None
    mejor_alternativa_condicion: str | None = None  # p. ej. "exige mínimo 20 unidades"


class ContextoNegociacion(BaseModel):
    """Lo que el backend (C) le pasa a la Capa 5 (A). Ver docs/CONTRATO_BACKEND.md."""

    pedido_id: str
    negocio: str
    comprador: str | None
    proveedor: Proveedor
    perfil_privado: dict[str, Any]  # personalidad, precio_piso_pct, perfil_concesion, sensible_a…
    cotizacion: Cotizacion
    items: list[ItemNegociable]
    valor_en_juego_uyu: Monto  # Σ cantidad × precio cotizado de este proveedor


class ErrorRespuesta(BaseModel):
    error: str
    detalle: Any = None


# ---------------------------------------------------------------- llamadas (docs/LLAMADAS.md)
class TurnoLlamada(BaseModel):
    rol: Literal["abasto", "proveedor"]
    texto: str
    segundo: int | None = None


class ResultadoLlamada(BaseModel):
    """Lo que se sacó de la llamada. En negociación: si hubo acuerdo y a qué precio."""

    resumen: str | None = None
    acuerdo: bool | None = None
    precio_acordado: Monto | None = None  # por unidad canónica, sin IVA, si el proveedor lo dijo
    condicion: str | None = None


class Llamada(BaseModel):
    id: str
    pedido_id: str
    proveedor_id: str
    tipo: Literal["cotizacion", "negociacion"]
    negociacion_id: str | None = None
    modo: Literal["real", "simulada"]
    estado: Literal["iniciando", "sonando", "en_curso", "procesando", "terminada", "fallida"]
    telefono: str | None = None  # enmascarado: +598 9•• ••• 222
    conversation_id: str | None = None
    call_sid: str | None = None
    transcripcion: list[TurnoLlamada] = Field(default_factory=list)
    resultado: ResultadoLlamada | None = None
    duracion_segundos: int | None = None
    mensaje_id: str | None = None  # tipo cotizacion: el mensaje que entra al feed
    error: str | None = None
    iniciada_en: datetime


class LlamarNegociacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mensaje: str | None = None  # el mensaje aprobado (editable), que guía al agente


class ConfigLlamadas(BaseModel):
    modo: Literal["real", "simulada"]
    lista: bool  # en modo real: si está todo configurado para llamar
    faltan: list[str]  # variables de entorno que faltan
    proveedores_con_telefono: list[str]
