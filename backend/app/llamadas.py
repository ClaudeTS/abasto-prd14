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
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

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
DURACION_MAXIMA_S = 15 * 60
ACTIVAS = ("iniciando", "sonando", "en_curso", "procesando")
_tareas: set[asyncio.Task] = set()


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


def instrucciones_cotizacion(pedido: Any, proveedor_id: str) -> dict[str, str]:
    """Variables dinámicas para pedir la cotización a quien no respondió."""
    base = _variables_base(pedido, proveedor_id)
    nombres = _nombres()
    vende = set(perfil_privado(proveedor_id).get("tabla_precios", {}))
    lineas = [l for l in pedido.lineas if not vende or l.producto_id in vende] or pedido.lineas
    unidades = {p.id: p.unidad_canonica for p in catalogo()}
    lista = "\n".join(
        f"- {fmt(l.cantidad)} {'litros' if unidades.get(l.producto_id) == 'l' else 'unidades'} "
        f"de {nombres[l.producto_id]} (para el {l.necesario_para.strftime('%d/%m')})"
        for l in lineas
    )
    instrucciones = (
        f"Llamás a {base['proveedor_nombre']} de parte de {base['comprador']}, de {base['negocio']}. "
        "Les pidieron cotización por WhatsApp y todavía no respondieron. Pedí precio de:\n"
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
            f"Hola, ¿hablo con {base['proveedor_nombre']}? Te llamo de parte de {base['comprador']}, "
            f"de {base['negocio']}, por la cotización que les pedimos por WhatsApp. ¿Tenés un minuto?"
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
            f"Hola, ¿hablo con {base['proveedor_nombre']}? Te llamo de parte de {base['comprador']}, "
            f"de {base['negocio']}, por la cotización de {nombres[asignado[0].producto_id].lower()}. "
            "¿Tenés un minuto?"
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
_SIN_ATENDER = {"busy": "ocupado", "no_answer": "no atendió", "failed": "la llamada falló"}


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
        llamada.error = f"El proveedor {_SIN_ATENDER.get(resultado_llamada, 'no pudo ser contactado')}"
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
    limite = time.time() + DURACION_MAXIMA_S
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


async def _seguir_simulada(llamada: Llamada, variables: dict[str, str]) -> None:
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


async def _seguir(llamada: Llamada, variables: dict[str, str]) -> None:
    try:
        if llamada.modo == "real":
            await _seguir_real(llamada)
        else:
            await _seguir_simulada(llamada, variables)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — el error queda en la llamada, la UI lo muestra
        log.exception("Falló el seguimiento de la llamada %s", llamada.id)
        llamada.estado, llamada.error = "fallida", str(exc)
    store.guardar("llamadas", llamada)
    await _al_terminar(llamada)
    log.info("Llamada %s %s (%s)", llamada.id, llamada.estado, llamada.modo)


# ---------------------------------------------------------------- entrada pública
def activa(pedido_id: str, proveedor_id: str) -> Llamada | None:
    return next(
        (l for l in store.listar("llamadas", Llamada, pedido_id=pedido_id, proveedor_id=proveedor_id)
         if l.estado in ACTIVAS),
        None,
    )


async def iniciar(
    *,
    pedido_id: str,
    proveedor_id: str,
    tipo: str,
    variables: dict[str, str],
    negociacion_id: str | None = None,
    simulada: bool = False,
) -> Llamada:
    """Crea la llamada, la dispara (real) o la arranca (simulada) y la sigue en segundo plano."""
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
    if modo == "real":
        try:
            datos = await _disparar(numero, variables)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            llamada.estado, llamada.error = "fallida", str(exc)
            store.guardar("llamadas", llamada)
            log.warning("No se pudo iniciar la llamada a %s: %s", proveedor_id, exc)
            return llamada
        llamada.conversation_id = datos.get("conversation_id")
        llamada.call_sid = datos.get("callSid")
        if not llamada.conversation_id:
            llamada.estado, llamada.error = "fallida", "ElevenLabs no devolvió conversation_id"
            store.guardar("llamadas", llamada)
            return llamada
    llamada.estado = "sonando"
    store.guardar("llamadas", llamada)
    tarea = asyncio.create_task(_seguir(llamada, variables))
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)
    log.info("Llamada %s (%s, %s) a %s", llamada.id, tipo, modo, llamada.telefono or proveedor_id)
    return llamada


def cancelar_todo() -> None:
    for tarea in list(_tareas):
        tarea.cancel()
    _tareas.clear()
