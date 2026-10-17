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
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import config, integracion_a, pedidos, pipeline, simulador, store
from app.models import (
    AprobacionNegociacion,
    ConfirmacionCotizacion,
    Cotizacion,
    EstadoProveedor,
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
    log.info(
        "Abasto backend · datos en %s · SIM_MODE=%s · extracción=%s · SIM_DELAY_SECONDS=%s",
        config.settings.data_dir,
        config.settings.sim_mode,
        pipeline.modo_extraccion(),
        config.settings.sim_delay_seconds,
    )
    yield
    simulador.cancelar_todo()


app = FastAPI(title="Abasto API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- errores con forma única
@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    cuerpo = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail), "detalle": None}
    return JSONResponse(status_code=exc.status_code, content=cuerpo)


@app.exception_handler(RequestValidationError)
async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"error": "Datos de entrada inválidos", "detalle": exc.errors()}
    )


@app.exception_handler(Exception)
async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Error no controlado")
    return JSONResponse(
        status_code=500, content={"error": "Error interno del backend", "detalle": str(exc)}
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
    return pipeline.confirmar(cot, (cuerpo or ConfirmacionCotizacion()).incluye_iva)


@app.post("/extraer", response_model=Cotizacion)
async def extraer(
    proveedor_id: str = Form(...),
    canal: str = Form("whatsapp_texto"),
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
    mensaje = MensajeCrudo(
        id=mensaje_id,
        pedido_id=pedido_id,
        proveedor_id=proveedor_id,
        canal=canal,  # type: ignore[arg-type]
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
    if ruta.parent != base or not ruta.is_file():
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
    texto_llm = await integracion_a.explicar(optimizacion.datos_para_explicar(plan, provs, nombres))
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


# ---------------------------------------------------------------- reset
@app.post("/reset")
async def reset(hard: bool = Query(False, description="También borra el cache")) -> dict:
    simulador.cancelar_todo()
    store.reset(borrar_cache=hard)
    return {"ok": True, "cache_borrado": hard}
