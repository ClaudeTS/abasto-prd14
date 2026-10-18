"""Llamadas telefónicas del agente de compras (rol C). Ver docs/LLAMADAS.md.

Dos tipos:
- `cotizacion`: llama al proveedor que no respondió y le pide la cotización. La transcripción entra
  al feed como un mensaje de canal "llamada" y pasa por la extracción como cualquier otro.
- `negociacion`: con la estrategia y el mensaje que Lucía aprobó, llama para negociar. El resultado
  (resumen, acuerdo, precio) queda en la llamada; nada se llama sin esa aprobación.

Modos (`LLAMADAS_MODO`):
- `simulada` (default): sin costo ni red. La transcripción aparece de a poco, con los fixtures.
- `real`: agente de ElevenLabs con número de Twilio importado (integración nativa).
  `POST /v1/convai/twilio/outbound-call` dispara la llamada y `GET /v1/convai/conversations/{id}`
  se consulta cada pocos segundos: sin webhooks, así no hace falta una URL pública.

El agente se configura una vez en la consola de ElevenLabs con un prompt base; lo de cada llamada
llega en variables dinámicas (`instrucciones`, `primer_mensaje`, …), sin overrides.
Solo se llama a los números de `TELEFONOS_PROVEEDORES`.

RF-06 (PRD 1.4): en el primer mensaje el agente se presenta como asistente de inteligencia artificial
y avisa que la llamada se graba; no hay duración máxima. Las llamadas de cotización siguen la
secuencia de contacto (§11.1): si el proveedor no atiende, se reintenta a los
`LLAMADA_REINTENTO_MINUTOS` (30); si tampoco, se le escribe por WhatsApp con el motivo y, si no tiene
WhatsApp, se le manda un email con la solicitud de cotización. Cada contacto enviado queda en la
colección `contactos`; el estado de la secuencia, en `secuencias` (y en `GET /llamadas/{id}`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app import config, pedidos, store
from app.models import (
    ConfigLlamadas,
    Llamada,
    MensajeCrudo,
    Negociacion,
    Plan,
    ResultadoLlamada,
    TurnoLlamada,
)
from app.normalizacion import fmt
from app.pipeline import catalogo, modo_extraccion, perfil_privado, procesar_mensaje, proveedores

log = logging.getLogger("abasto.llamadas")
INTERVALO_CONSULTA_S = 2.5
# No es una duración máxima de la llamada (RF-06: no hay): el agente no corta. Es hasta cuándo se
# sigue consultando a ElevenLabs una conversación que nunca informa que terminó.
SEGUIMIENTO_MAXIMO_S = 4 * 60 * 60
ACTIVAS = ("iniciando", "sonando", "en_curso", "procesando")
REINTENTO_MINUTOS = 30  # RF-06; se cambia con LLAMADA_REINTENTO_MINUTOS
# En simulado, cada minuto de espera dura 1 s × SIM_DELAY_SECONDS / 4 (30 min → 30 s con la base 4).
SEGUNDOS_SIMULADOS_POR_MINUTO = 1.0
DIAS_AUDIO = 60  # RF-06: la transcripción se guarda siempre; el audio, 60 días (retención en ElevenLabs)
_tareas: set[asyncio.Task] = set()
_reintentos: dict[str, asyncio.Task] = {}  # secuencia_id → reintento programado
_no_atendidas: set[str] = set()  # llamadas que terminaron sin que el proveedor atienda


class LlamadaNoPosible(ValueError):
    """Falta configuración, teléfono o datos para llamar (409 con el motivo)."""


# ---------------------------------------------------------------- configuración
def configuracion() -> ConfigLlamadas:
    s = config.settings
    faltan = [
        nombre
        for nombre, valor in (
            ("ELEVENLABS_API_KEY", s.elevenlabs_api_key),
            ("ELEVENLABS_AGENT_ID", s.elevenlabs_agent_id),
            ("ELEVENLABS_PHONE_NUMBER_ID", s.elevenlabs_phone_number_id),
            ("TELEFONOS_PROVEEDORES", s.telefonos_proveedores),
        )
        if not valor
    ]
    real = s.llamadas_modo == "real"
    return ConfigLlamadas(
        modo="real" if real else "simulada",
        lista=not real or not faltan,
        faltan=faltan if real else [],
        proveedores_con_telefono=sorted((s.telefonos_proveedores or {}).keys()),
    )


def enmascarar(numero: str | None) -> str | None:
    """+59899111222 → +598 99• ••• 222 (para la UI y los logs)."""
    if not numero:
        return None
    digitos = numero.lstrip("+")
    if len(digitos) < 7:
        return "•" * len(digitos)
    return f"+{digitos[:3]} {digitos[3:5]}• ••• {digitos[-3:]}"


# ---------------------------------------------------------------- instrucciones para el agente
def _nombres() -> dict[str, str]:
    return {p.id: p.nombre for p in catalogo()}


def _variables_base(pedido: Any, proveedor_id: str) -> dict[str, str]:
    prov = proveedores()[proveedor_id]
    return {
        "proveedor_nombre": prov.nombre,
        "negocio": pedido.negocio,
        "comprador": (pedido.comprador or "compras").split(" (")[0],
    }


def _presentacion(negocio: str) -> str:
    """RF-06: se identifica como IA y avisa que graba, en el primer mensaje."""
    return f"Soy el asistente de inteligencia artificial de {negocio} y te aviso que esta llamada se graba."


_REGLAS_IDENTIDAD = (
    "Ya te presentaste como asistente de inteligencia artificial y avisaste que la llamada se graba: "
    "si te lo preguntan, confirmalo, nunca lo niegues. La llamada no tiene duración máxima: no apures "
    "al proveedor. "
)


def lista_pedido(pedido: Any, proveedor_id: str) -> str:
    """Las líneas del pedido que vende ese proveedor, una por renglón (para llamadas y avisos)."""
    nombres = _nombres()
    vende = set(perfil_privado(proveedor_id).get("tabla_precios", {}))
    lineas = [l for l in pedido.lineas if not vende or l.producto_id in vende] or pedido.lineas
    unidades = {p.id: p.unidad_canonica for p in catalogo()}
    return "\n".join(
        f"- {fmt(l.cantidad)} {'litros' if unidades.get(l.producto_id) == 'l' else 'unidades'} "
        f"de {nombres[l.producto_id]} (para el {l.necesario_para.strftime('%d/%m')})"
        for l in lineas
    )


def instrucciones_cotizacion(pedido: Any, proveedor_id: str) -> dict[str, str]:
    """Variables dinámicas para pedir la cotización a quien no respondió."""
    base = _variables_base(pedido, proveedor_id)
    lista = lista_pedido(pedido, proveedor_id)
    instrucciones = (
        f"Llamás a {base['proveedor_nombre']} de parte de {base['comprador']}, de {base['negocio']}. "
        + _REGLAS_IDENTIDAD
        + "Les pidieron cotización por WhatsApp y todavía no respondieron. Pedí precio de:\n"
        f"{lista}\n"
        "Para cada producto preguntá el precio y en qué unidad cotiza (por unidad, por caja, por "
        "bidón), y si incluye IVA. Preguntá también plazo de entrega, forma de pago y costo de envío. "
        "En esta llamada no negocies: solo tomá nota. Antes de cortar, repetí los precios para "
        "confirmarlos y agradecé."
    )
    return {
        **base,
        "tipo_llamada": "cotizacion",
        "instrucciones": instrucciones,
        "primer_mensaje": (
            f"Hola, ¿hablo con {base['proveedor_nombre']}? {_presentacion(base['negocio'])} "
            f"Te llamo de parte de {base['comprador']} por la cotización que les pedimos por WhatsApp. "
            "¿Tenés un minuto?"
        ),
    }


def instrucciones_negociacion(
    pedido: Any, negociacion: Negociacion, plan: Plan, mensaje: str
) -> dict[str, str]:
    """Variables dinámicas para negociar con la estrategia y el mensaje que aprobó Lucía."""
    base = _variables_base(pedido, negociacion.proveedor_id)
    nombres = _nombres()
    asignado = [a for a in plan.asignaciones if a.proveedor_id == negociacion.proveedor_id]
    if not asignado:
        raise LlamadaNoPosible(f"{base['proveedor_nombre']} no tiene ítems en el plan")
    items = "\n".join(
        f"- {fmt(a.cantidad)} × {nombres[a.producto_id]} a $ {fmt(a.precio_unitario_sin_iva)} + IVA "
        f"c/u (total $ {fmt(a.subtotal)})"
        for a in asignado
    )
    estrategia = next((e for e in negociacion.estrategias if e.nombre == negociacion.elegida), None)
    descripcion = estrategia.descripcion if estrategia else negociacion.elegida
    instrucciones = (
        f"Llamás a {base['proveedor_nombre']} de parte de {base['comprador']}, de {base['negocio']}, "
        f"para negociar esta compra:\n{items}\n"
        + _REGLAS_IDENTIDAD
        + "\n"
        f"Estrategia aprobada por {base['comprador']}: {negociacion.elegida} ({descripcion}).\n"
        f"Mensaje aprobado, usalo como guion pero no lo leas textual: «{mensaje}»\n"
        "Reglas: no reveles cuánto están dispuestos a pagar, no inventes competidores ni precios, no "
        "amenaces. Si el proveedor ofrece algo razonable, aceptalo en principio y aclarale que "
        f"{base['comprador']} le confirma por WhatsApp. Antes de cortar, repetí el precio y la "
        "condición que acordaron."
    )
    return {
        **base,
        "tipo_llamada": "negociacion",
        "instrucciones": instrucciones,
        "primer_mensaje": (
            f"Hola, ¿hablo con {base['proveedor_nombre']}? {_presentacion(base['negocio'])} "
            f"Te llamo de parte de {base['comprador']} por la cotización de "
            f"{nombres[asignado[0].producto_id].lower()}. ¿Tenés un minuto?"
        ),
    }


# ---------------------------------------------------------------- ElevenLabs
def _headers() -> dict[str, str]:
    return {"xi-api-key": config.settings.elevenlabs_api_key}


async def _disparar(numero: str, variables: dict[str, str]) -> dict[str, Any]:
    s = config.settings
    cuerpo = {
        "agent_id": s.elevenlabs_agent_id,
        "agent_phone_number_id": s.elevenlabs_phone_number_id,
        "to_number": numero,
        "conversation_initiation_client_data": {"dynamic_variables": variables},
    }
    async with httpx.AsyncClient(base_url=s.elevenlabs_base_url, timeout=30) as http:
        r = await http.post("/v1/convai/twilio/outbound-call", json=cuerpo, headers=_headers())
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs respondió {r.status_code}: {r.text[:300]}")
    datos = r.json()
    if not datos.get("success", False):
        raise RuntimeError(datos.get("message") or "ElevenLabs no pudo iniciar la llamada")
    return datos


async def _consultar(conversation_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=config.settings.elevenlabs_base_url, timeout=30) as http:
        r = await http.get(f"/v1/convai/conversations/{conversation_id}", headers=_headers())
    r.raise_for_status()
    return r.json()


_ESTADOS = {"initiated": "sonando", "in-progress": "en_curso", "processing": "procesando"}
# `call_result` de ElevenLabs que cuentan como "no atendió" para la secuencia de contacto.
_SIN_ATENDER = {
    "busy": "El proveedor no atendió: daba ocupado",
    "no_answer": "El proveedor no atendió",
    "no-answer": "El proveedor no atendió",
    "failed": "El proveedor no atendió: la llamada no se pudo completar",
}


def _aplicar(llamada: Llamada, datos: dict[str, Any]) -> None:
    """Vuelca la respuesta de GET /conversations/{id} en la llamada."""
    turnos = [
        TurnoLlamada(
            rol="proveedor" if t.get("role") == "user" else "abasto",
            texto=t["message"].strip(),
            segundo=t.get("time_in_call_secs"),
        )
        for t in datos.get("transcript") or []
        if (t.get("message") or "").strip()
    ]
    if turnos:
        llamada.transcripcion = turnos
    meta = datos.get("metadata") or {}
    llamada.duracion_segundos = meta.get("call_duration_secs") or llamada.duracion_segundos
    llamada.call_sid = (meta.get("phone_call") or {}).get("call_sid") or llamada.call_sid
    estado = datos.get("status")
    if estado in _ESTADOS:
        llamada.estado = _ESTADOS[estado]  # type: ignore[assignment]
        return
    resultado_llamada = (meta.get("phone_call") or {}).get("call_result")
    if estado == "failed" or resultado_llamada in _SIN_ATENDER:
        llamada.estado = "fallida"
        llamada.error = _SIN_ATENDER.get(resultado_llamada, "El proveedor no atendió: no se pudo contactar")
        _no_atendidas.add(llamada.id)
        return
    if estado == "done":
        llamada.estado = "terminada"
        llamada.resultado = _resultado(datos.get("analysis") or {})


def _resultado(analisis: dict[str, Any]) -> ResultadoLlamada:
    """Resumen de ElevenLabs y datos recolectados (si el agente tiene configurados
    `acuerdo`, `precio_acordado` y `condicion` en Data collection, docs/LLAMADAS.md)."""
    datos = {k: (v or {}).get("value") for k, v in (analisis.get("data_collection_results") or {}).items()}
    precio = datos.get("precio_acordado")
    try:
        precio = Decimal(str(precio)) if precio not in (None, "") else None
    except Exception:  # noqa: BLE001 — si el agente devolvió texto, no inventamos un número
        precio = None
    acuerdo = datos.get("acuerdo")
    return ResultadoLlamada(
        resumen=analisis.get("transcript_summary") or None,
        acuerdo=acuerdo if isinstance(acuerdo, bool) else None,
        precio_acordado=precio,
        condicion=datos.get("condicion") or None,
    )


async def _seguir_real(llamada: Llamada) -> None:
    limite = time.time() + SEGUIMIENTO_MAXIMO_S
    while llamada.estado in ACTIVAS and time.time() < limite:
        await asyncio.sleep(INTERVALO_CONSULTA_S)
        try:
            _aplicar(llamada, await _consultar(llamada.conversation_id))  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            log.warning("No pude consultar la llamada %s: %s", llamada.id, exc)
            continue
        store.guardar("llamadas", llamada)
    if llamada.estado in ACTIVAS:
        llamada.estado, llamada.error = "fallida", "La llamada superó el tiempo máximo de seguimiento"


# ---------------------------------------------------------------- simulación (respaldo)
def _escala() -> float:
    return max(config.settings.sim_delay_seconds, 0.0) / 4.0


def _guion_simulado(llamada: Llamada, variables: dict[str, str]) -> tuple[list[TurnoLlamada], ResultadoLlamada]:
    nombre = variables["proveedor_nombre"]
    turnos = [TurnoLlamada(rol="abasto", texto=variables["primer_mensaje"])]
    if llamada.tipo == "cotizacion":
        fijo = next(
            (r["contenido"] for r in store.semilla("respuestas_fijas")["respuestas"]
             if r["proveedor_id"] == llamada.proveedor_id),
            None,
        )
        turnos += [
            TurnoLlamada(rol="proveedor", texto=fijo or "Sí, decime. Ahora te paso los precios por WhatsApp."),
            TurnoLlamada(rol="abasto", texto="Perfecto, anoto todo. ¡Muchas gracias!"),
        ]
        return turnos, ResultadoLlamada(resumen=f"{nombre} pasó la cotización por teléfono.")
    neg = store.obtener("negociaciones", llamada.negociacion_id or "", Negociacion)
    estrategia = next((e for e in (neg.estrategias if neg else []) if e.nombre == (neg.elegida if neg else "")), None)
    for t in (estrategia.transcripcion if estrategia else []):
        turnos.append(TurnoLlamada(rol="proveedor" if t.get("rol") == "proveedor" else "abasto", texto=t.get("texto", "")))
    turnos.append(
        TurnoLlamada(rol="abasto", texto=f"Perfecto, quedamos así. {variables['comprador']} te confirma por WhatsApp. ¡Gracias!")
    )
    concesion = estrategia.concesion_obtenida_pct if estrategia else 0.0
    plan_dict = store.obtener_dict("planes", llamada.pedido_id)
    precio = None
    if plan_dict and concesion:
        asignado = [a for a in Plan.model_validate(plan_dict).asignaciones if a.proveedor_id == llamada.proveedor_id]
        if asignado:
            precio = (asignado[0].precio_unitario_sin_iva * (1 - Decimal(str(concesion)) / 100)).quantize(Decimal("0.01"))
    return turnos, ResultadoLlamada(
        resumen=(
            f"{nombre} aceptó un {fmt(concesion, 1)} % de descuento con la estrategia "
            f"{neg.elegida if neg else ''}." if concesion else f"{nombre} no cedió en el precio."
        ),
        acuerdo=bool(concesion),
        precio_acordado=precio,
    )


async def _seguir_simulada(llamada: Llamada, variables: dict[str, str], no_atiende: bool = False) -> None:
    if no_atiende:  # ?simular_no_atiende=true: suena y nadie atiende (secuencia de contacto)
        await asyncio.sleep(6.0 * _escala())
        llamada.estado, llamada.error = "fallida", "El proveedor no atendió (llamada simulada)"
        _no_atendidas.add(llamada.id)
        return
    turnos, resultado = _guion_simulado(llamada, variables)
    await asyncio.sleep(2.0 * _escala())
    llamada.estado = "en_curso"
    store.guardar("llamadas", llamada)
    for turno in turnos:
        await asyncio.sleep(max(1.2, len(turno.texto) / 60) * _escala())
        llamada.transcripcion.append(turno)
        llamada.duracion_segundos = int(sum(max(4, len(t.texto) / 14) for t in llamada.transcripcion))
        store.guardar("llamadas", llamada)
    llamada.estado = "procesando"
    store.guardar("llamadas", llamada)
    await asyncio.sleep(1.0 * _escala())
    llamada.estado, llamada.resultado = "terminada", resultado


# ---------------------------------------------------------------- después de la llamada
def _texto_transcripcion(llamada: Llamada) -> str:
    nombre = proveedores()[llamada.proveedor_id].nombre
    return "\n".join(f"{'Abasto' if t.rol == 'abasto' else nombre}: {t.texto}" for t in llamada.transcripcion)


async def _al_terminar(llamada: Llamada) -> None:
    if llamada.tipo == "cotizacion" and llamada.estado == "terminada":
        mensaje = MensajeCrudo(
            id=f"msg_{llamada.proveedor_id}_{uuid.uuid4().hex[:6]}",
            pedido_id=llamada.pedido_id,
            proveedor_id=llamada.proveedor_id,
            canal="llamada",
            contenido_texto=_texto_transcripcion(llamada),
            recibido_en=datetime.now(),
            estado="pendiente",
        )
        llamada.mensaje_id = mensaje.id
        store.guardar("mensajes", mensaje)
        store.guardar("llamadas", llamada)
        if llamada.modo == "real" and modo_extraccion() != "llm":
            # Los fixtures no saben lo que se dijo en una llamada real: no se inventa una lectura.
            mensaje.estado, mensaje.error = "error", (
                "Para leer una llamada real hace falta la extracción con LLM (ANTHROPIC_API_KEY)"
            )
            store.guardar("mensajes", mensaje)
            return
        try:
            await procesar_mensaje(mensaje)
        except Exception:  # noqa: BLE001 — el mensaje queda en "error" con el motivo
            pass
        respondieron = {m["proveedor_id"] for m in store.valores("mensajes") if m["pedido_id"] == llamada.pedido_id}
        pedido = pedidos.obtener(llamada.pedido_id)
        if pedido and pedido.estado == "cotizando" and set(proveedores()) <= respondieron:
            pedidos.cambiar_estado(llamada.pedido_id, "cotizado")  # la llamada trajo la última respuesta
    if llamada.tipo == "negociacion":
        pedidos.cambiar_estado(llamada.pedido_id, "aprobado")


async def _seguir(llamada: Llamada, variables: dict[str, str], no_atiende: bool = False) -> None:
    try:
        if llamada.modo == "real":
            await _seguir_real(llamada)
        else:
            await _seguir_simulada(llamada, variables, no_atiende)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — el error queda en la llamada, la UI lo muestra
        log.exception("Falló el seguimiento de la llamada %s", llamada.id)
        llamada.estado, llamada.error = "fallida", str(exc)
    store.guardar("llamadas", llamada)
    await _al_terminar(llamada)
    await _continuar_secuencia(llamada)
    log.info("Llamada %s %s (%s)", llamada.id, llamada.estado, llamada.modo)


# ---------------------------------------------------------------- secuencia de contacto (RF-06, §11.1)
MotivoContacto = Literal["solicitud_cotizacion", "reintento", "aviso_no_atendio", "negociacion"]
EstadoPaso = Literal[
    "pendiente", "programado", "en_curso", "atendida", "no_atendida", "enviado", "omitido", "cancelado", "error"
]


class Contacto(BaseModel):
    """Contacto enviado a un proveedor. Esquema compartido: lo lee el detalle del pedido (bloque 1)."""

    id: str
    pedido_id: str
    proveedor_id: str
    canal: Literal["whatsapp", "email", "llamada"]
    sentido: Literal["enviado"] = "enviado"
    texto: str
    enviado_en: str  # ISO sin zona
    motivo: MotivoContacto


class PasoSecuencia(BaseModel):
    paso: Literal["llamada", "reintento", "whatsapp", "email"]
    estado: EstadoPaso = "pendiente"
    llamada_id: str | None = None
    contacto_id: str | None = None
    programado_para: datetime | None = None
    hecho_en: datetime | None = None
    detalle: str | None = None


class SecuenciaContacto(BaseModel):
    id: str
    pedido_id: str
    proveedor_id: str
    estado: Literal["en_curso", "reintento_programado", "atendida", "respondio", "aviso_enviado", "interrumpida"]
    intento: int = 1  # llamada en curso o última hecha (1 o 2)
    reintento_minutos: float = REINTENTO_MINUTOS
    reintento_en: datetime | None = None
    tiene_whatsapp: bool
    simular_no_atiende: bool = False
    pasos: list[PasoSecuencia]
    llamada_ids: list[str] = Field(default_factory=list)
    contacto_ids: list[str] = Field(default_factory=list)
    creada_en: datetime
    actualizada_en: datetime


class LlamadaDetalle(Llamada):
    """`GET /llamadas/{id}`: la llamada de siempre más campos opcionales de la secuencia de contacto."""

    intento: int | None = None
    atendida: bool | None = None
    audio_disponible_hasta: datetime | None = None  # llamadas reales: el audio se borra a los 60 días
    secuencia: SecuenciaContacto | None = None


ABIERTAS = ("en_curso", "reintento_programado")


def reintento_minutos() -> float:
    try:
        return max(float(os.environ.get("LLAMADA_REINTENTO_MINUTOS", "") or REINTENTO_MINUTOS), 0.0)
    except ValueError:
        return float(REINTENTO_MINUTOS)


def _espera_reintento_s(minutos: float, modo: str) -> float:
    if modo == "real":
        return minutos * 60
    return minutos * SEGUNDOS_SIMULADOS_POR_MINUTO * _escala()


def contacto_proveedor(proveedor_id: str) -> dict[str, Any]:
    """WhatsApp (sí/no) y email del proveedor: de data/historial_compras.json (datos de ejemplo del
    bloque 5) y, si no está, se deduce del canal preferido."""
    try:
        datos = store.semilla("historial_compras").get("contacto_proveedores", {}).get(proveedor_id) or {}
    except FileNotFoundError:
        datos = {}
    if "whatsapp" not in datos:
        canal = proveedores()[proveedor_id].canal_preferido if proveedor_id in proveedores() else ""
        datos = {**datos, "whatsapp": canal in ("whatsapp_texto", "whatsapp_audio", "foto")}
    return datos


def registrar_contacto(
    pedido_id: str, proveedor_id: str, canal: str, texto: str, motivo: MotivoContacto
) -> Contacto:
    contacto = Contacto(
        id=f"con_{uuid.uuid4().hex[:8]}",
        pedido_id=pedido_id,
        proveedor_id=proveedor_id,
        canal=canal,  # type: ignore[arg-type]
        texto=texto,
        enviado_en=datetime.now().replace(microsecond=0).isoformat(),
        motivo=motivo,
    )
    store.guardar("contactos", contacto)
    return contacto


def _guardar_secuencia(sec: SecuenciaContacto) -> None:
    sec.actualizada_en = datetime.now()
    store.guardar("secuencias", sec)


def _paso(sec: SecuenciaContacto, nombre: str) -> PasoSecuencia:
    return next(p for p in sec.pasos if p.paso == nombre)


def secuencia_de(llamada_id: str) -> SecuenciaContacto | None:
    return next(
        (SecuenciaContacto.model_validate(s) for s in store.valores("secuencias") if llamada_id in s.get("llamada_ids", [])),
        None,
    )


def secuencia_abierta(pedido_id: str, proveedor_id: str) -> SecuenciaContacto | None:
    return next(
        (s for s in store.listar("secuencias", SecuenciaContacto, pedido_id=pedido_id, proveedor_id=proveedor_id)
         if s.estado in ABIERTAS),
        None,
    )


def _nueva_secuencia(pedido_id: str, proveedor_id: str, simular_no_atiende: bool) -> SecuenciaContacto:
    ahora = datetime.now()
    return SecuenciaContacto(
        id=f"sec_{proveedor_id}_{uuid.uuid4().hex[:6]}",
        pedido_id=pedido_id,
        proveedor_id=proveedor_id,
        estado="en_curso",
        reintento_minutos=reintento_minutos(),
        tiene_whatsapp=bool(contacto_proveedor(proveedor_id).get("whatsapp")),
        simular_no_atiende=simular_no_atiende,
        pasos=[PasoSecuencia(paso=p) for p in ("llamada", "reintento", "whatsapp", "email")],
        creada_en=ahora,
        actualizada_en=ahora,
    )


def _respondio(pedido_id: str, proveedor_id: str) -> str | None:
    """Canal por el que ya respondió el proveedor (si respondió)."""
    m = next(
        (m for m in store.valores("mensajes") if m["pedido_id"] == pedido_id and m["proveedor_id"] == proveedor_id),
        None,
    )
    return m["canal"] if m else None


def _cerrar(sec: SecuenciaContacto, estado: str, detalle_resto: str) -> None:
    sec.estado = estado  # type: ignore[assignment]
    sec.reintento_en = None
    for p in sec.pasos:
        if p.estado in ("pendiente", "programado"):
            p.estado, p.detalle = "omitido", detalle_resto
    _guardar_secuencia(sec)


async def _continuar_secuencia(llamada: Llamada) -> None:
    """Después de cada llamada de cotización: decide el próximo paso de la secuencia."""
    if llamada.tipo != "cotizacion":
        return
    sec = secuencia_de(llamada.id)
    if sec is None or sec.estado not in ABIERTAS:
        return
    paso = _paso(sec, "llamada" if sec.intento == 1 else "reintento")
    paso.hecho_en = datetime.now()
    if llamada.estado == "terminada":
        paso.estado, paso.detalle = "atendida", "El proveedor atendió y pasó la cotización por teléfono."
        _cerrar(sec, "atendida", "No hizo falta: atendió la llamada.")
        return
    no_atendio = llamada.id in _no_atendidas
    if sec.intento == 1 and not no_atendio:  # falla técnica: no es "no atendió", no se reintenta solo
        paso.estado, paso.detalle = "error", llamada.error or "La llamada falló"
        _cerrar(sec, "interrumpida", "La primera llamada falló por un problema técnico.")
        return
    paso.estado = "no_atendida" if no_atendio else "error"
    paso.detalle = llamada.error or "El proveedor no atendió"
    if sec.intento == 1:
        _programar_reintento(sec, llamada.modo)
    else:
        await _avisar(sec)


def _programar_reintento(sec: SecuenciaContacto, modo: str) -> None:
    espera = _espera_reintento_s(sec.reintento_minutos, modo)
    sec.estado = "reintento_programado"
    sec.reintento_en = datetime.now() + timedelta(seconds=espera)
    paso = _paso(sec, "reintento")
    paso.estado, paso.programado_para = "programado", sec.reintento_en
    paso.detalle = f"Reintento a los {fmt(sec.reintento_minutos)} minutos" + (
        f" (simulado: {fmt(espera, 1)} s)" if modo != "real" else ""
    )
    _guardar_secuencia(sec)
    tarea = asyncio.create_task(_reintentar(sec.id, espera, modo))
    _reintentos[sec.id] = tarea
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)
    tarea.add_done_callback(lambda _t, sid=sec.id: _reintentos.pop(sid, None))
    log.info("Secuencia %s: reintento en %.1f s", sec.id, espera)


async def _reintentar(sec_id: str, espera: float, modo: str) -> None:
    await asyncio.sleep(espera)
    sec = store.obtener("secuencias", sec_id, SecuenciaContacto)
    if sec is None or sec.estado != "reintento_programado":
        return
    if (canal := _respondio(sec.pedido_id, sec.proveedor_id)) is not None:
        _paso(sec, "reintento").estado = "omitido"
        _cerrar(sec, "respondio", f"Ya respondió (canal {canal}) antes del reintento.")
        return
    pedido = pedidos.obtener(sec.pedido_id)
    try:
        await iniciar(
            pedido_id=sec.pedido_id,
            proveedor_id=sec.proveedor_id,
            tipo="cotizacion",
            variables=instrucciones_cotizacion(pedido, sec.proveedor_id),
            simulada=modo != "real",
            simular_no_atiende=sec.simular_no_atiende,
            _secuencia_id=sec.id,
        )
    except LlamadaNoPosible as exc:  # p. ej. se cambió la configuración entre la llamada y el reintento
        sec = store.obtener("secuencias", sec_id, SecuenciaContacto)
        if sec is None:
            return
        paso = _paso(sec, "reintento")
        paso.estado, paso.detalle, paso.hecho_en = "error", str(exc), datetime.now()
        sec.intento = 2
        await _avisar(sec)


def texto_aviso(pedido: Any, proveedor_id: str, canal: str) -> str:
    base = _variables_base(pedido, proveedor_id)
    lista = lista_pedido(pedido, proveedor_id)
    if canal == "whatsapp":
        return (
            f"Hola, ¿cómo va? Soy el asistente de inteligencia artificial de {base['negocio']}. "
            f"Te llamamos dos veces de parte de {base['comprador']} y no pudimos hablar: era para pedirte "
            f"cotización de:\n{lista}\n"
            "¿Nos pasás por acá el precio (aclarando si incluye IVA), el plazo de entrega, la forma de pago "
            "y el costo de envío? ¡Gracias!"
        )
    email = contacto_proveedor(proveedor_id).get("email") or "(sin email cargado)"
    return (
        f"Para: {email}\n"
        f"Asunto: Solicitud de cotización — {base['negocio']}\n\n"
        f"Hola, equipo de {base['proveedor_nombre']}:\n\n"
        f"Soy el asistente de inteligencia artificial de compras de {base['negocio']}. Los llamamos dos veces "
        f"de parte de {base['comprador']} sin poder comunicarnos, así que les enviamos la solicitud por esta vía.\n\n"
        f"Les pedimos cotización de:\n{lista}\n\n"
        "Para cada producto, ¿nos indican el precio unitario y en qué unidad cotizan, si incluye IVA, el plazo "
        "de entrega, la forma de pago, el costo de envío y la vigencia de la cotización?\n\n"
        f"Muchas gracias,\n{base['comprador']} · {base['negocio']}"
    )


async def _avisar(sec: SecuenciaContacto) -> None:
    """Tampoco atendió el reintento: WhatsApp con el motivo o, si no tiene, email con la solicitud."""
    if (canal_resp := _respondio(sec.pedido_id, sec.proveedor_id)) is not None:
        _cerrar(sec, "respondio", f"Ya respondió (canal {canal_resp}).")
        return
    pedido = pedidos.obtener(sec.pedido_id)
    canal = "whatsapp" if sec.tiene_whatsapp else "email"
    contacto = registrar_contacto(
        sec.pedido_id, sec.proveedor_id, canal, texto_aviso(pedido, sec.proveedor_id, canal), "aviso_no_atendio"
    )
    sec.contacto_ids.append(contacto.id)
    enviado = _paso(sec, canal)
    enviado.estado, enviado.contacto_id, enviado.hecho_en = "enviado", contacto.id, datetime.now()
    if canal == "whatsapp":
        enviado.detalle = "WhatsApp con el motivo del llamado (simulado)."
        _paso(sec, "email").estado, _paso(sec, "email").detalle = "omitido", "No hizo falta: se avisó por WhatsApp."
    else:
        enviado.detalle = "Email con la solicitud de cotización (simulado)."
        _paso(sec, "whatsapp").estado, _paso(sec, "whatsapp").detalle = "omitido", "El proveedor no tiene WhatsApp."
    sec.estado, sec.reintento_en = "aviso_enviado", None
    _guardar_secuencia(sec)
    log.info("Secuencia %s: aviso por %s (%s)", sec.id, canal, contacto.id)


def detalle(llamada: Llamada) -> LlamadaDetalle:
    sec = secuencia_de(llamada.id)
    intento = None
    if sec is not None:
        intento = 1 if sec.llamada_ids and sec.llamada_ids[0] == llamada.id else 2
    if llamada.estado == "terminada":
        atendida: bool | None = True
    elif llamada.id in _no_atendidas or (
        sec is not None and _paso(sec, "llamada" if intento == 1 else "reintento").estado == "no_atendida"
    ):
        atendida = False
    else:
        atendida = None
    return LlamadaDetalle(
        **llamada.model_dump(),
        intento=intento,
        atendida=atendida,
        audio_disponible_hasta=llamada.iniciada_en + timedelta(days=DIAS_AUDIO) if llamada.modo == "real" else None,
        secuencia=sec,
    )


# ---------------------------------------------------------------- entrada pública
def activa(pedido_id: str, proveedor_id: str) -> Llamada | None:
    return next(
        (l for l in store.listar("llamadas", Llamada, pedido_id=pedido_id, proveedor_id=proveedor_id)
         if l.estado in ACTIVAS),
        None,
    )


def _vincular_secuencia(llamada: Llamada, simular_no_atiende: bool, secuencia_id: str | None) -> None:
    """Toda llamada de cotización es un paso de una secuencia: la primera la crea; el reintento (o una
    llamada manual con el reintento programado, que lo adelanta) es el segundo intento."""
    sec = store.obtener("secuencias", secuencia_id, SecuenciaContacto) if secuencia_id else None
    if sec is None:
        sec = secuencia_abierta(llamada.pedido_id, llamada.proveedor_id)
        if sec is not None and sec.estado == "reintento_programado":
            if (tarea := _reintentos.pop(sec.id, None)) is not None:
                tarea.cancel()
        elif sec is None or sec.estado != "en_curso":
            sec = _nueva_secuencia(llamada.pedido_id, llamada.proveedor_id, simular_no_atiende)
    sec.intento = 1 if not sec.llamada_ids else 2
    sec.estado, sec.reintento_en = "en_curso", None
    sec.llamada_ids.append(llamada.id)
    paso = _paso(sec, "llamada" if sec.intento == 1 else "reintento")
    paso.estado, paso.llamada_id, paso.detalle = "en_curso", llamada.id, None
    _guardar_secuencia(sec)


async def iniciar(
    *,
    pedido_id: str,
    proveedor_id: str,
    tipo: str,
    variables: dict[str, str],
    negociacion_id: str | None = None,
    simulada: bool = False,
    simular_no_atiende: bool = False,
    _secuencia_id: str | None = None,
) -> Llamada:
    """Crea la llamada, la dispara (real) o la arranca (simulada) y la sigue en segundo plano.

    `simular_no_atiende` (solo simulada): suena y nadie atiende, en la llamada y en su reintento, para
    mostrar la secuencia de contacto entera.
    """
    if (en_curso := activa(pedido_id, proveedor_id)) is not None:
        return en_curso
    cfg = configuracion()
    modo = "simulada" if simulada or cfg.modo == "simulada" else "real"
    numero = (config.settings.telefonos_proveedores or {}).get(proveedor_id)
    if modo == "real":
        if cfg.faltan:
            raise LlamadaNoPosible("Faltan variables para llamar: " + ", ".join(cfg.faltan))
        if not numero:
            raise LlamadaNoPosible(
                f"No hay teléfono cargado para {proveedores()[proveedor_id].nombre} en TELEFONOS_PROVEEDORES"
            )
    llamada = Llamada(
        id=f"lla_{proveedor_id}_{uuid.uuid4().hex[:6]}",
        pedido_id=pedido_id,
        proveedor_id=proveedor_id,
        tipo=tipo,  # type: ignore[arg-type]
        negociacion_id=negociacion_id,
        modo=modo,  # type: ignore[arg-type]
        estado="iniciando",
        telefono=enmascarar(numero),
        iniciada_en=datetime.now(),
    )
    store.guardar("llamadas", llamada)
    if tipo == "cotizacion":
        _vincular_secuencia(llamada, simular_no_atiende and modo == "simulada", _secuencia_id)
    if modo == "real":
        try:
            datos = await _disparar(numero, variables)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            llamada.estado, llamada.error = "fallida", str(exc)
            store.guardar("llamadas", llamada)
            log.warning("No se pudo iniciar la llamada a %s: %s", proveedor_id, exc)
            await _continuar_secuencia(llamada)
            return llamada
        llamada.conversation_id = datos.get("conversation_id")
        llamada.call_sid = datos.get("callSid")
        if not llamada.conversation_id:
            llamada.estado, llamada.error = "fallida", "ElevenLabs no devolvió conversation_id"
            store.guardar("llamadas", llamada)
            await _continuar_secuencia(llamada)
            return llamada
    llamada.estado = "sonando"
    store.guardar("llamadas", llamada)
    if tipo == "negociacion":
        motivo: MotivoContacto = "negociacion"
    else:
        sec = secuencia_de(llamada.id)
        motivo = "reintento" if sec is not None and sec.intento == 2 else "solicitud_cotizacion"
    registrar_contacto(pedido_id, proveedor_id, "llamada", variables.get("primer_mensaje", ""), motivo)
    no_atiende = simular_no_atiende and modo == "simulada"
    tarea = asyncio.create_task(_seguir(llamada, variables, no_atiende))
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)
    log.info("Llamada %s (%s, %s) a %s", llamada.id, tipo, modo, llamada.telefono or proveedor_id)
    return llamada


def cancelar_todo() -> None:
    """Cancela las llamadas en seguimiento y los reintentos programados (POST /reset)."""
    for tarea in list(_tareas) + list(_reintentos.values()):
        tarea.cancel()
    _tareas.clear()
    _reintentos.clear()
    _no_atendidas.clear()
