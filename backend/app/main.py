"""API de Abasto (rol C). Endpoints de docs/ARQUITECTURA.md §4 + extensiones de CONTRATO_BACKEND.md.

Errores: siempre `{"error": "mensaje legible", "detalle": ...}` con su código 4xx/5xx.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config, integracion_a, llamadas, pedidos, pipeline, simulador, store
from app.models import (
    AprobacionNegociacion,
    Canal,
    ConfigLlamadas,
    ConfirmacionCotizacion,
    Cotizacion,
    EstadoProveedor,
    Llamada,
    LlamarNegociacion,
    MensajeCrudo,
    Negociacion,
    PedidoCompleto,
    Plan,
    Proveedor,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s · %(message)s")
log = logging.getLogger("abasto.api")
TIMEOUT_NEGOCIACION_S = 90


class ErrorAbasto(HTTPException):
    def __init__(self, status: int, error: str, detalle: object = None) -> None:
        super().__init__(status_code=status, detail={"error": error, "detalle": detalle})


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    simulador.reanudar()  # si el server se reinició a mitad de una cotización (--reload)
    log.info(
        "Abasto backend · datos en %s · SIM_MODE=%s · extracción=%s · SIM_DELAY_SECONDS=%s",
        config.settings.data_dir,
        config.settings.sim_mode,
        pipeline.modo_extraccion(),
        config.settings.sim_delay_seconds,
    )
    yield
    simulador.cancelar_todo()
    llamadas.cancelar_todo()


app = FastAPI(title="Abasto API", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------- errores con forma única
@app.middleware("http")
async def _inesperado(request: Request, call_next):
    """Captura los 500 DENTRO del middleware de CORS (registrado después, queda por fuera):
    así el navegador recibe el error con sus headers y el frontend puede mostrar `error`."""
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001
        log.exception("Error no controlado en %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"error": "Error interno del backend", "detalle": str(exc)}
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)  # incluye 404/405 de rutas inexistentes
async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    cuerpo = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail), "detalle": None}
    return JSONResponse(status_code=exc.status_code, content=cuerpo)


@app.exception_handler(RequestValidationError)
async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "Datos de entrada inválidos", "detalle": jsonable_encoder(exc.errors())},
    )


# ---------------------------------------------------------------- helpers
def _pedido(pedido_id: str):
    pedido = pedidos.obtener(pedido_id)
    if pedido is None:
        raise ErrorAbasto(404, f"No existe el pedido '{pedido_id}'")
    return pedido


def _cotizaciones(pedido_id: str) -> list[Cotizacion]:
    return sorted(
        store.listar("cotizaciones", Cotizacion, pedido_id=pedido_id), key=lambda c: c.proveedor_id
    )


def _nombres_productos() -> dict[str, str]:
    return {p.id: p.nombre for p in pipeline.catalogo()}


# ---------------------------------------------------------------- básicos
@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "sim_mode": config.settings.sim_mode,
        "extraccion": pipeline.modo_extraccion(),
        "llm_model": config.settings.llm_model,
        "api_key": bool(config.settings.anthropic_api_key),
    }


@app.get("/pedidos/demo", response_model=PedidoCompleto)
async def pedido_demo() -> PedidoCompleto:
    return pedidos.completo(_pedido(pedidos.PEDIDO_DEMO_ID))


@app.get("/pedidos/{pedido_id}", response_model=PedidoCompleto)
async def pedido(pedido_id: str) -> PedidoCompleto:
    return pedidos.completo(_pedido(pedido_id))


@app.get("/proveedores", response_model=list[Proveedor])
async def listar_proveedores() -> list[Proveedor]:
    return list(pipeline.proveedores().values())


# ---------------------------------------------------------------- Capa 1: cotizar y extraer
@app.post("/pedidos/{pedido_id}/cotizar")
async def cotizar(pedido_id: str) -> dict:
    _pedido(pedido_id)
    return await simulador.iniciar(pedido_id)


@app.get("/pedidos/{pedido_id}/mensajes", response_model=list[MensajeCrudo])
async def mensajes(pedido_id: str) -> list[MensajeCrudo]:
    _pedido(pedido_id)
    return sorted(
        store.listar("mensajes", MensajeCrudo, pedido_id=pedido_id), key=lambda m: m.recibido_en
    )


@app.get("/pedidos/{pedido_id}/proveedores/estado", response_model=list[EstadoProveedor])
async def estado_proveedores(pedido_id: str) -> list[EstadoProveedor]:
    _pedido(pedido_id)
    return simulador.estado_proveedores(pedido_id)


@app.get("/pedidos/{pedido_id}/cotizaciones", response_model=list[Cotizacion])
async def cotizaciones(pedido_id: str) -> list[Cotizacion]:
    _pedido(pedido_id)
    return _cotizaciones(pedido_id)


@app.post("/cotizaciones/{cotizacion_id}/confirmar", response_model=Cotizacion)
async def confirmar_cotizacion(
    cotizacion_id: str, cuerpo: ConfirmacionCotizacion | None = None
) -> Cotizacion:
    cot = store.obtener("cotizaciones", cotizacion_id, Cotizacion)
    if cot is None:
        raise ErrorAbasto(404, f"No existe la cotización '{cotizacion_id}'")
    cuerpo = cuerpo or ConfirmacionCotizacion()
    if cuerpo.campo is not None and cuerpo.campo != "iva":
        raise ErrorAbasto(
            422, f"Todavía no se puede confirmar el campo '{cuerpo.campo}'; solo 'iva'"
        )
    incluye_iva = cuerpo.iva()
    if "iva" in cot.campos_dudosos and incluye_iva is None:
        raise ErrorAbasto(
            422,
            "Falta indicar si los precios incluyen IVA",
            {"esperado": {"incluye_iva": "true | false"}},
        )
    try:
        nueva = pipeline.confirmar(cot, incluye_iva)
    except KeyError as exc:
        raise ErrorAbasto(409, "No se encontró la extracción original de esta cotización") from exc
    if store.obtener_dict("planes", cot.pedido_id) is not None:  # el plan quedó viejo
        store.guardar_dict("planes", cot.pedido_id, None)
        pedidos.cambiar_estado(cot.pedido_id, "cotizado")
    return nueva


@app.post("/extraer", response_model=Cotizacion)
async def extraer(
    proveedor_id: str = Form(...),
    canal: Canal = Form("whatsapp_texto"),
    texto: str | None = Form(None),
    archivo: UploadFile | None = File(None),
    pedido_id: str = Form("pruebas"),
) -> Cotizacion:
    """Extracción directa (pruebas del rol A y uso manual). No toca el feed de la demo."""
    if proveedor_id not in pipeline.proveedores():
        raise ErrorAbasto(404, f"Proveedor desconocido '{proveedor_id}'")
    if pipeline.modo_extraccion() != "llm":
        fijo = next(
            (r for r in store.semilla("respuestas_fijas")["respuestas"]
             if r["proveedor_id"] == proveedor_id),
            None,
        )
        if not (texto and fijo and texto.strip() == fijo["contenido"].strip()):
            raise ErrorAbasto(
                503,
                "La extracción de texto libre necesita la Capa 1 con LLM "
                "(app/extraccion.py + ANTHROPIC_API_KEY). Sin eso solo acepta los mensajes fijos.",
                {"modo_extraccion": pipeline.modo_extraccion()},
            )
    mensaje_id = f"msg_{proveedor_id}_{uuid.uuid4().hex[:6]}"
    nombre_archivo = None
    if archivo is not None:
        sufijo = Path(archivo.filename or "").suffix.lower() or ".bin"
        nombre_archivo = f"{mensaje_id}{sufijo}"
        destino = config.settings.archivos_dir / nombre_archivo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(await archivo.read())
        store.subir_archivo(nombre_archivo)
    mensaje = MensajeCrudo(
        id=mensaje_id,
        pedido_id=pedido_id,
        proveedor_id=proveedor_id,
        canal=canal,
        contenido_texto=texto,
        archivo=nombre_archivo,
        archivo_url=f"/archivos/{nombre_archivo}" if nombre_archivo else None,
        recibido_en=datetime.now(),
        estado="pendiente",
    )
    store.guardar("mensajes", mensaje)
    try:
        return await pipeline.procesar_mensaje(mensaje)
    except pipeline.ExtraccionNoDisponible as exc:
        raise ErrorAbasto(503, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise ErrorAbasto(502, "No se pudo extraer la cotización", str(exc)) from exc


@app.get("/archivos/{nombre}")
async def archivo(nombre: str) -> FileResponse:
    base = config.settings.archivos_dir.resolve()
    ruta = (base / nombre).resolve()
    if ruta.parent != base or not store.asegurar_archivo(nombre):  # con Postgres, lo baja si falta
        raise ErrorAbasto(404, f"No existe el archivo '{nombre}'")
    return FileResponse(ruta)


# ---------------------------------------------------------------- Capa 4: plan
@app.post("/pedidos/{pedido_id}/optimizar", response_model=Plan)
async def optimizar(
    pedido_id: str,
    forzar: bool = Query(False, description="Optimizar igual con respuestas pendientes o a revisar"),
) -> Plan:
    from app import optimizacion

    pedido = _pedido(pedido_id)
    cots = _cotizaciones(pedido_id)
    esperando = [e.nombre for e in simulador.estado_proveedores(pedido_id) if e.estado == "esperando"]
    if esperando and (not forzar or not cots):
        raise ErrorAbasto(
            409, f"Faltan respuestas de: {', '.join(esperando)}", {"esperando": esperando}
        )
    if not cots:
        raise ErrorAbasto(409, "Todavía no hay cotizaciones. Primero hay que cotizar.")
    if not forzar:
        a_revisar = [c for c in cots if c.estado == "revisar"]
        if a_revisar:
            provs = pipeline.proveedores()
            raise ErrorAbasto(
                409,
                "Hay cotizaciones para revisar antes de optimizar: "
                + ", ".join(f"{provs[c.proveedor_id].nombre} ({', '.join(c.campos_dudosos)})" for c in a_revisar),
                {"revisar": [{"cotizacion_id": c.id, "proveedor_id": c.proveedor_id,
                              "campos_dudosos": c.campos_dudosos} for c in a_revisar]},
            )
    provs = pipeline.proveedores()
    nombres = _nombres_productos()
    tc = float(pipeline.datos_pedido()["config"]["tipo_cambio_usd"])
    plan = await asyncio.to_thread(
        optimizacion.optimizar, pedido, cots, provs, tipo_cambio_usd=tc, nombres_productos=nombres
    )
    datos = optimizacion.datos_para_explicar(
        plan, provs, nombres, habitual_id=pedido.proveedor_habitual_id
    )
    texto_llm = await integracion_a.explicar(datos)
    if texto_llm:
        plan.explicacion, plan.explicacion_origen = texto_llm, "llm"
    store.guardar_dict("planes", pedido_id, plan.model_dump(mode="json"))
    pedidos.cambiar_estado(pedido_id, "optimizado")
    return plan


@app.get("/pedidos/{pedido_id}/plan", response_model=Plan)
async def obtener_plan(pedido_id: str) -> Plan:
    plan = store.obtener_dict("planes", pedido_id)
    if plan is None:
        raise ErrorAbasto(404, "Todavía no hay plan para este pedido")
    return Plan.model_validate(plan)


# ---------------------------------------------------------------- Capa 5: negociación
@app.post("/pedidos/{pedido_id}/negociar/{proveedor_id}", response_model=Negociacion)
async def negociar(pedido_id: str, proveedor_id: str) -> Negociacion:
    pedido = _pedido(pedido_id)
    if proveedor_id not in pipeline.proveedores():
        raise ErrorAbasto(404, f"Proveedor desconocido '{proveedor_id}'")
    plan_dict = store.obtener_dict("planes", pedido_id)
    if plan_dict is None:
        raise ErrorAbasto(409, "Primero hay que optimizar el pedido")
    try:
        contexto = integracion_a.construir_contexto(
            pedido,
            Plan.model_validate(plan_dict),
            _cotizaciones(pedido_id),
            pipeline.proveedores(),
            pipeline.perfil_privado(proveedor_id),
            proveedor_id,
            _nombres_productos(),
        )
    except (KeyError, ValueError) as exc:
        raise ErrorAbasto(409, f"No se puede negociar con '{proveedor_id}': {exc}") from exc
    pedidos.cambiar_estado(pedido_id, "negociando")
    try:
        neg = await asyncio.wait_for(integracion_a.negociar(contexto), TIMEOUT_NEGOCIACION_S)
    except integracion_a.CapaNoDisponible as exc:
        pedidos.cambiar_estado(pedido_id, "optimizado")
        raise ErrorAbasto(501, str(exc), {"contexto": contexto.model_dump(mode="json")}) from exc
    except asyncio.TimeoutError as exc:
        pedidos.cambiar_estado(pedido_id, "optimizado")
        raise ErrorAbasto(504, f"La negociación tardó más de {TIMEOUT_NEGOCIACION_S} s") from exc
    except Exception as exc:  # noqa: BLE001 — p. ej. LLMError de app/llm.py: mensaje legible
        pedidos.cambiar_estado(pedido_id, "optimizado")
        log.exception("La negociación ensayada falló")
        raise ErrorAbasto(502, f"La negociación ensayada falló: {exc}") from exc
    store.guardar("negociaciones", neg)
    return neg


@app.get("/negociaciones/{negociacion_id}", response_model=Negociacion)
async def obtener_negociacion(negociacion_id: str) -> Negociacion:
    neg = store.obtener("negociaciones", negociacion_id, Negociacion)
    if neg is None:
        raise ErrorAbasto(404, f"No existe la negociación '{negociacion_id}'")
    return neg


@app.post("/negociaciones/{negociacion_id}/aprobar", response_model=Negociacion)
async def aprobar(negociacion_id: str, cuerpo: AprobacionNegociacion | None = None) -> Negociacion:
    neg = store.obtener("negociaciones", negociacion_id, Negociacion)
    if neg is None:
        raise ErrorAbasto(404, f"No existe la negociación '{negociacion_id}'")
    if cuerpo and cuerpo.mensaje and cuerpo.mensaje.strip():
        neg.mensaje_propuesto = cuerpo.mensaje.strip()  # Lucía lo editó antes de aprobar
    neg.estado = "enviada_simulada"  # nada sale de verdad: envío simulado (AGENTS §2)
    store.guardar("negociaciones", neg)
    pedidos.cambiar_estado(neg.pedido_id, "aprobado")
    log.info("Negociación %s aprobada y 'enviada' (simulado)", neg.id)
    return neg


# ---------------------------------------------------------------- llamadas (docs/LLAMADAS.md)
@app.get("/llamadas/config", response_model=ConfigLlamadas)
async def config_llamadas() -> ConfigLlamadas:
    return llamadas.configuracion()


@app.post("/pedidos/{pedido_id}/llamar/{proveedor_id}", response_model=Llamada)
async def llamar_para_cotizar(
    pedido_id: str,
    proveedor_id: str,
    simulada: bool = Query(False, description="Forzar llamada simulada (respaldo en vivo)"),
) -> Llamada:
    """Llama al proveedor para pedirle la cotización (p. ej. el que no respondió)."""
    pedido = _pedido(pedido_id)
    if proveedor_id not in pipeline.proveedores():
        raise ErrorAbasto(404, f"Proveedor desconocido '{proveedor_id}'")
    ya = [m for m in store.listar("mensajes", MensajeCrudo, pedido_id=pedido_id, proveedor_id=proveedor_id)]
    if ya and llamadas.activa(pedido_id, proveedor_id) is None:
        raise ErrorAbasto(409, f"{pipeline.proveedores()[proveedor_id].nombre} ya respondió")
    try:
        return await llamadas.iniciar(
            pedido_id=pedido_id,
            proveedor_id=proveedor_id,
            tipo="cotizacion",
            variables=llamadas.instrucciones_cotizacion(pedido, proveedor_id),
            simulada=simulada,
        )
    except llamadas.LlamadaNoPosible as exc:
        raise ErrorAbasto(409, str(exc), {"config": llamadas.configuracion().model_dump()}) from exc


@app.post("/negociaciones/{negociacion_id}/llamar", response_model=Llamada)
async def llamar_para_negociar(
    negociacion_id: str,
    cuerpo: LlamarNegociacion | None = None,
    simulada: bool = Query(False, description="Forzar llamada simulada (respaldo en vivo)"),
) -> Llamada:
    """"Aprobar y llamar": Lucía aprueba la estrategia y el mensaje; el agente llama con eso."""
    neg = store.obtener("negociaciones", negociacion_id, Negociacion)
    if neg is None:
        raise ErrorAbasto(404, f"No existe la negociación '{negociacion_id}'")
    plan_dict = store.obtener_dict("planes", neg.pedido_id)
    if plan_dict is None:
        raise ErrorAbasto(409, "El plan cambió: volvé a optimizar y a negociar")
    if cuerpo and cuerpo.mensaje and cuerpo.mensaje.strip():
        neg.mensaje_propuesto = cuerpo.mensaje.strip()
    try:
        variables = llamadas.instrucciones_negociacion(
            _pedido(neg.pedido_id), neg, Plan.model_validate(plan_dict), neg.mensaje_propuesto
        )
        llamada = await llamadas.iniciar(
            pedido_id=neg.pedido_id,
            proveedor_id=neg.proveedor_id,
            tipo="negociacion",
            variables=variables,
            negociacion_id=neg.id,
            simulada=simulada,
        )
    except llamadas.LlamadaNoPosible as exc:
        raise ErrorAbasto(409, str(exc), {"config": llamadas.configuracion().model_dump()}) from exc
    neg.estado, neg.llamada_id = "aprobada", llamada.id  # aprobada por Lucía al apretar "llamar"
    store.guardar("negociaciones", neg)
    log.info("Negociación %s aprobada para llamar (%s)", neg.id, llamada.modo)
    return llamada


@app.get("/llamadas/{llamada_id}", response_model=Llamada)
async def obtener_llamada(llamada_id: str) -> Llamada:
    llamada = store.obtener("llamadas", llamada_id, Llamada)
    if llamada is None:
        raise ErrorAbasto(404, f"No existe la llamada '{llamada_id}'")
    return llamada


@app.get("/pedidos/{pedido_id}/llamadas", response_model=list[Llamada])
async def llamadas_del_pedido(pedido_id: str) -> list[Llamada]:
    _pedido(pedido_id)
    return sorted(store.listar("llamadas", Llamada, pedido_id=pedido_id), key=lambda l: l.iniciada_en)


# ---------------------------------------------------------------- reset
@app.post("/reset")
async def reset(hard: bool = Query(False, description="También borra el cache")) -> dict:
    simulador.cancelar_todo()
    llamadas.cancelar_todo()
    store.reset(borrar_cache=hard)
    return {"ok": True, "cache_borrado": hard}
