"""Orquestación de la Capa 1 (rol C): mensaje crudo → texto → extracción → reglas → Cotizacion.

La extracción con LLM es del rol A (`app/extraccion.py`, función `extraer_crudo`). Este módulo la
llama si existe y hay API key; si no, usa `data/extracciones_fijas.json` para que el flujo de punta
a punta funcione desde la hora 1 y la demo no dependa de la API. Ver docs/CONTRATO_BACKEND.md.
"""

from __future__ import annotations

import importlib
import logging
import uuid
from pathlib import Path
from typing import Any

from app import config, store
from app.models import Cotizacion, MensajeCrudo, Producto, Proveedor
from app.normalizacion import normalizar_cotizacion

log = logging.getLogger("abasto.pipeline")
MIN_CARACTERES_PDF = 50  # ARQUITECTURA §5: menos que esto → visión


class ExtraccionNoDisponible(RuntimeError):
    """No hay extractor con LLM ni fixture para este mensaje."""


# ---------------------------------------------------------------- datos de la demo
def datos_pedido() -> dict[str, Any]:
    return store.semilla("pedido_demo")


def catalogo() -> list[Producto]:
    return [Producto.model_validate(p) for p in datos_pedido()["catalogo"]]


def proveedores() -> dict[str, Proveedor]:
    return {
        p["publico"]["id"]: Proveedor.model_validate(p["publico"])
        for p in store.semilla("proveedores_sim")["proveedores"]
    }


def perfil_privado(proveedor_id: str) -> dict[str, Any]:
    for p in store.semilla("proveedores_sim")["proveedores"]:
        if p["publico"]["id"] == proveedor_id:
            return p["privado"]
    raise KeyError(proveedor_id)


# ---------------------------------------------------------------- texto de entrada
def obtener_texto(mensaje: MensajeCrudo) -> tuple[str | None, Path | None]:
    """Devuelve (texto, imagen) para el extractor según el canal."""
    archivo = config.settings.archivos_dir / mensaje.archivo if mensaje.archivo else None
    if mensaje.canal == "pdf" and archivo:
        from app.archivos import extraer_texto_pdf

        texto = extraer_texto_pdf(archivo)
        if len(texto.strip()) >= MIN_CARACTERES_PDF:
            return texto, None
        return None, archivo  # PDF escaneado: va a visión (rol A rasteriza o manda el PDF)
    if mensaje.canal == "foto":
        return None, archivo
    return mensaje.contenido_texto, None  # whatsapp_texto y whatsapp_audio (transcripción)


# ---------------------------------------------------------------- extracción
def _extractor_llm():
    """La función del rol A, si ya existe. None si todavía no."""
    try:
        modulo = importlib.import_module("app.extraccion")
    except ImportError:
        return None
    return getattr(modulo, "extraer_crudo", None)


def _crudo_fijo(proveedor_id: str) -> dict[str, Any] | None:
    return store.semilla("extracciones_fijas")["extracciones"].get(proveedor_id)


def modo_extraccion() -> str:
    """'llm' si se va a usar el extractor del rol A, 'fijo' si los fixtures."""
    modo = config.settings.extraccion_mode
    if modo == "fijo":
        return "fijo"
    disponible = _extractor_llm() is not None and bool(config.settings.anthropic_api_key)
    if modo == "llm" or disponible:
        return "llm" if disponible else "no_disponible"
    return "fijo"


async def extraer_crudo(mensaje: MensajeCrudo) -> tuple[dict[str, Any], str]:
    """Devuelve (salida cruda del extractor, origen 'llm'|'cache'|'fijo')."""
    modo = modo_extraccion()
    # /extraer (pedido "pruebas") no cachea: A prueba distintos textos para el mismo proveedor.
    clave_cache = (
        f"extraccion_{mensaje.pedido_id}_{mensaje.proveedor_id}"
        if mensaje.pedido_id != "pruebas"
        else None
    )
    if modo == "llm":
        if clave_cache and (en_cache := store.cache_leer(clave_cache)) is not None:
            return en_cache, "cache"
        texto, imagen = obtener_texto(mensaje)
        try:
            crudo = await _extractor_llm()(  # type: ignore[misc]
                texto=texto,
                imagen=imagen,
                canal=mensaje.canal,
                proveedor=proveedores()[mensaje.proveedor_id],
                catalogo=catalogo(),
            )
        except Exception as exc:  # noqa: BLE001 — en "auto" caemos al fixture, no rompemos la demo
            if config.settings.extraccion_mode == "llm" or not _crudo_fijo(mensaje.proveedor_id):
                raise
            log.warning("Extracción LLM falló para %s (%s); uso fixture", mensaje.id, exc)
            return _crudo_fijo(mensaje.proveedor_id), "fijo"  # type: ignore[return-value]
        if clave_cache:
            store.cache_guardar(clave_cache, crudo)
        return crudo, "llm"
    if modo == "no_disponible":
        raise ExtraccionNoDisponible(
            "EXTRACCION_MODE=llm pero falta la Capa 1 (app/extraccion.py) o ANTHROPIC_API_KEY"
        )
    crudo = _crudo_fijo(mensaje.proveedor_id)
    if crudo is None:
        raise ExtraccionNoDisponible(
            f"No hay extracción fija para '{mensaje.proveedor_id}' y la Capa 1 con LLM no está activa"
        )
    return crudo, "fijo"


def _normalizar(
    crudo: dict[str, Any],
    cotizacion_id: str,
    mensaje: MensajeCrudo,
    iva_forzado: bool | None,
    confirmada: bool = False,
) -> Cotizacion:
    datos = datos_pedido()
    return normalizar_cotizacion(
        crudo,
        cotizacion_id=cotizacion_id,
        pedido_id=mensaje.pedido_id,
        mensaje_id=mensaje.id,
        proveedor_id=mensaje.proveedor_id,
        catalogo={p.id: p.unidad_canonica for p in catalogo()},
        conversiones=datos["conversiones"],
        tipo_cambio_usd=float(datos["config"]["tipo_cambio_usd"]),
        iva=float(datos["config"]["iva"]),
        incluye_iva_forzado=iva_forzado,
        confirmada=confirmada,
    )


async def procesar_mensaje(mensaje: MensajeCrudo) -> Cotizacion:
    """Extrae, normaliza y guarda. Actualiza el estado del mensaje (para el feed)."""
    mensaje.estado = "leyendo"
    store.guardar("mensajes", mensaje)
    try:
        crudo, origen = await extraer_crudo(mensaje)
        cotizacion_id = f"cot_{mensaje.proveedor_id}_{uuid.uuid4().hex[:6]}"
        cotizacion = _normalizar(crudo, cotizacion_id, mensaje, None)
    except Exception as exc:  # noqa: BLE001 — el error se muestra en el feed, nunca en silencio
        log.exception("Falló la extracción de %s", mensaje.id)
        mensaje.estado = "error"
        mensaje.error = str(exc)
        store.guardar("mensajes", mensaje)
        raise
    store.guardar_dict(
        "extracciones", cotizacion.id, {"crudo": crudo, "origen": origen, "mensaje_id": mensaje.id}
    )
    store.guardar("cotizaciones", cotizacion)
    mensaje.estado = "extraido"
    mensaje.cotizacion_id = cotizacion.id
    store.guardar("mensajes", mensaje)
    log.info("Cotización %s (%s, origen %s)", cotizacion.id, cotizacion.estado, origen)
    return cotizacion


def confirmar(cotizacion: Cotizacion, incluye_iva: bool | None) -> Cotizacion:
    """Lucía confirma las dudas: se re-normaliza desde la salida cruda guardada."""
    registro = store.obtener_dict("extracciones", cotizacion.id)
    mensaje = store.obtener("mensajes", cotizacion.mensaje_id, MensajeCrudo)
    if registro is None or mensaje is None:
        raise KeyError(cotizacion.id)
    # Sin incluye_iva se confirma la lectura tal cual: cada ítem conserva el IVA que leyó el
    # extractor (forzar uno solo cambiaba precios en cotizaciones que mezclan ítems con y sin IVA).
    nueva = _normalizar(registro["crudo"], cotizacion.id, mensaje, incluye_iva, confirmada=True)
    store.guardar("cotizaciones", nueva)
    return nueva
