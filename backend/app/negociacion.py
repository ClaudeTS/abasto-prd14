"""Capa 5 — Negociación ensayada contra el gemelo del proveedor (rol A, ARQUITECTURA.md §7).

Contrato con C: `ensayar(contexto)` recibe el `ContextoNegociacion` que arma
`integracion_a.construir_contexto` (cantidades del plan, mejor alternativa real por ítem y el perfil
privado del gemelo) y devuelve las 3 estrategias, la elegida y el mensaje propuesto.

Por cada estrategia (competencia, volumen, plazo) se corren 2 simulaciones de 3 rondas: Abasto
(prompt `negociador`) contra el gemelo (prompt `proveedor_gemelo`), que conoce su piso y su perfil
de concesión. Al final el gemelo da su oferta en JSON (`cierre_gemelo`). Las 6 corridas van en
paralelo. El LLM solo conversa: la concesión y el respeto del piso se calculan acá (C recalcula la
ganancia con la concesión). Nada se envía: el mensaje espera la aprobación de Compras.

"competencia" solo se ensaya si otro proveedor cotiza más barato algún ítem. Una estrategia que no
se ensaya, o cuyas corridas fallan todas, vuelve igual (sin transcripción, 0 % y riesgo alto, al
final de la lista): la UI muestra las 3 y nunca se elige. Las corridas que no terminan en
PLAZO_CORRIDAS_SEGUNDOS se descartan, así la respuesta llega antes de los 90 s de C.

Errores, según cómo los trata C en `main.negociar`: si se vence el plazo, TimeoutError (504 y el
pedido vuelve a "optimizado"); si el LLM falla, NegociacionFallida, que es un CapaNoDisponible
(501 con el mensaje legible, también vuelve a "optimizado").
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean
from typing import Literal

from pydantic import BaseModel

from app import pipeline
from app.integracion_a import CapaNoDisponible
from app.llm import LLMError, cargar_prompt, pedir_json, pedir_texto
from app.models import ContextoNegociacion
from app.normalizacion import CENTAVO, fmt

log = logging.getLogger("abasto.negociacion")

ESTRATEGIAS = ("competencia", "volumen", "plazo")
DESCRIPCIONES = {
    "competencia": "Mencionar la mejor cotización alternativa, con nombre y precio reales.",
    "volumen": "Comprometer compras futuras a cambio de mejor precio.",
    "plazo": "Ofrecer pago contado o anticipado a cambio de descuento.",
}
NO_ENSAYADA = "No se pudo ensayar"
CORRIDAS = 2
RONDAS = 3
LIMITE_SEGUNDOS = 40  # objetivo de ARQUITECTURA §7 para toda la negociación
PLAZO_CORRIDAS_SEGUNDOS = 55  # las corridas que no terminen se descartan
PLAZO_TOTAL_SEGUNDOS = 85  # C corta POST /negociar a los 90 s
# Productos del catálogo demo que se compran al equipar puestos; el resto es compra mensual.
EQUIPAMIENTO = {"notebook", "silla"}
POR_UNIDAD = {"unidad": "por unidad", "l": "por litro", "kg": "por kg"}


class NegociacionFallida(CapaNoDisponible, LLMError):
    """El LLM falló. Es un CapaNoDisponible para que C responda 501 con este mensaje y vuelva el
    pedido a "optimizado"; un LLMError suelto le llega como 500 genérico y sin CORS."""


# --- Esquema del cierre del gemelo (prompt `cierre_gemelo`, docs/PROMPTS.md §3) ---


class PrecioFinal(BaseModel):
    producto_id: str
    precio: float


class CierreGemelo(BaseModel):
    acepta_negociar: bool
    precios_finales: list[PrecioFinal]
    condicion: str | None
    animo: Literal["cordial", "neutral", "molesto"]


@dataclass(frozen=True)
class ItemNegociado:
    producto_id: str
    nombre: str
    unidad: str
    cantidad: Decimal
    precio: Decimal  # cotizado, sin IVA, por unidad canónica
    alternativa: (
        str | None
    )  # "Mueblería Rivera cotiza $ 9.800 … pero exige mínimo 20 …"


@dataclass(frozen=True)
class Corrida:
    estrategia: str
    transcripcion: list[dict]
    cierre: CierreGemelo
    precios_finales: dict[str, Decimal]
    ganancia: Decimal
    concesion_pct: float


@dataclass(frozen=True)
class Estrategia:
    nombre: str
    descripcion: str
    transcripcion: list[dict]
    concesion_obtenida_pct: float
    riesgo: Literal["bajo", "medio", "alto"]

    def como_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "transcripcion": self.transcripcion,
            "concesion_obtenida_pct": self.concesion_obtenida_pct,
            "riesgo": self.riesgo,
        }


async def ensayar(contexto: ContextoNegociacion) -> dict:
    """Ensaya las 3 estrategias contra el gemelo y propone el mensaje de la mejor."""
    try:
        return await _ensayar(contexto)
    except LLMError as e:
        raise NegociacionFallida(str(e)) from e


async def _ensayar(contexto: ContextoNegociacion) -> dict:
    inicio = time.perf_counter()
    items = items_negociados(contexto)
    if not items:
        raise ValueError(f"El plan no le compra nada a {contexto.proveedor.nombre}.")
    ensayadas = [
        e
        for e in ESTRATEGIAS
        if e != "competencia" or any(i.alternativa for i in items)
    ]
    corridas, errores = await correr_todas(contexto, items, ensayadas)
    if not corridas:
        # Un error del LLM dice más que un plazo vencido; si todas se cortaron, es TimeoutError.
        raise next((e for e in errores if isinstance(e, LLMError)), errores[0])

    estrategias = [
        resumir(nombre, [c for c in corridas if c.estrategia == nombre])
        for nombre in ensayadas
        if any(c.estrategia == nombre for c in corridas)
    ]
    # Al final y con riesgo alto: si todas empatan en 0, C elige la primera de la lista.
    for nombre in ESTRATEGIAS:
        if all(e.nombre != nombre for e in estrategias):
            estrategias.append(
                SIN_COMPETENCIA if nombre not in ensayadas else sin_corridas(nombre)
            )
    elegida = elegir(estrategias, contexto.valor_en_juego_uyu)
    restante = PLAZO_TOTAL_SEGUNDOS - (time.perf_counter() - inicio)
    mensaje = await asyncio.wait_for(
        redactar_mensaje(contexto, items, elegida), max(restante, 1.0)
    )
    duracion = time.perf_counter() - inicio
    log.log(
        logging.WARNING if duracion > LIMITE_SEGUNDOS else logging.INFO,
        "Negociación con %s: %.1f s · elegida %s · %d/%d corridas",
        contexto.proveedor.id,
        duracion,
        elegida.nombre,
        len(corridas),
        len(corridas) + len(errores),
    )
    return {
        "estrategias": [e.como_dict() for e in estrategias],
        "elegida": elegida.nombre,
        "mensaje_propuesto": mensaje,
    }


def sin_corridas(
    nombre: str,
    descripcion: str = f"{NO_ENSAYADA}: el LLM falló o no respondió a tiempo; probá negociar de nuevo.",
) -> Estrategia:
    return Estrategia(
        nombre=nombre,
        descripcion=descripcion,
        transcripcion=[],
        concesion_obtenida_pct=0.0,
        riesgo="alto",
    )


SIN_COMPETENCIA = sin_corridas(
    "competencia",
    "No se ensayó: ningún otro proveedor cotiza más barato estos productos.",
)


async def correr_todas(
    contexto: ContextoNegociacion, items: list[ItemNegociado], nombres: list[str]
) -> tuple[list[Corrida], list[Exception]]:
    """Las CORRIDAS de cada estrategia en paralelo. Una corrida que falla con LLMError o no
    termina en PLAZO_CORRIDAS_SEGUNDOS (queda un TimeoutError) se descarta; cualquier otro error
    se propaga."""
    tareas = [
        asyncio.create_task(correr(contexto, items, nombre))
        for nombre in nombres
        for _ in range(CORRIDAS)
    ]
    try:
        await asyncio.wait(tareas, timeout=PLAZO_CORRIDAS_SEGUNDOS)
    finally:
        for tarea in tareas:  # a las terminadas no les hace nada
            tarea.cancel()
    await asyncio.gather(*tareas, return_exceptions=True)

    corridas, errores = [], []
    for tarea in tareas:
        if tarea.cancelled():
            error = TimeoutError(
                f"La corrida no terminó en {PLAZO_CORRIDAS_SEGUNDOS} s."
            )
        elif isinstance(tarea.exception(), LLMError):
            error = tarea.exception()
        elif tarea.exception() is not None:
            raise tarea.exception()
        else:
            corridas.append(tarea.result())
            continue
        log.warning("Corrida fallida: %s", error)
        errores.append(error)
    return corridas, errores


def items_negociados(contexto: ContextoNegociacion) -> list[ItemNegociado]:
    """Los ítems del plan con nombre y unidad del catálogo y, si otro proveedor lo cotiza más
    barato, esa alternativa real en texto (para la estrategia competencia)."""
    catalogo = {p.id: p for p in pipeline.catalogo()}
    descripciones = {
        i.producto_id: i.descripcion_original for i in contexto.cotizacion.items
    }
    items = []
    for i in contexto.items:
        producto = catalogo.get(i.producto_id)
        nombre = (
            producto.nombre
            if producto
            else descripciones.get(i.producto_id) or i.producto_id
        )
        unidad = producto.unidad_canonica if producto else "unidad"
        alternativa = None
        if (
            i.mejor_alternativa_precio is not None
            and i.mejor_alternativa_precio < i.precio_cotizado_sin_iva
        ):
            proveedor = i.mejor_alternativa_nombre or i.mejor_alternativa_proveedor_id
            alternativa = (
                f"{proveedor} cotiza $ {_fmt(i.mejor_alternativa_precio)}"
                f" {POR_UNIDAD[unidad]} sin IVA"
            )
            if i.mejor_alternativa_condicion:
                alternativa += f", pero {i.mejor_alternativa_condicion}"
        items.append(
            ItemNegociado(
                producto_id=i.producto_id,
                nombre=nombre,
                unidad=unidad,
                cantidad=Decimal(str(i.cantidad)),
                precio=i.precio_cotizado_sin_iva,
                alternativa=alternativa,
            )
        )
    return items


async def correr(
    contexto: ContextoNegociacion, items: list[ItemNegociado], estrategia: str
) -> Corrida:
    """Una simulación: RONDAS turnos de Abasto y del gemelo, y el cierre del gemelo."""
    nombre = contexto.proveedor.nombre
    system_abasto = cargar_prompt(
        "negociador_system",
        negocio=contexto.negocio,
        proveedor_nombre=nombre,
        estrategia=estrategia,
        mejores_alternativas=texto_alternativas(items),
        compromiso_volumen=compromiso_volumen(items),
    )
    apertura = cargar_prompt(
        "negociador_user",
        proveedor_nombre=nombre,
        cotizacion_resumen="\n".join(
            f"- {linea}" for linea in resumen(contexto, items)
        ),
    )
    system_gemelo = _system_gemelo(contexto, items)

    transcripcion: list[dict] = []
    for _ in range(RONDAS):
        texto = await pedir_texto(
            system=system_abasto, mensajes=_vista_abasto(apertura, transcripcion)
        )
        transcripcion.append({"rol": "abasto", "texto": texto})
        texto = await pedir_texto(
            system=system_gemelo, mensajes=_vista_gemelo(transcripcion)
        )
        transcripcion.append({"rol": "proveedor", "texto": texto})

    cierre = await pedir_json(
        system=system_gemelo,
        historial=_vista_gemelo(transcripcion),
        contenido=[
            {"type": "text", "text": cargar_prompt("cierre_gemelo", nombre=nombre)}
        ],
        esquema=CierreGemelo,
    )
    precios = precios_finales(cierre, items, contexto.perfil_privado)
    ganancia = sum(
        ((i.precio - precios[i.producto_id]) * i.cantidad for i in items), Decimal(0)
    )
    base = sum((i.precio * i.cantidad for i in items), Decimal(0))
    return Corrida(
        estrategia=estrategia,
        transcripcion=transcripcion,
        cierre=cierre,
        precios_finales=precios,
        ganancia=ganancia.quantize(CENTAVO, ROUND_HALF_UP),
        concesion_pct=float(ganancia / base * 100) if base else 0.0,
    )


def precios_finales(
    cierre: CierreGemelo, items: list[ItemNegociado], perfil: dict
) -> dict[str, Decimal]:
    """Oferta final del gemelo, acotada entre su piso y lo cotizado.

    Si no acepta negociar, o no menciona un producto, queda el precio cotizado.
    """
    piso_pct = Decimal(str(perfil.get("precio_piso_pct", 0)))
    ofrecidos = {
        p.producto_id: Decimal(str(p.precio))
        for p in cierre.precios_finales
        if p.precio > 0
    }
    precios = {}
    for item in items:
        precio = ofrecidos.get(item.producto_id, item.precio)
        if not cierre.acepta_negociar:
            precio = item.precio
        piso = item.precio * (1 - piso_pct / 100)
        precios[item.producto_id] = min(item.precio, max(piso, precio)).quantize(
            CENTAVO, ROUND_HALF_UP
        )
    return precios


def resumir(nombre: str, corridas: list[Corrida]) -> Estrategia:
    """Promedia las corridas de una estrategia y muestra la transcripción de la mejor."""
    mejor = max(corridas, key=lambda c: c.ganancia)
    animos = {c.cierre.animo for c in corridas}
    if "molesto" in animos:
        riesgo = "alto"
    elif animos == {"cordial"} and all(c.cierre.acepta_negociar for c in corridas):
        riesgo = "bajo"
    else:
        riesgo = "medio"
    descripcion = DESCRIPCIONES[nombre]
    if mejor.cierre.condicion:
        descripcion += (
            f" Condición del proveedor: {mejor.cierre.condicion.rstrip('.')}."
        )
    return Estrategia(
        nombre=nombre,
        descripcion=descripcion,
        transcripcion=mejor.transcripcion,
        concesion_obtenida_pct=round(mean(c.concesion_pct for c in corridas), 2),
        riesgo=riesgo,
    )


def ganancia(estrategia: Estrategia, valor_en_juego: Decimal) -> Decimal:
    """La misma cuenta que hace C (integracion_a.negociar): valor en juego × concesión %."""
    pct = Decimal(str(estrategia.concesion_obtenida_pct))
    return (valor_en_juego * pct / 100).quantize(CENTAVO)


def elegir(estrategias: list[Estrategia], valor_en_juego: Decimal) -> Estrategia:
    """La regla de C (integracion_a._elegir), para que el mensaje sea el de la que muestra C:
    mayor ganancia con riesgo distinto de alto; si todas son altas, la de mayor ganancia. En un
    empate gana la primera de la lista."""
    candidatas = [e for e in estrategias if e.riesgo != "alto"] or estrategias
    return max(candidatas, key=lambda e: ganancia(e, valor_en_juego))


async def redactar_mensaje(
    contexto: ContextoNegociacion, items: list[ItemNegociado], elegida: Estrategia
) -> str:
    system = cargar_prompt(
        "redactar_mensaje_system",
        negocio=contexto.negocio,
        proveedor_nombre=contexto.proveedor.nombre,
        estrategia=elegida.nombre,
        datos_reales="; ".join(datos_reales(contexto, items, elegida)),
    )
    return await pedir_texto(
        system=system,
        mensajes=[{"role": "user", "content": cargar_prompt("redactar_mensaje_user")}],
    )


def datos_reales(
    contexto: ContextoNegociacion, items: list[ItemNegociado], elegida: Estrategia
) -> list[str]:
    """Lo único que puede usar el mensaje final: nada del gemelo salvo el % a pedir."""
    datos = [
        f"cotización de {contexto.proveedor.nombre}: "
        + "; ".join(resumen(contexto, items))
    ]
    if elegida.nombre == "competencia":
        datos.append(f"mejor alternativa: {texto_alternativas(items)}")
    elif elegida.nombre == "volumen":
        datos.append(f"compromiso a ofrecer: {compromiso_volumen(items)}")
    else:
        datos.append(
            "condición a ofrecer: pago contado o anticipado"
            f" (hoy la cotización es {_texto_plazo(contexto.cotizacion.plazo_pago_dias)})"
        )
    pct = round(elegida.concesion_obtenida_pct)
    if pct >= 1:
        objetivos = ", ".join(
            f"{i.nombre} a $ {_fmt(i.precio * (100 - pct) / 100)} {POR_UNIDAD[i.unidad]}"
            for i in items
        )
        datos.append(f"pedido concreto: {pct} % de descuento ({objetivos})")
    else:
        datos.append("pedido concreto: preguntar qué mejora de precio pueden hacer")
    return datos


def resumen(contexto: ContextoNegociacion, items: list[ItemNegociado]) -> list[str]:
    """Una línea por producto que el plan le compra, más las condiciones."""
    lineas = [
        f"{i.nombre} [{i.producto_id}]: $ {_fmt(i.precio)} {POR_UNIDAD[i.unidad]} sin IVA"
        f" × {_fmt(i.cantidad)} = $ {_fmt(i.precio * i.cantidad)}"
        for i in items
    ]
    c = contexto.cotizacion
    condiciones = [
        "envío sin cargo" if not c.costo_envio else f"envío $ {_fmt(c.costo_envio)}",
        f"pago {_texto_plazo(c.plazo_pago_dias)}",
        f"entrega en {_dias(c.lead_time_dias)}",
    ]
    if c.pedido_minimo_total:
        condiciones.append(f"pedido mínimo $ {_fmt(c.pedido_minimo_total)}")
    return lineas + [", ".join(condiciones)]


def texto_alternativas(items: list[ItemNegociado]) -> str:
    partes = [f"{i.nombre}: {i.alternativa}" for i in items if i.alternativa]
    if not partes:
        return "ninguna (nadie cotiza más barato estos productos)"
    return "; ".join(partes)


def compromiso_volumen(items: list[ItemNegociado]) -> str:
    equipos = [i.nombre for i in items if i.producto_id in EQUIPAMIENTO]
    insumos = [i.nombre for i in items if i.producto_id not in EQUIPAMIENTO]
    partes = []
    if equipos:
        partes.append(
            "comprarle también lo de los próximos puestos que se equipen en los"
            f" siguientes meses ({', '.join(equipos)})"
        )
    if insumos:
        partes.append(f"repetir el pedido mensual ({', '.join(insumos)})")
    return " y ".join(partes)


def _texto_plazo(dias: int) -> str:
    return "contado" if dias == 0 else f"a {_dias(dias)}"


def _dias(dias: int) -> str:
    return "1 día" if dias == 1 else f"{dias} días"


def _lista(valor: object) -> str:
    if isinstance(valor, (list, tuple)):
        return ", ".join(str(v) for v in valor) or "nada en particular"
    return str(valor or "nada en particular")


def _system_gemelo(contexto: ContextoNegociacion, items: list[ItemNegociado]) -> str:
    perfil = contexto.perfil_privado
    return cargar_prompt(
        "proveedor_gemelo_system",
        nombre=contexto.proveedor.nombre,
        rubro=contexto.proveedor.rubro,
        personalidad=perfil.get("personalidad", ""),
        negocio=contexto.negocio,
        cotizacion_resumen="; ".join(resumen(contexto, items)),
        precio_piso_pct=perfil.get("precio_piso_pct", 0),
        perfil_concesion=perfil.get("perfil_concesion", ""),
        sensible_a=_lista(perfil.get("sensible_a")),
        insensible_a=_lista(perfil.get("insensible_a")),
    )


def _vista_abasto(apertura: str, transcripcion: list[dict]) -> list[dict]:
    """La conversación desde Abasto: sus turnos son "assistant", los del proveedor "user"."""
    return [{"role": "user", "content": apertura}] + [
        {"role": "assistant" if t["rol"] == "abasto" else "user", "content": t["texto"]}
        for t in transcripcion
    ]


def _vista_gemelo(transcripcion: list[dict]) -> list[dict]:
    """La conversación desde el gemelo: los turnos de Abasto le llegan como "user"."""
    return [
        {"role": "user" if t["rol"] == "abasto" else "assistant", "content": t["texto"]}
        for t in transcripcion
    ]


def _fmt(valor: Decimal | float) -> str:
    """Monto en formato uruguayo, con centavos solo si los tiene: 10.900 · 178,69."""
    d = Decimal(str(valor)).quantize(CENTAVO, ROUND_HALF_UP)
    return fmt(d, 0 if d == d.to_integral_value() else 2)
