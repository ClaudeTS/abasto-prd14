"""Capa 5 — Negociación ensayada. ARQUITECTURA §7, prompts de PROMPTS.md §3–§5.

Para cada estrategia (competencia, volumen, plazo) se corren 2 simulaciones de hasta 3 rondas entre
Abasto (prompt `negociador`) y el gemelo del proveedor (prompt `proveedor_gemelo`), que conoce su
precio piso y su perfil. Al final el gemelo emite su oferta (`cierre_gemelo`) y el código mide la
concesión. Las 6 corridas van en paralelo con asyncio.gather.

Los números los pone el código, no el LLM:
- la concesión se calcula contra la cotización y se acota al piso del proveedor;
- el backend (integracion_a.py) recalcula la ganancia y aplica la regla de elección de §7.

Contrato: `ensayar(contexto) -> dict` (docs/CONTRATO_BACKEND.md, "Para A").
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app import llm
from app.models import ContextoNegociacion

log = logging.getLogger("abasto.negociacion")

ESTRATEGIAS: tuple[str, ...] = ("competencia", "volumen", "plazo")
CORRIDAS = 2
RONDAS = 3
MAX_PALABRAS_MENSAJE = 80
# AGENTS §6.6 pide temperatura 0,7 para negociador y gemelo; el llm.py de A todavía no expone
# temperatura (usa salida estructurada con effort), así que la variación entre corridas sale del
# propio modelo. Si A agrega el parámetro, pasarlo en _pedir().
MAX_TOKENS_TURNO = 1024  # PROMPTS.md sugiere 300; con margen para que no corte por max_tokens
MAX_TOKENS_CIERRE = 1024
MAX_TOKENS_MENSAJE = 1024

DESCRIPCIONES = {
    "competencia": "Mencionar la mejor cotización alternativa real, con nombre y precio.",
    "volumen": "Ofrecer compromiso de compras futuras a cambio de mejor precio.",
    "plazo": "Ofrecer pago contado o anticipado a cambio de descuento.",
}
# Qué ofrece Abasto en la estrategia "volumen". Supuesto de negocio de la demo: para
# equipamiento, puestos nuevos; para insumos, el pedido mensual.
EQUIPAMIENTO = {"silla", "notebook"}
COMPROMISO_EQUIPAMIENTO = "equipar 10 puestos más en los próximos tres meses"
COMPROMISO_INSUMOS = "repetir este pedido todos los meses durante 6 meses"


# ---------------------------------------------------------------- esquemas de salida
class TurnoAbasto(BaseModel):
    texto: str


class TurnoGemelo(BaseModel):
    texto: str
    cierra_trato: bool
    molesto: bool


class PrecioFinal(BaseModel):
    producto_id: str
    precio: float


class Cierre(BaseModel):
    acepta_negociar: bool
    precio_final_por_item: list[PrecioFinal]
    condicion: str | None = None
    animo: Literal["cordial", "neutral", "molesto"]


class Redaccion(BaseModel):
    mensaje: str


class Texto(BaseModel):
    texto: str


# ---------------------------------------------------------------- resultado de una corrida
@dataclass
class Corrida:
    estrategia: str
    transcripcion: list[dict[str, str]] = field(default_factory=list)
    rondas: int = RONDAS
    molesto: bool = False
    cierre: Cierre | None = None
    concesion_pct: float = 0.0
    precios_finales: dict[str, Decimal] = field(default_factory=dict)


# ---------------------------------------------------------------- formato
def _monto(valor: Decimal | float) -> str:
    return "$ " + f"{Decimal(str(valor)).quantize(Decimal(1)):,}".replace(",", ".")


def _nombres() -> dict[str, str]:
    from app.pipeline import catalogo  # import diferido: evita ciclos al cargar módulos

    return {p.id: p.nombre for p in catalogo()}


def _cotizacion_resumen(ctx: ContextoNegociacion, nombres: dict[str, str]) -> str:
    c = ctx.cotizacion
    lineas = [
        f"- {nombres.get(i.producto_id, i.producto_id)}: {_monto(i.precio_unitario_sin_iva)} "
        f"por unidad, sin IVA"
        for i in c.items
        if i.producto_id in {x.producto_id for x in ctx.items}
    ]
    condiciones = [
        f"envío {_monto(c.costo_envio) if c.costo_envio else 'sin cargo'}",
        f"pago {'contado' if c.plazo_pago_dias == 0 else f'a {c.plazo_pago_dias} días'}",
        f"entrega en {c.lead_time_dias} días",
    ]
    return "\n".join(lineas) + "\nCondiciones: " + ", ".join(condiciones) + "."


def _items_plan(ctx: ContextoNegociacion, nombres: dict[str, str]) -> str:
    return "\n".join(
        f"- {nombres.get(i.producto_id, i.producto_id)}: {i.cantidad:g} × "
        f"{_monto(i.precio_cotizado_sin_iva)} = {_monto(Decimal(str(i.cantidad)) * i.precio_cotizado_sin_iva)}"
        for i in ctx.items
    )


def _alternativas(ctx: ContextoNegociacion, nombres: dict[str, str]) -> str:
    lineas = []
    for i in ctx.items:
        if i.mejor_alternativa_precio is None:
            continue
        linea = (
            f"- {i.mejor_alternativa_nombre} cotiza {nombres.get(i.producto_id, i.producto_id)} "
            f"a {_monto(i.mejor_alternativa_precio)} sin IVA"
        )
        if i.mejor_alternativa_condicion:
            linea += f" (ojo: {i.mejor_alternativa_condicion})"
        lineas.append(linea)
    return "\n".join(lineas) or "- No hay cotizaciones alternativas para estos ítems."


def _compromiso(ctx: ContextoNegociacion) -> str:
    if any(i.producto_id in EQUIPAMIENTO for i in ctx.items):
        return COMPROMISO_EQUIPAMIENTO
    return COMPROMISO_INSUMOS


def _historial(turnos: list[dict[str, str]], proveedor: str) -> str:
    if not turnos:
        return "(todavía no hay mensajes; arrancás vos)"
    nombre = {"abasto": "Abasto", "proveedor": proveedor}
    return "\n".join(f"{nombre[t['rol']]}: {t['texto']}" for t in turnos)


def _prompt(archivo: str, **variables: object) -> str:
    """Como llm.cargar_prompt, pero admite la variable {{nombre}} (que choca con el primer
    parámetro de cargar_prompt). Arreglo sugerido en llm.py: `def cargar_prompt(nombre, /, **v)`."""
    texto = llm.cargar_prompt(archivo)
    for clave, valor in variables.items():
        texto = texto.replace("{{" + clave + "}}", str(valor))
    return texto


# ---------------------------------------------------------------- llamadas al LLM
async def _pedir(system: str, user: str, esquema: type[BaseModel], max_tokens: int) -> Any:
    return await llm.pedir_json(
        system=system,
        contenido=[{"type": "text", "text": user}],
        esquema=esquema,
        max_tokens=max_tokens,
    )


def _system_gemelo(ctx: ContextoNegociacion, resumen: str) -> str:
    perfil = ctx.perfil_privado
    return _prompt(
        "proveedor_gemelo_system",
        nombre=ctx.proveedor.nombre,
        rubro=ctx.proveedor.rubro,
        personalidad=perfil.get("personalidad", ""),
        negocio=ctx.negocio,
        cotizacion_resumen=resumen,
        precio_piso_pct=perfil.get("precio_piso_pct", 0),
        perfil_concesion=perfil.get("perfil_concesion", ""),
        sensible_a="; ".join(perfil.get("sensible_a", [])) or "nada en particular",
        insensible_a="; ".join(perfil.get("insensible_a", [])) or "nada en particular",
    )


async def _correr(ctx: ContextoNegociacion, estrategia: str, textos: dict[str, str]) -> Corrida:
    """Una simulación: hasta RONDAS idas y vueltas + cierre del gemelo."""
    corrida = Corrida(estrategia=estrategia)
    proveedor = ctx.proveedor.nombre
    system_abasto = _prompt(
        "negociador_system",
        negocio=ctx.negocio,
        proveedor_nombre=proveedor,
        estrategia=estrategia,
        mejores_alternativas=textos["alternativas"],
        compromiso_volumen=textos["compromiso"],
    )
    system_gemelo = _system_gemelo(ctx, textos["resumen"])
    for ronda in range(1, RONDAS + 1):
        historial = _historial(corrida.transcripcion, proveedor)
        turno: TurnoAbasto = await _pedir(
            system_abasto,
            _prompt(
                "negociador_user",
                proveedor_nombre=proveedor,
                negocio=ctx.negocio,
                cotizacion_resumen=textos["resumen"],
                items_plan=textos["items"],
                mejores_alternativas=textos["alternativas"],
                historial=historial,
            ),
            TurnoAbasto,
            MAX_TOKENS_TURNO,
        )
        corrida.transcripcion.append({"rol": "abasto", "texto": turno.texto.strip()})
        respuesta: TurnoGemelo = await _pedir(
            system_gemelo,
            _prompt(
                "proveedor_gemelo_user",
                negocio=ctx.negocio,
                historial=_historial(corrida.transcripcion, proveedor),
            ),
            TurnoGemelo,
            MAX_TOKENS_TURNO,
        )
        corrida.transcripcion.append({"rol": "proveedor", "texto": respuesta.texto.strip()})
        corrida.molesto = corrida.molesto or respuesta.molesto
        if respuesta.cierra_trato:
            corrida.rondas = ronda
            break
    cierre_user = (
        f"Conversación con {ctx.negocio}:\n{_historial(corrida.transcripcion, proveedor)}\n\n"
        + _prompt("cierre_gemelo_user", nombre=proveedor)
    )
    corrida.cierre = await _pedir(system_gemelo, cierre_user, Cierre, MAX_TOKENS_CIERRE)
    corrida.molesto = corrida.molesto or corrida.cierre.animo == "molesto"
    _medir(corrida, ctx)
    return corrida


def _medir(corrida: Corrida, ctx: ContextoNegociacion) -> None:
    """Concesión ponderada por el valor del plan, acotada a [0, piso del proveedor]."""
    piso = Decimal(str(ctx.perfil_privado.get("precio_piso_pct", 0))) / 100
    ofertas = {p.producto_id: Decimal(str(p.precio)) for p in corrida.cierre.precio_final_por_item}
    total = ahorro = Decimal(0)
    for item in ctx.items:
        original = item.precio_cotizado_sin_iva
        final = ofertas.get(item.producto_id, original) if corrida.cierre.acepta_negociar else original
        final = min(max(final, original * (1 - piso)), original)  # nunca bajo el piso ni sobre lo cotizado
        corrida.precios_finales[item.producto_id] = final
        cantidad = Decimal(str(item.cantidad))
        total += original * cantidad
        ahorro += (original - final) * cantidad
    corrida.concesion_pct = float(ahorro / total * 100) if total else 0.0


def _riesgo(corridas: list[Corrida]) -> str:
    if any(c.molesto for c in corridas):
        return "alto"
    if all(c.rondas <= 2 for c in corridas):
        return "bajo"
    return "medio"


def _representativa(corridas: list[Corrida]) -> Corrida:
    """La corrida más cercana al promedio: la que se muestra en la UI."""
    promedio = statistics.mean(c.concesion_pct for c in corridas)
    return min(corridas, key=lambda c: abs(c.concesion_pct - promedio))


def _elegir(estrategias: list[dict[str, Any]]) -> str:
    """ARQUITECTURA §7: mayor ganancia con riesgo ≠ alto; si todas son altas, la de mayor ganancia."""
    candidatas = [e for e in estrategias if e["riesgo"] != "alto"] or estrategias
    return max(candidatas, key=lambda e: e["ganancia_esperada_uyu"])["nombre"]


# ---------------------------------------------------------------- mensaje final
def _datos_reales(ctx: ContextoNegociacion, estrategia: str, textos: dict[str, str]) -> str:
    partes = [f"Cotización de {ctx.proveedor.nombre}:\n{textos['resumen']}"]
    if estrategia == "competencia":
        partes.append(f"Mejores alternativas reales:\n{textos['alternativas']}")
    elif estrategia == "volumen":
        partes.append(f"Compromiso que se puede ofrecer: {textos['compromiso']}.")
    else:
        partes.append("Condición que se puede ofrecer: pago contado al recibir la mercadería.")
    return "\n".join(partes)


async def _redactar(
    ctx: ContextoNegociacion, estrategia: str, corrida: Corrida, textos: dict[str, str]
) -> str:
    nombres = _nombres()
    resultado = ", ".join(
        f"{nombres.get(pid, pid)} a {_monto(precio)}" for pid, precio in corrida.precios_finales.items()
    )
    if corrida.cierre and corrida.cierre.condicion:
        resultado += f" ({corrida.cierre.condicion})"
    system = _prompt(
        "redactar_mensaje_system",
        negocio=ctx.negocio,
        proveedor_nombre=ctx.proveedor.nombre,
        estrategia=estrategia,
        datos_reales=_datos_reales(ctx, estrategia, textos),
    )
    user = _prompt(
        "redactar_mensaje_user",
        estrategia=estrategia,
        resultado=resultado,
        transcripcion=_historial(corrida.transcripcion, ctx.proveedor.nombre),
    )
    redaccion: Redaccion = await _pedir(system, user, Redaccion, MAX_TOKENS_MENSAJE)
    mensaje = redaccion.mensaje.strip()
    if len(mensaje.split()) > MAX_PALABRAS_MENSAJE:
        log.warning("El mensaje propuesto tiene %s palabras (máx. %s)", len(mensaje.split()), MAX_PALABRAS_MENSAJE)
    return mensaje


# ---------------------------------------------------------------- entrada pública
async def ensayar(contexto: ContextoNegociacion) -> dict[str, Any]:
    """Ensaya las 3 estrategias y propone el mensaje. Devuelve el dict del contrato."""
    inicio = time.perf_counter()
    nombres = _nombres()
    textos = {
        "resumen": _cotizacion_resumen(contexto, nombres),
        "items": _items_plan(contexto, nombres),
        "alternativas": _alternativas(contexto, nombres),
        "compromiso": _compromiso(contexto),
    }
    tareas = [
        _correr(contexto, estrategia, textos)
        for estrategia in ESTRATEGIAS
        for _ in range(CORRIDAS)
    ]
    resultados = await asyncio.gather(*tareas, return_exceptions=True)

    por_estrategia: dict[str, list[Corrida]] = {e: [] for e in ESTRATEGIAS}
    errores: list[BaseException] = []
    for resultado in resultados:
        if isinstance(resultado, BaseException):
            errores.append(resultado)
            log.warning("Una corrida falló: %s", resultado)
        else:
            por_estrategia[resultado.estrategia].append(resultado)
    if not any(por_estrategia.values()):
        raise errores[0]  # todas fallaron: que el endpoint muestre el error real del LLM

    estrategias: list[dict[str, Any]] = []
    representativas: dict[str, Corrida] = {}
    for nombre, corridas in por_estrategia.items():
        if not corridas:
            continue  # si una estrategia falló entera, se muestran las otras
        concesion = statistics.mean(c.concesion_pct for c in corridas)
        representativa = _representativa(corridas)
        representativas[nombre] = representativa
        estrategias.append(
            {
                "nombre": nombre,
                "descripcion": DESCRIPCIONES[nombre],
                "transcripcion": representativa.transcripcion,
                "concesion_obtenida_pct": round(concesion, 2),
                "ganancia_esperada_uyu": float(contexto.valor_en_juego_uyu) * concesion / 100,
                "riesgo": _riesgo(corridas),
            }
        )
    elegida = _elegir(estrategias)
    mensaje = await _redactar(contexto, elegida, representativas[elegida], textos)
    log.info(
        "Negociación con %s ensayada en %.1f s · elegida %s · %s",
        contexto.proveedor.id,
        time.perf_counter() - inicio,
        elegida,
        ", ".join(f"{e['nombre']} {e['concesion_obtenida_pct']} % ({e['riesgo']})" for e in estrategias),
    )
    return {"estrategias": estrategias, "elegida": elegida, "mensaje_propuesto": mensaje}
