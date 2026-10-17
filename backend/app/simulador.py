"""Proveedores simulados (rol C). ARQUITECTURA §8.

`POST /pedidos/{id}/cotizar` lanza una tarea por proveedor: espera su demora, genera la respuesta en
su canal (texto, audio transcripto, PDF o foto), guarda el `MensajeCrudo` y dispara la extracción.

Modos (`SIM_MODE`):
- `fijo` (default): respuestas de data/respuestas_fijas.json. Determinístico: la demo sale igual siempre.
- `llm`: genera con el prompt `proveedor_responde` usando `app.llm.completar` (rol A) y cachea en
  backend/data/cache/ la primera respuesta por (pedido, proveedor). Si falla, cae al fixture.

Demoras: las de los fixtures (`demora_segundos`, la papelera tarda 40 s) escaladas por
`SIM_DELAY_SECONDS / 4`. Con SIM_DELAY_SECONDS=0 todo llega al instante (tests).
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import time
import uuid
from datetime import datetime
from typing import Any

from app import config, pedidos, store
from app.models import EstadoProveedor, MensajeCrudo
from app.pipeline import catalogo, procesar_mensaje
from app.pipeline import proveedores as proveedores_publicos

log = logging.getLogger("abasto.simulador")
_tareas: dict[str, set[asyncio.Task]] = {}
_PROMPT = config.BACKEND_DIR / "app" / "prompts" / "proveedor_responde.md"


def _escala() -> float:
    return max(config.settings.sim_delay_seconds, 0.0) / 4.0


def _fixtures() -> dict[str, dict[str, Any]]:
    return {r["proveedor_id"]: r for r in store.semilla("respuestas_fijas")["respuestas"]}


def _proveedores_sim() -> list[dict[str, Any]]:
    return store.semilla("proveedores_sim")["proveedores"]


def demora_de(proveedor_id: str, demora_factor: float) -> float:
    fijo = _fixtures().get(proveedor_id)
    base = fijo["demora_segundos"] if fijo else 4.0 * demora_factor
    return base * _escala()


# ---------------------------------------------------------------- generación de contenido
def _render_prompt(variables: dict[str, str]) -> tuple[str, str]:
    texto = _PROMPT.read_text(encoding="utf-8").split("-->", 1)[-1]
    for clave, valor in variables.items():
        texto = texto.replace("{{" + clave + "}}", valor)
    system, user = texto.split("=== USER ===", 1)
    return system.strip(), user.strip()


def _variables_prompt(prov: dict[str, Any], pedido: Any) -> dict[str, str]:
    pub, pri = prov["publico"], prov["privado"]
    nombres = {p.id: p.nombre for p in catalogo()}
    lineas = "\n".join(
        f"- {nombres[l.producto_id]}: {l.cantidad:g}" for l in pedido.lineas
    )  # se le pide todo a todos; cada uno cotiza lo suyo, como en la vida real
    tabla = "\n".join(
        f"- {pid}: {v['moneda']} {v['precio']} por {v['unidad']}"
        f"{' IVA incluido' if v['incluye_iva'] else ' + IVA'}"
        f"{', mínimo ' + str(v['cantidad_minima']) if v.get('cantidad_minima') else ''}"
        for pid, v in pri["tabla_precios"].items()
    )
    return {
        "nombre": pub["nombre"],
        "rubro": pub["rubro"],
        "personalidad": pri["personalidad"],
        "muletillas": pri["muletillas"],
        "canal": pub["canal_preferido"],
        "tabla_precios": tabla,
        "envio": pri["envio"],
        "pedido_minimo": pri["pedido_minimo"],
        "plazo_pago": pri["plazo_pago"],
        "lead_time": pri["lead_time"],
        "habitos": pri["habitos"],
        "negocio": pedido.negocio,
        "comprador": pedido.comprador or "compras",
        "pedido_para_este_proveedor": lineas,
        "fecha": pedido.fecha.isoformat(),
        "fecha_necesaria": min(l.necesario_para for l in pedido.lineas).isoformat(),
    }


async def generar_contenido(prov: dict[str, Any], pedido: Any) -> tuple[str, str]:
    """Devuelve (contenido, origen 'fijo'|'cache'|'llm')."""
    pid = prov["publico"]["id"]
    fijo = _fixtures().get(pid, {}).get("contenido")
    if config.settings.sim_mode != "llm":
        if fijo is None:
            raise RuntimeError(f"No hay respuesta fija para {pid}")
        return fijo, "fijo"
    clave = f"sim_{pedido.id}_{pid}"
    if (en_cache := store.cache_leer(clave)) is not None:
        return en_cache["contenido"], "cache"
    try:
        llm = importlib.import_module("app.llm")
        system, user = _render_prompt(_variables_prompt(prov, pedido))
        contenido = await llm.completar(system, user, temperature=0.7, max_tokens=900)
    except Exception as exc:  # noqa: BLE001 — sin LLM la demo sigue con el fixture
        if fijo is None:
            raise
        log.warning("Simulador LLM falló para %s (%s); uso fixture", pid, exc)
        return fijo, "fijo"
    store.cache_guardar(clave, {"contenido": contenido})
    return contenido, "llm"


def _guardar_archivo(canal: str, contenido: str, mensaje_id: str) -> str | None:
    """Genera el PDF o la foto. Devuelve el nombre del archivo en runtime/archivos/."""
    from app import archivos  # import diferido: reportlab/PIL solo cuando hacen falta

    if canal == "pdf":
        nombre = f"{mensaje_id}.pdf"
        archivos.generar_pdf_presupuesto(contenido, config.settings.archivos_dir / nombre)
        return nombre
    if canal == "foto":
        nombre = f"{mensaje_id}.jpg"
        archivos.generar_foto_presupuesto(contenido, config.settings.archivos_dir / nombre)
        return nombre
    return None


# ---------------------------------------------------------------- tareas
async def _responder(pedido_id: str, prov: dict[str, Any], demora: float) -> None:
    pub = prov["publico"]
    await asyncio.sleep(demora)
    pedido = pedidos.obtener(pedido_id)
    contenido, origen = await generar_contenido(prov, pedido)
    mensaje_id = f"msg_{pub['id']}_{uuid.uuid4().hex[:6]}"
    canal = pub["canal_preferido"]
    archivo = await asyncio.to_thread(_guardar_archivo, canal, contenido, mensaje_id)
    mensaje = MensajeCrudo(
        id=mensaje_id,
        pedido_id=pedido_id,
        proveedor_id=pub["id"],
        canal=canal,
        contenido_texto=None if canal in ("pdf", "foto") else contenido,
        archivo=archivo,
        archivo_url=f"/archivos/{archivo}" if archivo else None,
        recibido_en=datetime.now(),
        estado="pendiente",
    )
    store.guardar("mensajes", mensaje)
    log.info("Llegó %s de %s (%s, origen %s)", canal, pub["id"], mensaje_id, origen)
    # Pausa corta en "leyendo…" para que el feed muestre el paso (la extracción fija es instantánea).
    await asyncio.sleep(1.6 * _escala())
    try:
        await procesar_mensaje(mensaje)
    except Exception:  # noqa: BLE001 — el mensaje ya quedó en estado "error" con el motivo
        pass


async def _todas(pedido_id: str, tareas: list[asyncio.Task]) -> None:
    await asyncio.gather(*tareas, return_exceptions=True)
    pedidos.cambiar_estado(pedido_id, "cotizado")
    log.info("Pedido %s cotizado", pedido_id)


def en_curso(pedido_id: str) -> bool:
    return any(not t.done() for t in _tareas.get(pedido_id, set()))


async def iniciar(pedido_id: str) -> dict[str, Any]:
    """Lanza las respuestas de todos los proveedores. Idempotente mientras está cotizando."""
    if en_curso(pedido_id):
        return {"estado": "cotizando", "ya_estaba_en_curso": True}
    inicio = time.time()
    plan: dict[str, Any] = {"inicio": inicio, "proveedores": {}}
    tareas = []
    for prov in _proveedores_sim():
        pid = prov["publico"]["id"]
        demora = demora_de(pid, prov["privado"].get("demora_factor", 1.0))
        plan["proveedores"][pid] = {"eta": inicio + demora}
        tareas.append(asyncio.create_task(_responder(pedido_id, prov, demora)))
    store.guardar_dict("simulaciones", pedido_id, plan)
    pedidos.cambiar_estado(pedido_id, "cotizando")
    cierre = asyncio.create_task(_todas(pedido_id, tareas))
    _tareas[pedido_id] = {*tareas, cierre}
    return {"estado": "cotizando", "proveedores": len(tareas)}


def cancelar_todo() -> None:
    for tareas in _tareas.values():
        for t in tareas:
            t.cancel()
    _tareas.clear()


def estado_proveedores(pedido_id: str) -> list[EstadoProveedor]:
    plan = store.obtener_dict("simulaciones", pedido_id) or {"proveedores": {}}
    respondieron = {
        m["proveedor_id"] for m in store.valores("mensajes") if m["pedido_id"] == pedido_id
    }
    ahora = time.time()
    salida = []
    for pid, prov in proveedores_publicos().items():
        eta = plan["proveedores"].get(pid, {}).get("eta")
        if pid in respondieron:
            estado, falta = "respondio", None
        elif eta is None:
            estado, falta = "sin_pedido", None
        else:
            estado, falta = "esperando", round(max(eta - ahora, 0.0), 1)
        salida.append(
            EstadoProveedor(
                proveedor_id=pid,
                nombre=prov.nombre,
                canal=prov.canal_preferido,
                estado=estado,
                responde_en_segundos=falta,
            )
        )
    return salida
