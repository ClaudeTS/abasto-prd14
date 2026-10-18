"""KPI del dashboard (PRD 1.4 §4, RF-09).

Cada KPI se calcula juntando dos fuentes:
- **Reales:** lo que hay en el store (corridas y órdenes del agente, cotizaciones, negociaciones,
  llamadas, simulaciones de cotización).
- **De ejemplo:** `data/historial_compras.json`, un histórico inventado y marcado como tal. Si un KPI
  usa al menos una observación de ejemplo, sale con `ejemplo: true` y la UI muestra "Datos de ejemplo".

Ningún número se inventa: si en el período no hay observaciones, el KPI vuelve con `valor: null`.
Las demoras del simulador de proveedores están comprimidas para la demo (`SIM_DELAY_SECONDS`), así que
no cuentan para los tiempos de respuesta de los proveedores; las llamadas simuladas reusan la
transcripción del gemelo, así que no cuentan para la precisión del gemelo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from app import store
from app.normalizacion import fmt

ClienteInterno = Literal["ventas", "personal"]
CanalContacto = Literal["llamada", "whatsapp", "email"]
CANALES: tuple[CanalContacto, ...] = ("llamada", "whatsapp", "email")
DIAS_POR_DEFECTO = 30
CLIENTE_POR_DEFECTO: ClienteInterno = "personal"  # el pedido de la demo es consumo interno de Tecnova
NOTA_EJEMPLO = (
    "Los KPI marcados como «Datos de ejemplo» se completan con un histórico inventado "
    "(data/historial_compras.json) hasta que haya meses de uso real."
)


# ---------------------------------------------------------------- modelos de salida
class Meta(BaseModel):
    texto: str  # "±2 pp" | "A definir"
    valor: float | None = None
    cumple: bool | None = None


class Fuentes(BaseModel):
    reales: int = 0
    ejemplo: int = 0


class TiempoCanal(BaseModel):
    canal: CanalContacto
    minutos: float | None
    muestras: int
    ejemplo: bool


class KPI(BaseModel):
    id: str
    nombre: str
    valor: float | None
    unidad: Literal["%", "h", "min", "pp"]
    detalle: str | None = None
    como_se_calcula: str
    meta: Meta | None = None  # None: "A definir" con la línea base del primer mes
    ejemplo: bool
    fuentes: Fuentes
    valor_anterior: float | None = None  # mismo cálculo en el período anterior de igual largo
    mejor_si: Literal["mayor", "menor"] | None = None
    por_canal: list[TiempoCanal] | None = None


class Pendiente(BaseModel):
    id: str
    tipo: Literal["orden", "negociacion"]
    titulo: str
    detalle: str
    pedido_id: str
    proveedor_id: str
    monto_sin_iva: float | None = None
    enlace: str


class Dashboard(BaseModel):
    desde: date
    hasta: date
    cliente_interno: ClienteInterno | None
    generado_en: datetime
    kpis: list[KPI]
    tiempo_por_canal: list[TiempoCanal]
    pendientes: list[Pendiente]
    ejemplo: bool
    nota_ejemplo: str


# ---------------------------------------------------------------- utilidades
def _dt(valor: Any) -> datetime | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(valor)).replace(tzinfo=None)
    except ValueError:
        return None


@dataclass(frozen=True)
class Periodo:
    desde: date
    hasta: date
    cliente: ClienteInterno | None = None

    def incluye(self, fecha: datetime | None, cliente: str | None) -> bool:
        if fecha is None or not (self.desde <= fecha.date() <= self.hasta):
            return False
        return self.cliente is None or cliente == self.cliente

    def anterior(self) -> "Periodo":
        largo = (self.hasta - self.desde).days + 1
        return Periodo(self.desde - timedelta(days=largo), self.desde - timedelta(days=1), self.cliente)


def periodo(desde: date | None, hasta: date | None, cliente: ClienteInterno | None) -> Periodo:
    hasta = hasta or date.today()
    desde = desde or hasta - timedelta(days=DIAS_POR_DEFECTO - 1)
    if desde > hasta:
        raise ValueError("«desde» no puede ser posterior a «hasta»")
    return Periodo(desde, hasta, cliente)


def historial() -> dict[str, Any]:
    return store.semilla("historial_compras")


def _proveedores() -> dict[str, dict[str, Any]]:
    return {p["publico"]["id"]: p["publico"] for p in store.semilla("proveedores_sim")["proveedores"]}


def nombre_proveedor(proveedor_id: str) -> str:
    return _proveedores().get(proveedor_id, {}).get("nombre", proveedor_id)


def nombres_productos() -> dict[str, str]:
    return {p["id"]: p["nombre"] for p in store.semilla("pedido_demo")["catalogo"]}


def canal_de(canal: str) -> CanalContacto:
    """Canal del mensaje del proveedor → canal de contacto (WhatsApp, email o llamada)."""
    if canal == "llamada":
        return "llamada"
    if canal == "pdf":  # el presupuesto en PDF llega por email
        return "email"
    return "whatsapp"  # texto, audio y foto llegan por WhatsApp


def _cliente_pedido(pedido_id: str) -> str:
    pedido = store.obtener_dict("pedidos", pedido_id) or {}
    return pedido.get("cliente_interno") or CLIENTE_POR_DEFECTO


def _pct(parte: float, total: float) -> float | None:
    return round(parte / total * 100, 1) if total else None


def _prom(valores: list[float], decimales: int = 1) -> float | None:
    return round(sum(valores) / len(valores), decimales) if valores else None


# ---------------------------------------------------------------- observaciones
@dataclass
class _Obs:
    fecha: datetime
    cliente: str | None
    ejemplo: bool
    datos: dict[str, Any] = field(default_factory=dict)


def _corridas() -> list[dict[str, Any]]:
    return store.valores("agentes")


def _negociacion_llamada() -> dict[tuple[str, str], dict[str, Any]]:
    """Resultado de la última llamada de negociación terminada, por (pedido, proveedor)."""
    salida: dict[tuple[str, str], dict[str, Any]] = {}
    for l in sorted(store.valores("llamadas"), key=lambda x: x.get("iniciada_en") or ""):
        if l.get("tipo") == "negociacion" and l.get("estado") == "terminada":
            salida[(l["pedido_id"], l["proveedor_id"])] = l
    return salida


def _primera_asignacion(pedido_id: str, proveedor_id: str) -> dict[str, Any] | None:
    plan = store.obtener_dict("planes", pedido_id)
    if not plan:
        return None
    return next((a for a in plan.get("asignaciones", []) if a["proveedor_id"] == proveedor_id), None)


def obs_ordenes() -> list[_Obs]:
    """Una observación por línea de orden emitida (para ahorro) con datos de la orden."""
    obs: list[_Obs] = []
    negociadas = _negociacion_llamada()
    for c in _corridas():
        cliente = _cliente_pedido(c["pedido_id"])
        creada = _dt(c.get("creada_en"))
        for o in c.get("ordenes", []):
            if o.get("estado") != "enviada_simulada":
                continue
            emitida = _dt(o.get("enviada_en"))
            llamada = negociadas.get((c["pedido_id"], o["proveedor_id"]))
            primera = _primera_asignacion(c["pedido_id"], o["proveedor_id"])
            acordado = ((llamada or {}).get("resultado") or {}).get("precio_acordado")
            for n, linea in enumerate(o.get("lineas", [])):
                inicial = float(linea["precio_unitario_sin_iva"])
                final = inicial
                if acordado and primera and primera["producto_id"] == linea["producto_id"]:
                    final = float(acordado)
                obs.append(_Obs(emitida, cliente, False, {
                    "orden": o["numero"], "auto": o.get("aprobada_por") == "agente",
                    "horas": ((emitida - creada).total_seconds() / 3600) if emitida and creada else None,
                    "inicial": inicial * float(linea["cantidad"]), "final": final * float(linea["cantidad"]),
                    "primera_linea": n == 0,
                }))
    # Negociaciones por teléfono de la demo guiada (sin corrida del agente): el ahorro sobre el plan.
    con_orden = {(c["pedido_id"], o["proveedor_id"]) for c in _corridas() for o in c.get("ordenes", [])}
    for (pedido_id, proveedor_id), l in negociadas.items():
        acordado = (l.get("resultado") or {}).get("precio_acordado")
        primera = _primera_asignacion(pedido_id, proveedor_id)
        if (pedido_id, proveedor_id) in con_orden or not acordado or not primera:
            continue
        cantidad = float(primera["cantidad"])
        obs.append(_Obs(_dt(l.get("iniciada_en")), _cliente_pedido(pedido_id), False, {
            "orden": None, "auto": None, "horas": None, "primera_linea": False,
            "inicial": float(primera["precio_unitario_sin_iva"]) * cantidad,
            "final": float(acordado) * cantidad,
        }))
    for o in historial()["ordenes"]:
        obs.append(_Obs(_dt(o["emitida_en"]), o["cliente_interno"], True, {
            "orden": o["numero"], "auto": o["emitida_por"] == "agente",
            "horas": (_dt(o["emitida_en"]) - _dt(o["pedido_creado_en"])).total_seconds() / 3600,
            "inicial": o["precio_cotizacion_inicial"] * o["cantidad"],
            "final": o["precio_unitario_sin_iva"] * o["cantidad"],
            "primera_linea": True,  # en el histórico cada orden tiene una línea
        }))
    return obs


def obs_cotizaciones() -> list[_Obs]:
    mensajes = {m["id"]: m for m in store.valores("mensajes")}
    obs = []
    for c in store.valores("cotizaciones"):
        if c.get("pedido_id") == "pruebas":
            continue
        fecha = _dt((mensajes.get(c.get("mensaje_id")) or {}).get("recibido_en")) or datetime.now()
        obs.append(_Obs(fecha, _cliente_pedido(c["pedido_id"]), False, {
            "sin_correccion": c.get("estado", "valida") == "valida",
            "para_revisar": c.get("estado") == "revisar",
        }))
    pedidos_hist = {p["id"]: p for p in historial()["pedidos"]}
    for c in historial()["cotizaciones"]:
        obs.append(_Obs(_dt(c["fecha"]), pedidos_hist[c["pedido_id"]]["cliente_interno"], True, {
            "sin_correccion": not c["corregida"], "para_revisar": False,
        }))
    return obs


def obs_negociaciones() -> list[_Obs]:
    obs = []
    negociaciones = {n["id"]: n for n in store.valores("negociaciones")}
    for (pedido_id, proveedor_id), l in _negociacion_llamada().items():
        resultado = l.get("resultado") or {}
        neg = negociaciones.get(l.get("negociacion_id") or "") or {}
        elegida = next((e for e in neg.get("estrategias", []) if e.get("nombre") == neg.get("elegida")), None)
        primera = _primera_asignacion(pedido_id, proveedor_id)
        acordado = resultado.get("precio_acordado")
        real = None
        if acordado and primera and float(primera["precio_unitario_sin_iva"]):
            base = float(primera["precio_unitario_sin_iva"])
            real = max(0.0, (base - float(acordado)) / base * 100)
        mejora = bool(resultado.get("acuerdo")) or (real is not None and real > 0)
        obs.append(_Obs(_dt(l.get("iniciada_en")), _cliente_pedido(pedido_id), False, {
            "mejora": mejora,
            "simulada": float(elegida["concesion_obtenida_pct"]) if elegida else None,
            "real": real,
            "cuenta_para_gemelo": l.get("modo") == "real",  # la simulada repite al gemelo
        }))
    pedidos_hist = {p["id"]: p for p in historial()["pedidos"]}
    for n in historial()["negociaciones"]:
        obs.append(_Obs(_dt(n["fecha"]), pedidos_hist[n["pedido_id"]]["cliente_interno"], True, {
            "mejora": n["mejora"], "simulada": n["concesion_simulada_pct"],
            "real": n["concesion_real_pct"], "cuenta_para_gemelo": True,
        }))
    return obs


def obs_respuestas() -> list[_Obs]:
    """Una observación por (pedido, proveedor) al que se le pidió cotización."""
    obs = []
    respondieron: dict[str, set[str]] = {}
    for m in store.valores("mensajes"):
        respondieron.setdefault(m["pedido_id"], set()).add(m["proveedor_id"])
    for sim in store.valores("simulaciones"):
        if not sim:
            continue
        fecha = datetime.fromtimestamp(sim["inicio"])
        cliente = _cliente_pedido(sim["pedido_id"])
        for proveedor_id in sim.get("proveedores", {}):
            obs.append(_Obs(fecha, cliente, False, {
                "proveedor_id": proveedor_id,
                "respondio": proveedor_id in respondieron.get(sim["pedido_id"], set()),
            }))
    pedidos_hist = {p["id"]: p for p in historial()["pedidos"]}
    pares: dict[tuple[str, str], _Obs] = {}
    for c in historial()["contactos"]:
        clave = (c["pedido_id"], c["proveedor_id"])
        o = pares.setdefault(clave, _Obs(_dt(c["enviado_en"]), pedidos_hist[c["pedido_id"]]["cliente_interno"], True,
                                         {"proveedor_id": c["proveedor_id"], "respondio": False}))
        o.datos["respondio"] = o.datos["respondio"] or c["respondido_en"] is not None
    return obs + list(pares.values())


def obs_tiempos_canal() -> list[_Obs]:
    """Minutos de respuesta por proveedor y canal. Solo llamadas reales y el histórico de ejemplo."""
    obs = []
    for l in store.valores("llamadas"):
        if l.get("modo") == "real" and l.get("tipo") == "cotizacion" and l.get("mensaje_id") and l.get("duracion_segundos"):
            obs.append(_Obs(_dt(l["iniciada_en"]), _cliente_pedido(l["pedido_id"]), False, {
                "proveedor_id": l["proveedor_id"], "canal": "llamada", "minutos": l["duracion_segundos"] / 60,
            }))
    pedidos_hist = {p["id"]: p for p in historial()["pedidos"]}
    for c in historial()["contactos"]:
        if c["respondido_en"] is None:
            continue
        minutos = (_dt(c["respondido_en"]) - _dt(c["enviado_en"])).total_seconds() / 60
        obs.append(_Obs(_dt(c["enviado_en"]), pedidos_hist[c["pedido_id"]]["cliente_interno"], True, {
            "proveedor_id": c["proveedor_id"], "canal": c["canal"], "minutos": minutos,
        }))
    return obs


def obs_pedidos_internos() -> list[_Obs]:
    """Minutos desde que llega la solicitud (voz o email) hasta que el pedido está completo."""
    obs = []
    for c in _corridas():
        if not c.get("texto"):
            continue
        pasos = {p["id"]: p for p in c.get("pasos", [])}
        confirmar, inventario = pasos.get("confirmar", {}), pasos.get("inventario", {})
        fin = _dt(confirmar.get("fin")) if confirmar.get("estado") == "hecho" else None
        if fin is None and confirmar.get("estado") == "omitido":
            fin = _dt(inventario.get("fin"))
        inicio = _dt(c.get("creada_en"))
        if fin and inicio:
            obs.append(_Obs(inicio, _cliente_pedido(c["pedido_id"]), False,
                            {"minutos": (fin - inicio).total_seconds() / 60}))
    for p in historial()["pedidos"]:
        if p["solicitud_recibida_en"]:
            inicio, fin = _dt(p["solicitud_recibida_en"]), _dt(p["creado_en"])
            obs.append(_Obs(inicio, p["cliente_interno"], True, {"minutos": (fin - inicio).total_seconds() / 60}))
    return obs


# ---------------------------------------------------------------- cálculo
def _fuentes(obs: list[_Obs]) -> Fuentes:
    return Fuentes(reales=sum(not o.ejemplo for o in obs), ejemplo=sum(o.ejemplo for o in obs))


def _filtrar(obs: list[_Obs], per: Periodo) -> list[_Obs]:
    return [o for o in obs if per.incluye(o.fecha, o.cliente)]


def _kpi_automaticas(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    ordenes = {}
    for o in obs:
        if o.datos["orden"] and o.datos["primera_linea"]:
            ordenes[(o.ejemplo, o.datos["orden"])] = o
    usadas = list(ordenes.values())
    auto = sum(o.datos["auto"] for o in usadas)
    valor = _pct(auto, len(usadas))
    n = len(usadas)
    return valor, (f"{auto} de {n} {'orden' if n == 1 else 'órdenes'}" if usadas else None), usadas


def _kpi_ahorro(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    inicial = sum(o.datos["inicial"] for o in obs)
    final = sum(o.datos["final"] for o in obs)
    valor = _pct(inicial - final, inicial)
    return valor, (f"$ {fmt(inicial - final)} en el período" if obs else None), obs


def _kpi_tiempo_orden(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    usadas = [o for o in obs if o.datos["orden"] and o.datos["primera_linea"] and o.datos["horas"] is not None]
    valor = _prom([o.datos["horas"] for o in usadas])
    n = len(usadas)
    return valor, (f"promedio de {n} {'orden' if n == 1 else 'órdenes'}" if usadas else None), usadas


def _kpi_cotizaciones(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    ok = sum(o.datos["sin_correccion"] for o in obs)
    revisar = sum(o.datos["para_revisar"] for o in obs)
    detalle = f"{ok} de {len(obs)} cotizaciones" + (f" · {revisar} para revisar" if revisar else "")
    return _pct(ok, len(obs)), (detalle if obs else None), obs


def _kpi_gemelo(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    usadas = [o for o in obs if o.datos["cuenta_para_gemelo"] and o.datos["simulada"] is not None and o.datos["real"] is not None]
    valor = _prom([abs(o.datos["simulada"] - o.datos["real"]) for o in usadas])
    n = len(usadas)
    return valor, (f"{n} {'negociación comparada' if n == 1 else 'negociaciones comparadas'}" if usadas else None), usadas


def _kpi_efectividad(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    mejora = sum(o.datos["mejora"] for o in obs)
    return _pct(mejora, len(obs)), (f"{mejora} de {len(obs)} con mejora" if obs else None), obs


def _kpi_respuesta(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    si = sum(o.datos["respondio"] for o in obs)
    return _pct(si, len(obs)), (f"{si} de {len(obs)} solicitudes respondidas" if obs else None), obs


def tiempos_por_canal(obs: list[_Obs]) -> list[TiempoCanal]:
    salida = []
    for canal in CANALES:
        del_canal = [o for o in obs if o.datos["canal"] == canal]
        salida.append(TiempoCanal(
            canal=canal, minutos=_prom([o.datos["minutos"] for o in del_canal]),
            muestras=len(del_canal), ejemplo=any(o.ejemplo for o in del_canal),
        ))
    return salida


def _kpi_canal(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    canales = [t for t in tiempos_por_canal(obs) if t.minutos is not None]
    if not canales:
        return None, None, obs
    rapido = min(canales, key=lambda t: t.minutos or 0)
    nombres = {"llamada": "llamada", "whatsapp": "WhatsApp", "email": "email"}
    return rapido.minutos, f"el más rápido es {nombres[rapido.canal]}", obs


def _kpi_internos(obs: list[_Obs]) -> tuple[float | None, str | None, list[_Obs]]:
    valor = _prom([o.datos["minutos"] for o in obs])
    return valor, ("de la nota de voz o el email al pedido completo" if obs else None), obs


_DEFINICIONES = (
    # id, nombre, unidad, mejor_si, cómo se calcula, observaciones, cálculo, meta
    ("tasa_compras_automaticas", "Tasa de compras automáticas", "%", "mayor",
     "Órdenes emitidas por compra automática ÷ órdenes emitidas en el período.", obs_ordenes, _kpi_automaticas),
    ("ahorro_cotizacion_inicial", "Ahorro contra la cotización inicial", "%", "mayor",
     "(Primera cotización − precio final acordado) ÷ primera cotización, ponderado por monto, sobre las líneas compradas.",
     obs_ordenes, _kpi_ahorro),
    ("tiempo_pedido_a_orden", "Tiempo del pedido a la orden", "h", "menor",
     "Promedio de horas entre la creación del pedido y la emisión de la orden de compra.", obs_ordenes, _kpi_tiempo_orden),
    ("cotizaciones_sin_correccion", "Cotizaciones sin corrección", "%", "mayor",
     "Cotizaciones leídas que no requirieron corrección humana ÷ cotizaciones recibidas (las que esperan revisión cuentan como corrección).",
     obs_cotizaciones, _kpi_cotizaciones),
    ("precision_gemelo", "Precisión del gemelo digital", "pp", "menor",
     "Diferencia promedio, en puntos porcentuales, entre la concesión ensayada con el gemelo y la obtenida en la negociación real. Las llamadas simuladas no cuentan: repiten el ensayo.",
     obs_negociaciones, _kpi_gemelo),
    ("efectividad_negociacion", "Efectividad de negociación", "%", "mayor",
     "Negociaciones con mejora de precio o condiciones ÷ negociaciones con resultado conocido.",
     obs_negociaciones, _kpi_efectividad),
    ("tasa_respuesta_proveedores", "Tasa de respuesta de proveedores", "%", "mayor",
     "Proveedores que respondieron la solicitud de cotización ÷ proveedores contactados (por pedido).",
     obs_respuestas, _kpi_respuesta),
    ("tiempo_respuesta_por_canal", "Tiempo de respuesta del proveedor por canal", "min", "menor",
     "Promedio de minutos entre el contacto y la respuesta, separado por canal. Las respuestas del simulador no cuentan: sus demoras están comprimidas para la demo.",
     obs_tiempos_canal, _kpi_canal),
    ("tiempo_respuesta_pedidos_internos", "Tiempo de respuesta a pedidos internos", "min", "menor",
     "Promedio de minutos entre la recepción de la nota de voz o el email y el pedido completo.",
     obs_pedidos_internos, _kpi_internos),
)


def _meta(kpi_id: str, valor: float | None) -> Meta | None:
    if kpi_id == "precision_gemelo":
        return Meta(texto="±2 pp", valor=2.0, cumple=None if valor is None else valor <= 2.0)
    return None  # a definir con la línea base del primer mes (PRD §14, pregunta 5)


def calcular(per: Periodo) -> list[KPI]:
    kpis = []
    anterior = per.anterior()
    cache: dict[Any, list[_Obs]] = {}
    for kpi_id, nombre, unidad, mejor_si, como, fuente, calculo in _DEFINICIONES:
        todas = cache.setdefault(fuente, fuente())
        valor, detalle, usadas = calculo(_filtrar(todas, per))
        previo, _, _ = calculo(_filtrar(todas, anterior))
        kpis.append(KPI(
            id=kpi_id, nombre=nombre, valor=valor, unidad=unidad, detalle=detalle, como_se_calcula=como,
            meta=_meta(kpi_id, valor), ejemplo=any(o.ejemplo for o in usadas), fuentes=_fuentes(usadas),
            valor_anterior=previo, mejor_si=mejor_si,
            por_canal=tiempos_por_canal(usadas) if kpi_id == "tiempo_respuesta_por_canal" else None,
        ))
    return kpis


# ---------------------------------------------------------------- pendientes de aprobación
def pendientes(cliente: ClienteInterno | None = None) -> list[Pendiente]:
    """Lo que espera al administrador ahora (solo datos reales: no hay pendientes de ejemplo)."""
    nombres = nombres_productos()
    salida = []
    for c in _corridas():
        if c.get("estado") in ("cancelada", "error"):
            continue
        if cliente and _cliente_pedido(c["pedido_id"]) != cliente:
            continue
        for o in c.get("ordenes", []):
            if o.get("estado") != "esperando_aprobacion":
                continue
            productos = ", ".join(l["nombre_corto"] for l in o.get("lineas", []))
            motivo = "; ".join(m.rstrip(". ") for m in o.get("motivos", [])) or "Requiere tu aprobación"
            motivo += "."
            salida.append(Pendiente(
                id=f"orden:{c['id']}:{o['id']}", tipo="orden",
                titulo=f"{o['numero']} · {o['proveedor_nombre']} · {productos}",
                detalle=f"$ {fmt(o['total_sin_iva'])} + IVA. {motivo}",
                pedido_id=c["pedido_id"], proveedor_id=o["proveedor_id"],
                monto_sin_iva=float(o["total_sin_iva"]), enlace=f"/pedidos/{c['pedido_id']}",
            ))
    for n in store.valores("negociaciones"):
        if n.get("estado") != "simulada":
            continue
        if cliente and _cliente_pedido(n["pedido_id"]) != cliente:
            continue
        elegida = next((e for e in n.get("estrategias", []) if e.get("nombre") == n.get("elegida")), None)
        primera = _primera_asignacion(n["pedido_id"], n["proveedor_id"])
        producto = nombres.get(primera["producto_id"], "") if primera else ""
        detalle = f"Estrategia «{n['elegida']}» ensayada con el gemelo"
        if elegida:
            detalle += f": −{fmt(elegida['concesion_obtenida_pct'], 1)} %, unos $ {fmt(elegida['ganancia_esperada_uyu'])}"
        salida.append(Pendiente(
            id=f"negociacion:{n['id']}", tipo="negociacion",
            titulo=f"Negociación con {nombre_proveedor(n['proveedor_id'])}" + (f" · {producto}" if producto else ""),
            detalle=detalle + ". Espera tu aprobación.",
            pedido_id=n["pedido_id"], proveedor_id=n["proveedor_id"],
            monto_sin_iva=float(elegida["ganancia_esperada_uyu"]) if elegida else None, enlace="/negociacion",
        ))
    return salida


def dashboard(per: Periodo) -> Dashboard:
    kpis = calcular(per)
    canal = next(k for k in kpis if k.id == "tiempo_respuesta_por_canal")
    return Dashboard(
        desde=per.desde, hasta=per.hasta, cliente_interno=per.cliente, generado_en=datetime.now(),
        kpis=kpis, tiempo_por_canal=canal.por_canal or [], pendientes=pendientes(per.cliente),
        ejemplo=any(k.ejemplo for k in kpis), nota_ejemplo=NOTA_EJEMPLO,
    )
