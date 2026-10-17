"""Capa 1 — Percepción (rol A): mensaje de un proveedor → salida cruda del prompt `extractor`.

Contrato con C (docs/CONTRATO_BACKEND.md §"Para A"): `extraer_crudo` devuelve los números tal como
vinieron en el mensaje. Moneda, IVA y unidades las convierte C en `app/normalizacion.py`; acá solo
se lee, se mapea al catálogo y se marca lo dudoso. Referencia de la salida: data/extracciones_fijas.json.
"""

from __future__ import annotations

import base64
import html
import logging
import re
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app import store
from app.llm import cargar_prompt, pedir_json
from app.models import Producto, Proveedor

log = logging.getLogger("abasto.extraccion")

TIPOS_IMAGEN = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class EntradaInvalida(Exception):
    """El mensaje no trae lo necesario para extraer (texto o archivo legible)."""


# --- Esquema que devuelve el LLM (prompt `extractor`, docs/PROMPTS.md §1) ---


class ItemExtraido(BaseModel):
    producto_id: str | None
    descripcion_original: str
    precio: float | None
    moneda: Literal["UYU", "USD"]
    unidad_original: str
    incluye_iva_original: bool
    cantidad_minima: float | None
    evidencia: str


class ExtraccionLLM(BaseModel):
    items: list[ItemExtraido]
    costo_envio: float | None
    pedido_minimo_total: float | None
    plazo_pago_dias: int | None
    lead_time_dias: int | None
    validez_dias: int | None
    observaciones: list[str]
    confianza: float
    campos_dudosos: list[str]


async def extraer_crudo(
    *,
    texto: str | None,
    imagen: Path | None,
    canal: str,
    proveedor: Proveedor,
    catalogo: list[Producto],
) -> dict:
    """Lee la cotización con el LLM. `texto` viene listo (WhatsApp, audio transcripto o texto
    del PDF); si es None, `imagen` es la foto o el PDF escaneado y va a visión."""
    inicio = time.perf_counter()
    # pdfplumber parte las filas de la tabla en líneas; el HTML deja cada fila en una.
    tabla = canal == "pdf" and not _es_html(texto or "")
    contenido, texto_fuente = armar_contenido(
        texto=texto, imagen=imagen, canal=canal, proveedor=proveedor, catalogo=catalogo
    )
    extraccion = await pedir_json(
        system=cargar_prompt("extractor_system"),
        contenido=contenido,
        esquema=ExtraccionLLM,
    )
    crudo = revisar(extraccion, texto_fuente, tabla=tabla)
    log.info(
        "extracción %s (%s): %d ítems, confianza %.2f, %.1f s",
        proveedor.id,
        canal,
        len(crudo["items"]),
        crudo["confianza"],
        time.perf_counter() - inicio,
    )
    return crudo


def revisar(
    extraccion: ExtraccionLLM, texto_fuente: str | None, *, tabla: bool = False
) -> dict:
    """Controles que no convierten nada: confianza en [0, 1] y evidencia que esté en el mensaje.

    Una evidencia sin letras ni números ("", "...", comillas) queda vacía, así C marca
    `precio:<producto>` y la cotización va a revisar. Una que no aparece en el texto se marca `evidencia:<producto>` (la UI la muestra; no
    bloquea, porque puede ser una paráfrasis). Con una foto o un PDF escaneado no hay texto
    contra el cual comparar.
    """
    crudo = extraccion.model_dump(mode="json")
    crudo["confianza"] = min(max(extraccion.confianza, 0.0), 1.0)
    dudosos = list(extraccion.campos_dudosos)
    for item, item_crudo in zip(extraccion.items, crudo["items"]):
        if not re.search(r"\w", item.evidencia):
            item_crudo["evidencia"] = ""
        elif (
            texto_fuente is not None
            and item.producto_id
            and not evidencia_en_texto(item.evidencia, texto_fuente, tabla=tabla)
        ):
            dudosos.append(f"evidencia:{item.producto_id}")
    crudo["campos_dudosos"] = list(dict.fromkeys(dudosos))
    return crudo


# --- Armado del pedido al LLM según el canal ---


def armar_contenido(
    *,
    texto: str | None,
    imagen: Path | None,
    canal: str,
    proveedor: Proveedor,
    catalogo: list[Producto],
) -> tuple[list[dict], str | None]:
    """Bloques para el LLM y el texto fuente (None si el LLM lee un archivo)."""
    adjunto: dict | None = None
    if texto is not None and texto.strip():
        if _es_html(
            texto
        ):  # /extraer con canal pdf puede traer el HTML del presupuesto
            texto = html_a_texto(texto)
        mensaje = texto
    elif imagen is not None:
        adjunto = _bloque_archivo(Path(imagen))
        texto = None
        mensaje = (
            "(el PDF adjunto es el presupuesto)"
            if adjunto["type"] == "document"
            else "(la imagen adjunta es el presupuesto)"
        )
    else:
        raise EntradaInvalida(f"El mensaje ({canal}) no trae texto ni archivo.")

    user = cargar_prompt(
        "extractor_user",
        catalogo=_catalogo_para_prompt(catalogo),
        unidades=_unidades_para_prompt(),
        proveedor_nombre=proveedor.nombre,
        rubro=proveedor.rubro,
        canal=canal,
        mensaje=mensaje,
    )
    bloques = ([adjunto] if adjunto else []) + [{"type": "text", "text": user}]
    return bloques, texto


def _catalogo_para_prompt(catalogo: list[Producto]) -> str:
    return "\n".join(f"- {p.id} → {p.nombre} ({p.unidad_canonica})" for p in catalogo)


def _unidades_para_prompt() -> str:
    """Las presentaciones que C sabe convertir (pedido_demo.json → conversiones)."""
    conversiones = store.semilla("pedido_demo").get("conversiones", {})
    return "\n".join(f"- {nombre}" for nombre in conversiones) or "- (ninguna)"


def _bloque_archivo(ruta: Path) -> dict:
    if not ruta.is_file():
        raise EntradaInvalida(f"No existe el archivo {ruta.name}.")
    datos = base64.standard_b64encode(ruta.read_bytes()).decode()
    sufijo = ruta.suffix.lower()
    if (
        sufijo == ".pdf"
    ):  # PDF escaneado: la API lo lee como documento (texto + páginas)
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": datos,
            },
        }
    tipo = TIPOS_IMAGEN.get(sufijo)
    if tipo is None:
        raise EntradaInvalida(
            f"Formato de archivo no soportado: {ruta.suffix or ruta.name}"
        )
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": tipo, "data": datos},
    }


def _es_html(texto: str) -> bool:
    return bool(re.search(r"<(h\d|p|table|tr|td|th|div|br)\b", texto, flags=re.I))


def html_a_texto(contenido: str) -> str:
    """HTML simple de presupuesto (h2, p, table) → texto plano con filas en líneas."""
    texto = re.sub(r"</(p|h\d|tr|div)>|<br\s*/?>", "\n", contenido, flags=re.I)
    texto = re.sub(r"</t[dh]>", " | ", texto, flags=re.I)
    texto = html.unescape(re.sub(r"<[^>]+>", "", texto))
    lineas = (re.sub(r"[ \t]+", " ", linea).strip(" |") for linea in texto.splitlines())
    return "\n".join(linea for linea in lineas if linea)


# --- Evidencia ---


def evidencia_en_texto(evidencia: str, texto: str, *, tabla: bool = False) -> bool:
    """Cada fragmento de la evidencia (separados por "...") está en el mensaje, sin importar
    mayúsculas, comillas ni espacios. Si el texto es una tabla de pdfplumber (`tabla`), que parte
    cada fila en varias líneas, alcanza con que las palabras del fragmento estén en el tramo de
    una sola fila (ver `_tramos`)."""
    fuente = _comparable(texto)
    fragmentos = [_comparable(f) for f in re.split(r"\.\.\.|…", evidencia)]
    fragmentos = [f for f in fragmentos if f]
    tramos = _tramos(texto) if tabla else []
    return bool(fragmentos) and all(
        f in fuente or any(set(_palabras(f)) <= t for t in tramos) for f in fragmentos
    )


# Un monto con decimales (780,00 · 7.800,00 · 95.00) o con punto de miles (10.900).
_MONTO = re.compile(r"\d[.,]\d{2}(?!\d)|\d{1,3}(?:\.\d{3})+(?![\d,])")


def _tramos(texto: str) -> list[set[str]]:
    """Las palabras de cada fila de la tabla y de la descripción partida a su alrededor.

    pdfplumber deja los montos de una fila en una línea y reparte la descripción arriba y abajo.
    Cada tramo va desde la línea que sigue a la fila anterior hasta la que precede a la siguiente
    (en los extremos, hasta 4 líneas), así que trae los montos de una sola fila. Con menos de dos
    filas no hay nada que separar: se compara el texto literal.
    """
    lineas = [linea for linea in map(_comparable, texto.splitlines()) if linea]
    filas = [i for i, linea in enumerate(lineas) if _MONTO.search(linea)]
    if len(filas) < 2:
        return []
    tramos = []
    for k, fila in enumerate(filas):
        inicio = filas[k - 1] + 1 if k else max(fila - 4, 0)
        fin = filas[k + 1] if k + 1 < len(filas) else fila + 5
        tramos.append(set(_palabras(" ".join(lineas[inicio:fin]))))
    return tramos


def _comparable(texto: str) -> str:
    sin_comillas = re.sub(r"[\"“”'‘’]", "", texto.casefold())
    return re.sub(r"\s+", " ", sin_comillas.replace("|", " ")).strip()


def _palabras(texto: str) -> list[str]:
    return [p for p in (p.strip(".,;:()[]") for p in texto.split()) if p]
