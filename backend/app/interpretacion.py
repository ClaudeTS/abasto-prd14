"""Entender el pedido de compra por voz o texto (rol A; agente de compras, docs/AGENTE.md).

`interpretar` devuelve qué productos pidió Lucía, cuántos y para cuándo, con la evidencia literal de
cada uno (prompt `interpretar_pedido`, docs/PROMPTS.md §7). No calcula nada: la reposición la hace
`app/inventario.py` y la propuesta la arma `app/agente.py`. Sin LLM, o si el LLM falla, solo entiende
la frase de la demo (data/inventario_demo.json → pedido_por_voz_demo), como /extraer con los mensajes
fijos; dictada también vale, aunque el dictado escriba "10" donde la frase dice "diez".
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import date
from typing import Literal

from pydantic import BaseModel

from app import config, store
from app.extraccion import evidencia_en_texto
from app.llm import cargar_prompt, pedir_json
from app.models import Producto

log = logging.getLogger("abasto.interpretacion")

DIAS_SEMANA = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
# Sin tildes, como quedan después de _simple: el dictado del navegador escribe los números en cifras.
NUMEROS = {
    palabra: str(n)
    for n, palabra in enumerate(
        "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince "
        "dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro "
        "veinticinco veintiseis veintisiete veintiocho veintinueve treinta".split()
    )
}


class InterpretacionNoDisponible(RuntimeError):
    """Sin LLM y con un texto que no es la frase de la demo."""


# --- Esquema que devuelve el LLM (prompt `interpretar_pedido`) ---


class ItemPedidoLLM(BaseModel):
    producto_id: str | None
    descripcion: str
    cantidad: float | None
    necesario_para: str | None  # AAAA-MM-DD
    evidencia: str


class InterpretacionLLM(BaseModel):
    items: list[ItemPedidoLLM]
    excluir: list[str]
    horizonte_meses: int | None
    evidencia_horizonte: str | None
    dudas: list[str]


# --- Lo que usa el agente ---


class ItemInterpretado(BaseModel):
    producto_id: str
    descripcion: str
    cantidad: float | None
    necesario_para: date | None
    evidencia: str


class Interpretacion(BaseModel):
    origen: Literal["llm", "fijo"]
    items: list[ItemInterpretado]
    no_entendido: list[str]  # lo que pidió y no está en el catálogo
    excluir: list[str]
    horizonte_meses: int | None
    evidencia_horizonte: str | None
    dudas: list[str]


def llm_disponible() -> bool:
    return bool(config.settings.anthropic_api_key) and config.settings.extraccion_mode != "fijo"


def frase_demo() -> str:
    return store.semilla("inventario_demo")["pedido_por_voz_demo"]["texto"]


def es_frase_demo(texto: str) -> bool:
    return _simple(texto) == _simple(frase_demo())


def _fija(*, catalogo: list[Producto], fecha: date) -> Interpretacion:
    """La interpretación guardada de la frase de la demo. La evidencia se busca en la frase escrita:
    en el dictado puede decir "10" donde la evidencia dice "diez"."""
    fija = InterpretacionLLM.model_validate(store.semilla("inventario_demo")["pedido_por_voz_demo"]["interpretacion"])
    return revisar(fija, frase_demo(), catalogo=catalogo, fecha=fecha, origen="fijo")


async def interpretar(texto: str, *, catalogo: list[Producto], fecha: date, negocio: str) -> Interpretacion:
    if not llm_disponible():
        if not es_frase_demo(texto):
            raise InterpretacionNoDisponible(
                "Para entender un pedido libre hace falta el LLM (ANTHROPIC_API_KEY). "
                "Sin eso solo entiendo la frase de la demo."
            )
        return _fija(catalogo=catalogo, fecha=fecha)
    inicio = time.perf_counter()
    try:
        salida = await pedir_json(
            system=cargar_prompt("interpretar_pedido_system"),
            contenido=[
                {
                    "type": "text",
                    "text": cargar_prompt(
                        "interpretar_pedido_user",
                        catalogo="\n".join(f"- {p.id} → {p.nombre} ({p.unidad_canonica})" for p in catalogo),
                        negocio=negocio,
                        fecha=fecha_larga(fecha),
                        texto=texto,
                    ),
                }
            ],
            esquema=InterpretacionLLM,
        )
    except Exception as exc:  # noqa: BLE001 — la frase de la demo tiene respaldo; un pedido libre, no
        if not es_frase_demo(texto):
            raise
        log.warning("interpretar_pedido falló (%s): uso la interpretación fija de la frase de la demo", exc)
        return _fija(catalogo=catalogo, fecha=fecha)
    log.info("pedido interpretado: %d ítems, %.1f s", len(salida.items), time.perf_counter() - inicio)
    return revisar(salida, texto, catalogo=catalogo, fecha=fecha, origen="llm")


def revisar(
    salida: InterpretacionLLM,
    texto: str,
    *,
    catalogo: list[Producto],
    fecha: date,
    origen: Literal["llm", "fijo"],
) -> Interpretacion:
    """Controles que no cambian lo que se pidió: producto del catálogo, una línea por producto,
    fecha válida y no pasada, evidencia que esté en el texto. Lo que no cierra va a `dudas`."""
    nombres = {p.id: p.nombre for p in catalogo}
    items: list[ItemInterpretado] = []
    no_entendido: list[str] = []
    dudas = list(salida.dudas)
    for item in salida.items:
        if item.producto_id not in nombres:
            no_entendido.append(item.descripcion)
            continue
        nombre = nombres[item.producto_id]
        if any(i.producto_id == item.producto_id for i in items):
            dudas.append(f"Nombraste {nombre} dos veces: tomé la primera.")
            continue
        necesario = _fecha(item.necesario_para)
        if item.necesario_para and necesario is None:
            dudas.append(f"No entendí la fecha de {nombre} ({item.necesario_para}).")
        elif necesario is not None and necesario < fecha:
            dudas.append(f"La fecha de {nombre} ({necesario:%d/%m}) ya pasó.")
            necesario = None
        if not evidencia_en_texto(item.evidencia, texto):
            dudas.append(f"No encontré «{item.evidencia}» en lo que dijiste: revisá {nombre}.")
        items.append(
            ItemInterpretado(
                producto_id=item.producto_id,
                descripcion=item.descripcion,
                cantidad=item.cantidad if item.cantidad and item.cantidad > 0 else None,
                necesario_para=necesario,
                evidencia=item.evidencia,
            )
        )
    horizonte = salida.horizonte_meses
    if horizonte is not None and not 1 <= horizonte <= 6:
        dudas.append("El horizonte va de 1 a 6 meses: uso el de siempre.")
        horizonte = None
    return Interpretacion(
        origen=origen,
        items=items,
        no_entendido=no_entendido,
        excluir=[p for p in dict.fromkeys(salida.excluir) if p in nombres],
        horizonte_meses=horizonte,
        evidencia_horizonte=salida.evidencia_horizonte if horizonte else None,
        dudas=dudas,
    )


def fecha_larga(fecha: date) -> str:
    return f"{DIAS_SEMANA[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]} de {fecha.year} ({fecha.isoformat()})"


def _fecha(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def _simple(texto: str) -> str:
    """Para comparar con la frase de la demo sin importar tildes, mayúsculas, puntuación ni si los
    números están en letras o en cifras."""
    t = unicodedata.normalize("NFKD", texto.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(NUMEROS.get(p, p) for p in re.findall(r"\w+", t))
