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
from app.models import Cotizacion, EstadoProveedor, MensajeCrudo
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


def responder_repregunta(cotizacion: Cotizacion) -> tuple[str, bool | None]:
    """Lo que contesta el proveedor simulado cuando el agente le repregunta una duda de su cotización.

    Sale de su lista de precios real, la misma con la que cotizó. Devuelve el texto de la respuesta y, si
    la duda era el IVA, si los precios lo incluyen (None si la respuesta no lo aclara).
    """
    prov = next((p for p in _proveedores_sim() if p["publico"]["id"] == cotizacion.proveedor_id), None)
    if "iva" not in cotizacion.campos_dudosos:
        return "Sí, los precios que te pasé están bien.", None
    tabla = prov["privado"].get("tabla_precios", {}) if prov else {}
    ivas = {bool(tabla[i.producto_id].get("incluye_iva")) for i in cotizacion.items if i.producto_id in tabla}
    if len(ivas) != 1:
        return "Depende del producto, después te paso el detalle.", None
    return ("Sí, todo con el IVA incluido.", True) if ivas.pop() else ("No, son más IVA.", False)


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


def _texto_visible(canal: str, contenido: str) -> str | None:
    """Texto que la UI muestra junto al archivo (y donde resalta las evidencias).

    PDF: el texto del presupuesto (para "Texto extraído del PDF"). Foto: nada, la lee el modelo.
    """
    if canal == "pdf":
        from app.archivos import html_a_texto

        return html_a_texto(contenido)
    if canal == "foto":
        return None
    return contenido


def _guardar_archivo(canal: str, contenido: str, mensaje_id: str) -> str | None:
    """Genera el PDF o la foto. Devuelve el nombre del archivo en runtime/archivos/."""
    from app import archivos  # import diferido: reportlab/PIL solo cuando hacen falta

    if canal == "pdf":
        nombre = f"{mensaje_id}.pdf"
        archivos.generar_pdf_presupuesto(contenido, config.settings.archivos_dir / nombre)
        store.subir_archivo(nombre)
        return nombre
    if canal == "foto":
        nombre = f"{mensaje_id}.jpg"
        archivos.generar_foto_presupuesto(contenido, config.settings.archivos_dir / nombre)
        store.subir_archivo(nombre)
        return nombre
    return None


# ---------------------------------------------------------------- tareas
async def _responder(pedido_id: str, prov: dict[str, Any], demora: float) -> None:
    pub = prov["publico"]
    await asyncio.sleep(demora)
    from app import llamadas  # import local: llamadas importa pipeline/pedidos, evita ciclos

    # Si Abasto lo está llamando, no mandar el WhatsApp encima de la llamada: esperar a que
    # termine. Si la llamada trajo la cotización, el chequeo de abajo lo saltea; si falló, responde.
    while llamadas.activa(pedido_id, pub["id"]) is not None:
        await asyncio.sleep(1)
    ya_respondio = any(
        m["pedido_id"] == pedido_id and m["proveedor_id"] == pub["id"] for m in store.valores("mensajes")
    )
    if ya_respondio:  # p. ej. Abasto lo llamó por teléfono antes de que contestara (llamadas.py)
        return
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
        contenido_texto=_texto_visible(canal, contenido),
        archivo=archivo,
        archivo_url=f"/archivos/{archivo}" if archivo else None,
        recibido_en=datetime.now(),
        estado="pendiente",
    )
    store.guardar("mensajes", mensaje)
    log.info("Llegó %s de %s (%s, origen %s)", canal, pub["id"], mensaje_id, origen)
    # Pausa en "leyendo…" para que el feed muestre el paso (la extracción fija es instantánea).
    await asyncio.sleep(0.3 * _escala())
    mensaje.estado = "leyendo"
    store.guardar("mensajes", mensaje)
    await asyncio.sleep(1.6 * _escala())
    try:
        await procesar_mensaje(mensaje)
    except Exception:  # noqa: BLE001 — el mensaje ya quedó en estado "error" con el motivo
        pass


async def _todas(pedido_id: str, tareas: list[asyncio.Task]) -> None:
    await asyncio.gather(*tareas, return_exceptions=True)
    pedido = pedidos.obtener(pedido_id)
    if pedido is not None and pedido.estado == "cotizando":  # no pisar "optimizado" (forzar=true)
        pedidos.cambiar_estado(pedido_id, "cotizado")
    log.info("Pedido %s cotizado", pedido_id)


def en_curso(pedido_id: str) -> bool:
    return any(not t.done() for t in _tareas.get(pedido_id, set()))


def _respuesta(estado: str, *, en_curso_ya: bool = False, ya_cotizado: bool = False) -> dict[str, Any]:
    """Misma forma siempre, para que el frontend no tenga que adivinar claves."""
    return {
        "estado": estado,
        "proveedores": len(_proveedores_sim()),
        "ya_estaba_en_curso": en_curso_ya,
        "ya_cotizado": ya_cotizado,
    }


def _lanzar(pedido_id: str, demoras: dict[str, float]) -> None:
    sims = {p["publico"]["id"]: p for p in _proveedores_sim()}
    tareas = [
        asyncio.create_task(_responder(pedido_id, sims[pid], demora)) for pid, demora in demoras.items()
    ]
    cierre = asyncio.create_task(_todas(pedido_id, tareas))
    _tareas[pedido_id] = {*tareas, cierre}


def _cancelar(pedido_id: str) -> None:
    for t in _tareas.pop(pedido_id, set()):
        t.cancel()


async def iniciar(pedido_id: str) -> dict[str, Any]:
    """Lanza las respuestas de todos los proveedores.

    Idempotente: si ya está corriendo o ya se cotizó, no relanza (para repetir: POST /reset).
    Si el runtime se borró por fuera (rm -rf con el server vivo), cancela las tareas huérfanas.
    """
    hay_registro = store.obtener_dict("simulaciones", pedido_id) is not None
    if en_curso(pedido_id):
        if hay_registro:
            return _respuesta("cotizando", en_curso_ya=True)
        _cancelar(pedido_id)  # tareas de un runtime que ya no existe
    pedido = pedidos.obtener(pedido_id)
    if hay_registro and pedido is not None and pedido.estado != "nuevo":
        return _respuesta(pedido.estado, ya_cotizado=True)
    inicio = time.time()
    demoras = {
        p["publico"]["id"]: demora_de(p["publico"]["id"], p["privado"].get("demora_factor", 1.0))
        for p in _proveedores_sim()
    }
    plan = {
        "pedido_id": pedido_id,
        "inicio": inicio,
        "proveedores": {pid: {"eta": inicio + d} for pid, d in demoras.items()},
    }
    store.guardar_dict("simulaciones", pedido_id, plan)
    pedidos.cambiar_estado(pedido_id, "cotizando")
    _lanzar(pedido_id, demoras)
    return _respuesta("cotizando")


def reanudar() -> None:
    """Al arrancar: relanza las respuestas que faltaban si el server se reinició cotizando."""
    ahora = time.time()
    for plan in store.valores("simulaciones"):
        if not plan or en_curso(plan["pedido_id"]):
            continue
        pedido = pedidos.obtener(plan["pedido_id"])
        if pedido is None or pedido.estado != "cotizando":
            continue
        respondieron = {
            m["proveedor_id"] for m in store.valores("mensajes") if m["pedido_id"] == pedido.id
        }
        faltan = {
            pid: max(datos["eta"] - ahora, 0.0)
            for pid, datos in plan["proveedores"].items()
            if pid not in respondieron
        }
        log.info("Reanudo la cotización de %s: faltan %s", pedido.id, sorted(faltan))
        _lanzar(pedido.id, faltan)
        trabados = [
            MensajeCrudo.model_validate(m)
            for m in store.valores("mensajes")
            if m["pedido_id"] == pedido.id and m["estado"] in ("pendiente", "leyendo")
        ]
        for mensaje in trabados:  # quedaron a medio leer cuando se cortó el server
            _tareas[pedido.id].add(asyncio.create_task(_reprocesar(mensaje)))


async def _reprocesar(mensaje: MensajeCrudo) -> None:
    try:
        await procesar_mensaje(mensaje)
    except Exception:  # noqa: BLE001 — queda en estado "error" con el motivo
        pass


def cancelar_todo() -> None:
    for pedido_id in list(_tareas):
        _cancelar(pedido_id)


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
