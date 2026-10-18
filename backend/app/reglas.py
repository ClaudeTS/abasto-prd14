"""Reglas por producto, historial con reversión y configuración general (PRD 1.4: RF-02, RF-03, RF-04,
RF-13, RF-14, RF-15, RF-20; tablas de §11.2).

Dónde vive cada dato (sin duplicar):
- compra automática (`modo`), stock mínimo y tope total por producto (`tope_automatico_uyu`) son del
  inventario del agente (`app/inventario.py`): se leen con `inventario.item()` y se escriben con
  `inventario.cambiar()`.
- el resto (stock base, zafra, tope de precio unitario, plazos, proveedores habilitados, sustitutos,
  negociación, cliente interno) va en la colección "reglas", un documento por producto.
- cada cambio queda en "historial_reglas", una fila por campo (tabla `historial_regla`).
- la configuración general (`configuracion`) va en la colección "configuracion", documento "general";
  `pipeline.config_vigente()` la superpone a la `config` de data/pedido_demo.json.

Las reglas valen para lo que se calcule después del cambio: el próximo cierre, las cotizaciones y
órdenes nuevas. No hay "deploy": el agente las lee del store en cada decisión.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app import inventario, pipeline, store
from app.auth import Usuario
from app.inventario import CambioInventario, Reposicion
from app.models import Monto
from app.normalizacion import fmt

COLECCION = "reglas"
HISTORIAL = "historial_reglas"
CONFIG = "configuracion"
CONFIG_ID = "general"
HORA_CIERRE = 18  # consulta diaria de stock al cierre de la jornada (RF-02)
VIGENCIA_DEFECTO = 30

Moneda = Literal["UYU", "USD"]
ClienteInterno = Literal["ventas", "personal"]


# ---------------------------------------------------------------- modelos
class Zafra(BaseModel):
    inicio: str  # "MM-DD": la zafra se repite todos los años (ej. "05-01")
    fin: str  # "MM-DD" (puede cruzar el fin de año)
    cantidad: float


class ProveedorHabilitado(BaseModel):
    proveedor_id: str
    prioridad: int = 1
    minimo_compra: float | None = None  # en la unidad del producto; None = sin mínimo
    unidad_venta: str | None = None  # "caja de 5 resmas"; None = la unidad del producto
    factor_conversion: float = 1


class Sustituto(BaseModel):
    nombre: str
    producto_id: str | None = None
    aprobado_por: str | None = None


class Reglas(BaseModel):
    """Todas las reglas de un producto (regla_producto, producto_proveedor, producto_sustituto,
    regla_negociacion)."""

    compra_automatica: bool
    stock_minimo: float
    stock_base: float | None = None
    zafra: Zafra | None = None
    tope_precio_unitario: Monto | None = None  # sin IVA, en moneda_tope
    moneda_tope: Moneda = "UYU"
    tope_automatico_uyu: Monto | None = None  # tope del total por producto (agente original)
    plazo_entrega_max_dias: int | None = None
    plazo_pago_requerido_dias: int | None = None
    proveedores: list[ProveedorHabilitado] = Field(default_factory=list)
    sustitutos: list[Sustituto] = Field(default_factory=list)
    descuento_objetivo_pct: float | None = None  # None = a definir (pregunta abierta 1)
    concesion_maxima_pct: float | None = None
    cliente_interno: ClienteInterno = "personal"


DEL_INVENTARIO = ("compra_automatica", "stock_minimo", "tope_automatico_uyu")
PROPIOS = tuple(c for c in Reglas.model_fields if c not in DEL_INVENTARIO)


class PropuestaReglas(BaseModel):
    """Solo los campos que vienen cambian; null borra (zafra, stock base, topes, negociación)."""

    compra_automatica: bool | None = None
    stock_minimo: float | None = None
    stock_base: float | None = None
    zafra: Zafra | None = None
    tope_precio_unitario: float | None = None
    moneda_tope: Moneda | None = None
    tope_automatico_uyu: float | None = None
    plazo_entrega_max_dias: int | None = None
    plazo_pago_requerido_dias: int | None = None
    proveedores: list[ProveedorHabilitado] | None = None
    sustitutos: list[Sustituto] | None = None
    descuento_objetivo_pct: float | None = None
    concesion_maxima_pct: float | None = None
    cliente_interno: ClienteInterno | None = None

    def campos(self) -> dict[str, Any]:
        return {c: getattr(self, c) for c in self.model_fields_set if c in Reglas.model_fields}


class CambioReglas(PropuestaReglas):
    motivo: str  # obligatorio (RF-15)


class Revertir(BaseModel):
    motivo: str | None = None


class PrecioVigente(BaseModel):
    proveedor_id: str
    proveedor_nombre: str
    precio_sin_iva_uyu: Monto
    cotizacion_id: str
    pedido_id: str
    validez_dias: int | None
    evidencia: str


class Contexto(BaseModel):
    """El dato actual que afecta a cada regla (§11.4)."""

    unidad: str
    stock_actual: float
    en_camino: float
    fecha_corte: datetime  # último cierre de jornada
    proximo_cierre: datetime
    reposicion: Reposicion | None  # lo que pediría hoy el cierre con las reglas guardadas
    precios: list[PrecioVigente]  # el último de cada proveedor, del más barato al más caro
    mejor_precio: PrecioVigente | None
    tope_unitario_uyu: Monto | None  # el tope llevado a pesos con el tipo de cambio
    tipo_cambio_usd: float
    en_zafra: bool


class VistaReglas(BaseModel):
    producto_id: str
    nombre: str
    nombre_corto: str
    unidad: str
    tipo: str
    reglas: Reglas
    contexto: Contexto
    actualizado_por: str | None = None
    actualizado_en: datetime | None = None


class CambioRegla(BaseModel):
    """Una fila de historial_regla."""

    id: str
    tabla: Literal["regla_producto", "configuracion"]
    registro: str  # producto_id o "general"
    campo: str
    etiqueta: str
    anterior: Any = None
    nuevo: Any = None
    texto_anterior: str
    texto_nuevo: str
    usuario_id: str
    usuario: str
    fecha: datetime
    motivo: str
    lote: str  # los campos guardados juntos
    revierte: str | None = None  # id del cambio que deshace
    revertido_por: str | None = None


class CambioCampo(BaseModel):
    campo: str
    etiqueta: str
    anterior: str
    nuevo: str


class VistaPrevia(BaseModel):
    valido: bool
    errores: dict[str, str]
    cambios: list[CambioCampo]
    aplica_cierre: bool  # False: equipamiento, se compra cuando alguien lo pide
    dispara_compra: bool
    cantidad: float
    motivo: Literal["pronostico", "stock_base", "zafra"] | None
    aprobacion: Literal["automatica", "requiere_aprobacion"] | None
    mejor_precio: PrecioVigente | None
    tope_unitario_uyu: Monto | None
    bajo_tope: bool | None  # None: sin tope o sin cotizaciones
    texto: str
    evidencia: str | None


class Configuracion(BaseModel):
    tipo_cambio_usd: float
    fecha_tipo_cambio: date | None = None
    iva: float  # fracción: 0.22
    vigencia_dias_default: int
    moneda_base: Moneda
    monedas: list[Moneda] = Field(default_factory=lambda: ["UYU", "USD"])
    actualizado_por: str | None = None
    actualizado_en: datetime | None = None


class CambioConfiguracion(BaseModel):
    tipo_cambio_usd: float | None = None
    fecha_tipo_cambio: date | None = None
    iva: float | None = None
    vigencia_dias_default: int | None = None
    moneda_base: Moneda | None = None
    motivo: str | None = None


class ReglasError(Exception):
    def __init__(self, status: int, error: str, detalle: Any = None) -> None:
        super().__init__(error)
        self.status = status
        self.error = error
        self.detalle = detalle


# ---------------------------------------------------------------- lectura
def productos_ids() -> list[str]:
    return [p["producto_id"] for p in store.semilla("inventario_demo")["productos"]]


def _existe(producto_id: str) -> None:
    if producto_id not in productos_ids():
        raise ReglasError(404, f"No existe el producto '{producto_id}'")


def _item(producto_id: str, simular: dict[str, Any] | None = None):
    return inventario.item(producto_id, inventario.horizonte_por_defecto(), simular=simular)


def actuales(producto_id: str) -> Reglas:
    _existe(producto_id)
    item = _item(producto_id)
    guardadas = store.obtener_dict(COLECCION, producto_id) or {}
    propios = {c: guardadas[c] for c in PROPIOS if c in guardadas}
    if "proveedores" not in propios:  # antes de editar: los del inventario, en su orden
        propios["proveedores"] = [
            {"proveedor_id": p.id, "prioridad": n + 1} for n, p in enumerate(item.proveedores)
        ]
    return Reglas(
        compra_automatica=item.modo == "automatico",
        stock_minimo=item.stock_minimo,
        tope_automatico_uyu=item.tope_automatico_uyu,
        **propios,
    )


def tipo_cambio() -> float:
    return float(pipeline.config_vigente()["tipo_cambio_usd"])


def _tope_uyu(reglas: Reglas) -> Decimal | None:
    if reglas.tope_precio_unitario is None:
        return None
    tope = Decimal(str(reglas.tope_precio_unitario))
    if reglas.moneda_tope == "USD":
        tope = (tope * Decimal(str(tipo_cambio()))).quantize(Decimal("0.01"))
    return tope


def tope_unitario_uyu(producto_id: str) -> Decimal | None:
    """Tope de precio unitario sin IVA en pesos (RF-04), o None si no está definido. Lo usa el agente."""
    guardadas = store.obtener_dict(COLECCION, producto_id) or {}
    if guardadas.get("tope_precio_unitario") is None:
        return None
    tope = Decimal(str(guardadas["tope_precio_unitario"]))
    if guardadas.get("moneda_tope") == "USD":
        tope = (tope * Decimal(str(tipo_cambio()))).quantize(Decimal("0.01"))
    return tope


def precios_vigentes(producto_id: str) -> list[PrecioVigente]:
    """La última cotización leída de cada proveedor para el producto (las dudosas sin confirmar no)."""
    nombres = {p.id: p.nombre for p in pipeline.proveedores().values()}
    ultimo: dict[str, PrecioVigente] = {}
    for cot in store.valores("cotizaciones"):
        if cot.get("estado") == "revisar":
            continue
        for it in cot.get("items", []):
            if it.get("producto_id") != producto_id:
                continue
            ultimo[cot["proveedor_id"]] = PrecioVigente(
                proveedor_id=cot["proveedor_id"],
                proveedor_nombre=nombres.get(cot["proveedor_id"], cot["proveedor_id"]),
                precio_sin_iva_uyu=Decimal(str(it["precio_unitario_sin_iva"])),
                cotizacion_id=cot["id"],
                pedido_id=cot.get("pedido_id", ""),
                validez_dias=cot.get("validez_dias"),
                evidencia=it.get("evidencia") or "",
            )
    return sorted(ultimo.values(), key=lambda p: p.precio_sin_iva_uyu)


def _cierres() -> tuple[datetime, datetime]:
    hoy = inventario.fecha_hoy()
    proximo = datetime(hoy.year, hoy.month, hoy.day, HORA_CIERRE)
    return proximo - timedelta(days=1), proximo


def vista(producto_id: str) -> VistaReglas:
    reglas = actuales(producto_id)
    item = _item(producto_id)
    guardadas = store.obtener_dict(COLECCION, producto_id) or {}
    precios = precios_vigentes(producto_id)
    corte, proximo = _cierres()
    tope = _tope_uyu(reglas)
    return VistaReglas(
        producto_id=producto_id,
        nombre=item.nombre,
        nombre_corto=item.nombre_corto,
        unidad=item.unidad,
        tipo=item.tipo,
        reglas=reglas,
        contexto=Contexto(
            unidad=item.unidad,
            stock_actual=item.stock_actual,
            en_camino=item.en_camino,
            fecha_corte=corte,
            proximo_cierre=proximo,
            reposicion=item.reposicion,
            precios=precios,
            mejor_precio=precios[0] if precios else None,
            tope_unitario_uyu=tope,
            tipo_cambio_usd=tipo_cambio(),
            en_zafra=inventario.en_zafra(reglas.zafra.model_dump() if reglas.zafra else None, inventario.fecha_hoy()),
        ),
        actualizado_por=guardadas.get("actualizado_por"),
        actualizado_en=guardadas.get("actualizado_en"),
    )


def todas() -> list[VistaReglas]:
    return [vista(p) for p in productos_ids()]


# ---------------------------------------------------------------- validación
def _mm_dd_valido(valor: str) -> bool:
    try:
        datetime.strptime(f"2024-{valor}", "%Y-%m-%d")  # 2024: acepta el 29/02
    except (TypeError, ValueError):
        return False
    return len(valor) == 5


def validar(reglas: Reglas) -> dict[str, str]:
    errores: dict[str, str] = {}
    no_negativos = (
        "stock_minimo", "stock_base", "tope_precio_unitario", "tope_automatico_uyu",
        "plazo_entrega_max_dias", "plazo_pago_requerido_dias", "descuento_objetivo_pct", "concesion_maxima_pct",
    )
    for campo in no_negativos:
        valor = getattr(reglas, campo)
        if valor is not None and valor < 0:
            errores[campo] = "No puede ser negativo."
    if "stock_base" not in errores and reglas.stock_base is not None and reglas.stock_base <= reglas.stock_minimo:
        errores["stock_base"] = "El stock base tiene que ser mayor que el stock mínimo."
    for campo in ("descuento_objetivo_pct", "concesion_maxima_pct"):
        valor = getattr(reglas, campo)
        if campo not in errores and valor is not None and valor > 100:
            errores[campo] = "Tiene que estar entre 0 y 100 %."
    if reglas.zafra is not None:
        z = reglas.zafra
        if not _mm_dd_valido(z.inicio) or not _mm_dd_valido(z.fin):
            errores["zafra"] = "Las fechas de la zafra van como día y mes (ej. 01/05 a 31/08)."
        elif z.cantidad <= 0:
            errores["zafra"] = "La cantidad de zafra tiene que ser mayor que cero."
    conocidos = pipeline.proveedores()
    vistos: set[str] = set()
    for p in reglas.proveedores:
        if p.proveedor_id not in conocidos:
            errores["proveedores"] = f"No existe el proveedor '{p.proveedor_id}'."
        elif p.proveedor_id in vistos:
            errores["proveedores"] = f"{conocidos[p.proveedor_id].nombre} está dos veces."
        elif p.prioridad < 1:
            errores["proveedores"] = "La prioridad empieza en 1."
        elif p.minimo_compra is not None and p.minimo_compra < 0:
            errores["proveedores"] = "El mínimo de compra no puede ser negativo."
        elif p.factor_conversion <= 0:
            errores["proveedores"] = "La conversión tiene que ser mayor que cero."
        vistos.add(p.proveedor_id)
    if any(not s.nombre.strip() for s in reglas.sustitutos):
        errores["sustitutos"] = "Cada sustituto necesita un nombre."
    return errores


def _aplicar(reglas: Reglas, campos: dict[str, Any]) -> Reglas:
    datos = reglas.model_dump()
    for campo, valor in campos.items():
        datos[campo] = valor.model_dump() if isinstance(valor, BaseModel) else (
            [v.model_dump() if isinstance(v, BaseModel) else v for v in valor] if isinstance(valor, list) else valor
        )
    if datos.get("proveedores"):
        datos["proveedores"] = sorted(datos["proveedores"], key=lambda p: p["prioridad"])
    return Reglas.model_validate(datos)


# ---------------------------------------------------------------- textos
ETIQUETAS = {
    "compra_automatica": "Compra automática",
    "stock_minimo": "Stock mínimo",
    "stock_base": "Stock base",
    "zafra": "Zafra",
    "tope_precio_unitario": "Tope unitario",
    "moneda_tope": "Moneda del tope",
    "tope_automatico_uyu": "Tope del total por producto",
    "plazo_entrega_max_dias": "Plazo de entrega máximo",
    "plazo_pago_requerido_dias": "Plazo de pago requerido",
    "proveedores": "Proveedores habilitados",
    "sustitutos": "Sustitutos aceptados",
    "descuento_objetivo_pct": "Descuento objetivo",
    "concesion_maxima_pct": "Concesión máxima",
    "cliente_interno": "Cliente interno",
    "tipo_cambio_usd": "Tipo de cambio USD / UYU",
    "fecha_tipo_cambio": "Fecha del tipo de cambio",
    "iva": "Tasa de IVA",
    "vigencia_dias_default": "Vigencia por defecto",
    "moneda_base": "Moneda base",
}


def _u(unidad: str) -> str:
    return "L" if unidad == "l" else "kg" if unidad == "kg" else "u."


def _numero(valor: float | Decimal) -> str:
    return fmt(valor, 0 if float(valor) == int(float(valor)) else 2)


def _dd_mm(mm_dd: str) -> str:
    return f"{mm_dd[3:]}/{mm_dd[:2]}"


def texto(campo: str, valor: Any, reglas: Reglas | None = None, unidad: str = "unidad") -> str:
    if valor is None:
        return "a definir" if campo.endswith("_pct") else "sin definir"
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if campo in ("stock_minimo", "stock_base"):
        return f"{_numero(valor)} {_u(unidad)}"
    if campo == "tope_precio_unitario":
        moneda = reglas.moneda_tope if reglas else "UYU"
        return f"{'USD' if moneda == 'USD' else '$'} {_numero(valor)}"
    if campo == "tope_automatico_uyu":
        return f"$ {_numero(valor)}"
    if campo.endswith("_dias") or campo == "vigencia_dias_default":
        return f"{valor} días"
    if campo.endswith("_pct"):
        return f"{fmt(valor, 1 if float(valor) != int(float(valor)) else 0)} %"
    if campo == "iva":
        return f"{fmt(float(valor) * 100, 0 if float(valor) * 100 == int(float(valor) * 100) else 1)} %"
    if campo == "tipo_cambio_usd":
        return fmt(valor, 2)
    if campo in ("moneda_tope", "moneda_base"):
        return "Pesos (UYU)" if valor == "UYU" else "Dólares (USD)"
    if campo == "cliente_interno":
        return "Ventas" if valor == "ventas" else "Personal"
    if campo == "zafra":
        z = valor if isinstance(valor, dict) else valor.model_dump()
        return f"{_dd_mm(z['inicio'])} a {_dd_mm(z['fin'])} · {_numero(z['cantidad'])} {_u(unidad)}"
    if campo == "proveedores":
        nombres = {p.id: p.nombre for p in pipeline.proveedores().values()}
        lista = sorted((p if isinstance(p, dict) else p.model_dump() for p in valor), key=lambda p: p["prioridad"])
        return ", ".join(f"{p['prioridad']}. {nombres.get(p['proveedor_id'], p['proveedor_id'])}" for p in lista) or "ninguno"
    if campo == "sustitutos":
        return ", ".join((s if isinstance(s, dict) else s.model_dump())["nombre"] for s in valor) or "ninguno"
    return str(valor)


def _json(valor: Any) -> str:
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)


def _diferencias(antes: Reglas, despues: Reglas, unidad: str) -> list[tuple[str, Any, Any, str, str]]:
    a, d = antes.model_dump(mode="json"), despues.model_dump(mode="json")
    return [
        (c, a[c], d[c], texto(c, a[c], antes, unidad), texto(c, d[c], despues, unidad))
        for c in Reglas.model_fields
        if _json(a[c]) != _json(d[c])
    ]


# ---------------------------------------------------------------- escritura
def _ahora() -> datetime:
    return datetime.now().astimezone()


def _motivo(motivo: str | None) -> str:
    motivo = (motivo or "").strip()
    if not motivo:
        raise ReglasError(422, "Contá el motivo del cambio: queda en el historial", {"motivo": "Obligatorio para guardar."})
    return motivo


def cambiar(producto_id: str, cambio: CambioReglas, usuario: Usuario, *, revierte: str | None = None) -> VistaReglas:
    motivo = _motivo(cambio.motivo)
    antes = actuales(producto_id)
    despues = _aplicar(antes, cambio.campos())
    errores = validar(despues)
    if errores:
        raise ReglasError(422, "Hay valores para corregir: " + " ".join(errores.values()), errores)
    unidad = _item(producto_id).unidad
    diferencias = _diferencias(antes, despues, unidad)
    if not diferencias:
        return vista(producto_id)
    nuevos = despues.model_dump(mode="json")
    inv = {c for c, *_ in diferencias if c in DEL_INVENTARIO}
    if inv:
        inventario.cambiar(
            producto_id,
            CambioInventario(
                **{
                    {"compra_automatica": "modo"}.get(c, c): (
                        ("automatico" if nuevos[c] else "manual") if c == "compra_automatica" else nuevos[c]
                    )
                    for c in inv
                }
            ),
        )
    fecha = _ahora()
    store.guardar_dict(
        COLECCION,
        producto_id,
        {
            **(store.obtener_dict(COLECCION, producto_id) or {}),
            **{c: nuevos[c] for c in PROPIOS},
            "actualizado_por": usuario.nombre,
            "actualizado_en": fecha.isoformat(),
        },
    )
    lote = uuid.uuid4().hex[:8]
    for campo, anterior, nuevo, t_ant, t_nuevo in diferencias:
        _registrar(
            CambioRegla(
                id=f"cr_{uuid.uuid4().hex[:10]}",
                tabla="regla_producto",
                registro=producto_id,
                campo=campo,
                etiqueta=ETIQUETAS[campo],
                anterior=anterior,
                nuevo=nuevo,
                texto_anterior=t_ant,
                texto_nuevo=t_nuevo,
                usuario_id=usuario.id,
                usuario=usuario.nombre,
                fecha=fecha,
                motivo=motivo,
                lote=lote,
                revierte=revierte,
            )
        )
    return vista(producto_id)


def _registrar(cambio: CambioRegla) -> None:
    store.guardar_dict(HISTORIAL, cambio.id, cambio.model_dump(mode="json"))


def historial(producto_id: str | None = None, tabla: str = "regla_producto") -> list[CambioRegla]:
    filas = [
        CambioRegla.model_validate(v)
        for v in store.valores(HISTORIAL)
        if v.get("tabla") == tabla and (producto_id is None or v.get("registro") == producto_id)
    ]
    return sorted(filas, key=lambda c: c.fecha, reverse=True)


def revertir(producto_id: str, cambio_id: str, usuario: Usuario, motivo: str | None = None) -> VistaReglas:
    _existe(producto_id)
    datos = store.obtener_dict(HISTORIAL, cambio_id)
    if not datos or datos.get("registro") != producto_id or datos.get("tabla") != "regla_producto":
        raise ReglasError(404, f"No existe el cambio '{cambio_id}' para este producto")
    original = CambioRegla.model_validate(datos)
    if original.revertido_por:
        raise ReglasError(409, "Ese cambio ya se revirtió")
    actual = actuales(producto_id).model_dump(mode="json")[original.campo]
    if _json(actual) != _json(original.nuevo):
        raise ReglasError(
            409,
            f"{original.etiqueta} cambió después de ese registro: revertí primero el cambio más reciente",
            {"actual": actual},
        )
    texto_motivo = (motivo or "").strip() or f"Reversión del cambio del {original.fecha:%d/%m %H:%M} («{original.motivo}»)"
    cambio = CambioReglas.model_validate({original.campo: original.anterior, "motivo": texto_motivo})
    resultado = cambiar(producto_id, cambio, usuario, revierte=cambio_id)
    nuevo = next((c for c in historial(producto_id) if c.revierte == cambio_id), None)
    original.revertido_por = nuevo.id if nuevo else "?"
    _registrar(original)
    return resultado


# ---------------------------------------------------------------- vista previa (§11.4)
def vista_previa(producto_id: str, propuesta: PropuestaReglas) -> VistaPrevia:
    antes = actuales(producto_id)
    try:
        despues = _aplicar(antes, propuesta.campos())
    except ValueError as exc:
        raise ReglasError(422, "Datos de entrada inválidos", str(exc)) from exc
    errores = validar(despues)
    item_actual = _item(producto_id)
    unidad = item_actual.unidad
    u = _u(unidad)
    cambios = [CambioCampo(campo=c, etiqueta=ETIQUETAS[c], anterior=ta, nuevo=tn) for c, _, _, ta, tn in _diferencias(antes, despues, unidad)]
    precios = precios_vigentes(producto_id)
    mejor = precios[0] if precios else None
    tope = _tope_uyu(despues) if "tope_precio_unitario" not in errores else None
    bajo_tope = None if tope is None or mejor is None else mejor.precio_sin_iva_uyu <= tope
    base = dict(cambios=cambios, mejor_precio=mejor, tope_unitario_uyu=tope, bajo_tope=bajo_tope)
    if errores:
        return VistaPrevia(
            valido=False, errores=errores, aplica_cierre=False, dispara_compra=False, cantidad=0, motivo=None,
            aprobacion=None, texto="Corregí los valores marcados para ver el efecto.", evidencia=None, **base,
        )
    _, proximo = _cierres()
    simular = {
        "modo": "automatico" if despues.compra_automatica else "manual",
        "stock_minimo": despues.stock_minimo,
        "tope_automatico_uyu": float(despues.tope_automatico_uyu) if despues.tope_automatico_uyu is not None else None,
        "stock_base": despues.stock_base,
        "zafra": despues.zafra.model_dump() if despues.zafra else None,
    }
    item = _item(producto_id, simular)
    repo = item.reposicion
    precio_txt = _texto_precio(mejor, tope, despues)
    if repo is None:
        return VistaPrevia(
            valido=True, errores={}, aplica_cierre=False, dispara_compra=False, cantidad=0, motivo=None,
            aprobacion="automatica" if despues.compra_automatica else "requiere_aprobacion",
            texto="Este producto se compra cuando alguien lo pide (equipamiento, sin historial de consumo): "
            "el cierre de jornada no dispara compras. " + precio_txt,
            evidencia=None, **base,
        )
    cuando = f"al cierre de hoy ({proximo:%d/%m} {proximo:%H:%M})"
    if repo.cantidad <= 0:
        return VistaPrevia(
            valido=True, errores={}, aplica_cierre=True, dispara_compra=False, cantidad=0, motivo=repo.motivo,
            aprobacion=None, texto=f"Con estos valores, {cuando} no se dispara ninguna compra. " + precio_txt,
            evidencia=repo.evidencia, **base,
        )
    razones: list[str] = []
    if not despues.compra_automatica:
        razones.append("la compra automática está apagada")
    if bajo_tope is False:
        razones.append("el mejor precio supera el tope unitario")
    if despues.tope_automatico_uyu is not None and mejor is not None:
        total = mejor.precio_sin_iva_uyu * Decimal(str(repo.cantidad))
        if total > Decimal(str(despues.tope_automatico_uyu)):
            razones.append(f"el total estimado ($ {fmt(total)}) supera el tope del total")
    por = {
        "zafra": f"zafra del {_dd_mm(despues.zafra.inicio)} al {_dd_mm(despues.zafra.fin)}" if despues.zafra else "zafra",
        "stock_base": f"llegó al mínimo: lleva el stock a {_numero(despues.stock_base or 0)} {u}",
        "pronostico": "pronóstico del próximo mes más el mínimo",
    }[repo.motivo]
    tipo = "una compra automática" if not razones else "un pedido de compra"
    textos = f"Con estos valores, {cuando} se dispara {tipo} de {_numero(repo.cantidad)} {u} ({por}). " + precio_txt
    if razones:
        textos += " Queda pendiente de aprobación: " + "; ".join(razones) + "."
    return VistaPrevia(
        valido=True, errores={}, aplica_cierre=True, dispara_compra=True, cantidad=repo.cantidad, motivo=repo.motivo,
        aprobacion="requiere_aprobacion" if razones else "automatica", texto=textos.strip(), evidencia=repo.evidencia,
        **base,
    )


def _texto_precio(mejor: PrecioVigente | None, tope: Decimal | None, reglas: Reglas) -> str:
    if tope is None:
        return "No hay tope de precio unitario: cualquier precio pasa."
    tope_txt = f"$ {_numero(tope)}" + (
        f" (USD {_numero(reglas.tope_precio_unitario or 0)} × {fmt(tipo_cambio(), 2)})" if reglas.moneda_tope == "USD" else ""
    )
    if mejor is None:
        return f"Todavía no hay cotizaciones para comparar con el tope de {tope_txt}."
    precio = f"$ {_numero(mejor.precio_sin_iva_uyu)} ({mejor.proveedor_nombre})"
    if mejor.precio_sin_iva_uyu <= tope:
        return f"El mejor precio vigente, {precio}, está bajo el tope de {tope_txt}."
    return f"El mejor precio vigente, {precio}, supera el tope de {tope_txt}."


# ---------------------------------------------------------------- configuración (RF-20)
def configuracion() -> Configuracion:
    datos = pipeline.config_vigente()
    return Configuracion(
        tipo_cambio_usd=float(datos["tipo_cambio_usd"]),
        fecha_tipo_cambio=datos.get("fecha_tipo_cambio"),
        iva=float(datos["iva"]),
        vigencia_dias_default=int(datos.get("vigencia_dias_default", VIGENCIA_DEFECTO)),
        moneda_base=datos.get("moneda_base", "UYU"),
        actualizado_por=datos.get("actualizado_por"),
        actualizado_en=datos.get("actualizado_en"),
    )


def _validar_configuracion(c: Configuracion) -> dict[str, str]:
    errores: dict[str, str] = {}
    if c.tipo_cambio_usd <= 0:
        errores["tipo_cambio_usd"] = "El tipo de cambio tiene que ser mayor que cero."
    if not 0 <= c.iva < 1:
        errores["iva"] = "La tasa de IVA va como fracción entre 0 y 1 (22 % = 0,22)."
    if not 1 <= c.vigencia_dias_default <= 365:
        errores["vigencia_dias_default"] = "La vigencia va de 1 a 365 días."
    if c.moneda_base != "UYU":
        errores["moneda_base"] = "Por ahora las comparaciones se hacen en pesos (UYU): la moneda base no se puede cambiar."
    return errores


CAMPOS_CONFIG = ("tipo_cambio_usd", "fecha_tipo_cambio", "iva", "vigencia_dias_default", "moneda_base")


def cambiar_configuracion(cambio: CambioConfiguracion, usuario: Usuario) -> Configuracion:
    antes = configuracion()
    campos = {c: getattr(cambio, c) for c in cambio.model_fields_set if c in CAMPOS_CONFIG}
    if any(v is None for k, v in campos.items() if k != "fecha_tipo_cambio"):
        raise ReglasError(422, "Los parámetros generales no pueden quedar vacíos")
    if "tipo_cambio_usd" in campos and campos["tipo_cambio_usd"] != antes.tipo_cambio_usd and "fecha_tipo_cambio" not in campos:
        campos["fecha_tipo_cambio"] = date.today()
    despues = antes.model_copy(update=campos)
    errores = _validar_configuracion(despues)
    if errores:
        raise ReglasError(422, "Hay valores para corregir: " + " ".join(errores.values()), errores)
    a, d = antes.model_dump(mode="json"), despues.model_dump(mode="json")
    diferencias = [c for c in CAMPOS_CONFIG if _json(a[c]) != _json(d[c])]
    if not diferencias:
        return antes
    fecha = _ahora()
    store.guardar_dict(
        CONFIG,
        CONFIG_ID,
        {**{c: d[c] for c in CAMPOS_CONFIG}, "actualizado_por": usuario.nombre, "actualizado_en": fecha.isoformat()},
    )
    lote = uuid.uuid4().hex[:8]
    motivo = (cambio.motivo or "").strip() or "Cambio de configuración"
    for campo in diferencias:
        _registrar(
            CambioRegla(
                id=f"cr_{uuid.uuid4().hex[:10]}",
                tabla="configuracion",
                registro=CONFIG_ID,
                campo=campo,
                etiqueta=ETIQUETAS[campo],
                anterior=a[campo],
                nuevo=d[campo],
                texto_anterior=_texto_fecha(a[campo]) if campo == "fecha_tipo_cambio" else texto(campo, a[campo]),
                texto_nuevo=_texto_fecha(d[campo]) if campo == "fecha_tipo_cambio" else texto(campo, d[campo]),
                usuario_id=usuario.id,
                usuario=usuario.nombre,
                fecha=fecha,
                motivo=motivo,
                lote=lote,
            )
        )
    return configuracion()


def _texto_fecha(valor: str | None) -> str:
    return "sin fecha" if not valor else f"{valor[8:10]}/{valor[5:7]}/{valor[:4]}"
