"""Reglas post-LLM (rol C): moneda, IVA y unidades. ARQUITECTURA §5 paso 4 y AGENTS §7.

El extractor (rol A) devuelve los números tal como vinieron. Acá se convierten en código, nunca
en el prompt, y cada conversión queda escrita en `conversion_aplicada` para mostrarla en la UI.
"""

from __future__ import annotations

import unicodedata
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.models import Cotizacion, ItemCotizado

CENTAVO = Decimal("0.01")
UMBRAL_CONFIANZA = 0.6
# Dudas que cambian un precio: con estas la cotización no entra al solver hasta que se confirme.
DUDAS_QUE_BLOQUEAN = ("iva", "moneda", "unidad:", "precio:")

_UNIDADES_BASE = {
    "unidad": ("unidad", 1),
    "u": ("unidad", 1),
    "un": ("unidad", 1),
    "unid": ("unidad", 1),
    "c/u": ("unidad", 1),
    "xunidad": ("unidad", 1),
    "porunidad": ("unidad", 1),
    "cadauno": ("unidad", 1),
    "l": ("l", 1),
    "lt": ("l", 1),
    "litro": ("l", 1),
    "kg": ("kg", 1),
    "kilo": ("kg", 1),
}


# ---------------------------------------------------------------- formato
def fmt(valor: Decimal | float | int, decimales: int = 0) -> str:
    """Formato uruguayo: 31.200 · 893,44."""
    d = Decimal(str(valor)).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    entero, _, frac = f"{d:,.{decimales}f}".partition(".")
    entero = entero.replace(",", ".")
    return f"{entero},{frac}" if decimales else entero


def _clave_unidad(texto: str) -> str:
    """Normaliza 'Bidón de 5 L' y 'bidon 5L' a la misma clave: 'bidon5l'."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    for largo, corto in (("litros", "l"), ("litro", "l"), ("lts", "l"), ("kilos", "kg")):
        t = t.replace(largo, corto)
    palabras = [p for p in t.replace(".", " ").split() if p not in ("de", "del")]
    return "".join(palabras)


def resolver_unidad(
    unidad_original: str, unidad_canonica: str, conversiones: dict[str, Any]
) -> tuple[Decimal, str | None]:
    """Devuelve (factor, texto de conversión) o (1, None) si ya es canónica.

    Lanza ValueError si la unidad no se puede llevar a la canónica del producto.
    """
    clave = _clave_unidad(unidad_original)
    if clave in _UNIDADES_BASE:
        canonica, factor = _UNIDADES_BASE[clave]
        if canonica == unidad_canonica:
            return Decimal(factor), None
    for nombre, conv in conversiones.items():
        if _clave_unidad(nombre) == clave and conv["a"] == unidad_canonica:
            factor = Decimal(str(conv["factor"]))
            return factor, f"{nombre} → {fmt(factor)} {unidad_canonica}"
    raise ValueError(f"unidad '{unidad_original}' sin conversión a {unidad_canonica}")


# ---------------------------------------------------------------- normalización
def normalizar_item(
    crudo: dict[str, Any],
    unidad_canonica: str,
    *,
    tipo_cambio_usd: float,
    iva: float,
    conversiones: dict[str, Any],
    incluye_iva_forzado: bool | None = None,
) -> tuple[ItemCotizado, list[str]]:
    """Convierte un ítem crudo del extractor. Devuelve el ítem y las dudas que generó."""
    dudas: list[str] = []
    precio = Decimal(str(crudo["precio"]))
    moneda = crudo.get("moneda") or "UYU"
    incluye_iva = bool(crudo.get("incluye_iva_original", False))
    if incluye_iva_forzado is not None:
        incluye_iva = incluye_iva_forzado
    unidad_original = crudo.get("unidad_original") or unidad_canonica
    pasos: list[str] = []

    valor = precio
    if moneda == "USD":
        tc = Decimal(str(tipo_cambio_usd))
        valor = precio * tc
        pasos.append(
            f"USD {fmt(precio, 2 if precio % 1 else 0)} × {fmt(tc, 2)} = UYU {fmt(valor)}"
        )
    if incluye_iva:
        divisor = Decimal(1) + Decimal(str(iva))
        antes = valor
        valor = valor / divisor
        pasos.append(f"con IVA: {fmt(antes)} / {fmt(divisor, 2)} = {fmt(valor, 2)}")
    try:
        factor, texto_unidad = resolver_unidad(unidad_original, unidad_canonica, conversiones)
    except ValueError:
        factor, texto_unidad = Decimal(1), None
        dudas.append(f"unidad:{crudo.get('producto_id')}")
    if factor != 1:
        antes = valor
        valor = valor / factor
        pasos.append(f"{texto_unidad}: {fmt(antes, 2)} / {fmt(factor)} = {fmt(valor, 2)}")

    minima = crudo.get("cantidad_minima")
    item = ItemCotizado(
        producto_id=crudo["producto_id"],
        descripcion_original=crudo.get("descripcion_original"),
        precio_unitario_sin_iva=valor.quantize(CENTAVO, rounding=ROUND_HALF_UP),
        precio_original=precio,
        moneda_original=moneda,
        incluye_iva_original=incluye_iva,
        unidad_original=unidad_original,
        conversion_aplicada=" · ".join(pasos) or None,
        cantidad_minima=float(Decimal(str(minima)) * factor) if minima is not None else None,
        evidencia=crudo.get("evidencia") or "",
    )
    if not item.evidencia:
        dudas.append(f"precio:{item.producto_id}")  # AGENTS §6.4: nunca un precio sin fuente
    return item, dudas


def requiere_revision(confianza: float, campos_dudosos: list[str]) -> bool:
    return confianza < UMBRAL_CONFIANZA or any(
        d == p or d.startswith(p) for d in campos_dudosos for p in DUDAS_QUE_BLOQUEAN
    )


def normalizar_cotizacion(
    crudo: dict[str, Any],
    *,
    cotizacion_id: str,
    pedido_id: str,
    mensaje_id: str,
    proveedor_id: str,
    catalogo: dict[str, str],  # producto_id -> unidad canónica
    conversiones: dict[str, Any],
    tipo_cambio_usd: float,
    iva: float,
    incluye_iva_forzado: bool | None = None,
    confirmada: bool = False,
) -> Cotizacion:
    """Aplica las reglas post-LLM a la salida cruda del prompt `extractor`."""
    items: list[ItemCotizado] = []
    sin_mapear: list[str] = []
    dudas = list(crudo.get("campos_dudosos") or [])
    if incluye_iva_forzado is not None:
        dudas = [d for d in dudas if d != "iva"]

    for item_crudo in crudo.get("items") or []:
        producto_id = item_crudo.get("producto_id")
        if producto_id not in catalogo or item_crudo.get("precio") is None:
            sin_mapear.append(item_crudo.get("descripcion_original") or str(producto_id))
            continue
        item, dudas_item = normalizar_item(
            item_crudo,
            catalogo[producto_id],
            tipo_cambio_usd=tipo_cambio_usd,
            iva=iva,
            conversiones=conversiones,
            incluye_iva_forzado=incluye_iva_forzado,
        )
        items.append(item)
        dudas.extend(d for d in dudas_item if d not in dudas)

    confianza = float(crudo.get("confianza") or 0)
    if confirmada or incluye_iva_forzado is not None:
        estado = "confirmada"
        confianza = 1.0  # lo confirmó una persona: deja de ser una lectura dudosa
    elif requiere_revision(confianza, dudas):
        estado = "revisar"
    else:
        estado = "valida"

    lead = crudo.get("lead_time_dias")
    if lead is None:
        dudas.append("lead_time")
    minimo_total = crudo.get("pedido_minimo_total")
    return Cotizacion(
        id=cotizacion_id,
        pedido_id=pedido_id,
        mensaje_id=mensaje_id,
        proveedor_id=proveedor_id,
        items=items,
        costo_envio=Decimal(str(crudo.get("costo_envio") or 0)),
        pedido_minimo_total=Decimal(str(minimo_total)) if minimo_total is not None else None,
        plazo_pago_dias=int(crudo.get("plazo_pago_dias") or 0),
        lead_time_dias=int(lead or 0),
        validez_dias=crudo.get("validez_dias"),
        observaciones=list(crudo.get("observaciones") or []),
        confianza=confianza,
        campos_dudosos=dudas,
        estado=estado,
        items_sin_mapear=sin_mapear,
        tipo_cambio_usd=tipo_cambio_usd,
    )
