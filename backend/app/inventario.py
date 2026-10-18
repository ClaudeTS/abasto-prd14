"""Inventario de la empresa y reposición (agente de compras, docs/AGENTE.md).

Stock, stock mínimo, consumo de 24 meses, modo automático o manual y tope por producto, en
data/inventario_demo.json; lo que Lucía cambia desde la UI queda en la colección "inventario".

El pronóstico se calcula en código, no con el LLM: nivel (promedio de los últimos 12 meses) por
índice estacional del mes (su promedio en los años del historial contra el promedio de todo el
historial). Los dos se redondean antes de multiplicar, así la cuenta que muestra la UI da exacto.
Reposición = pronóstico del horizonte + mínimo − stock − en camino, redondeada hacia arriba al
múltiplo de compra. Cada número lleva su cuenta en `evidencia`.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app import pipeline, store
from app.models import Monto
from app.normalizacion import fmt

Modo = Literal["automatico", "manual"]
DIAS_POR_MES = 30
MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MESES_LARGOS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


class ConsumoMes(BaseModel):
    mes: str  # "2025-11"
    cantidad: float


class MesPronostico(BaseModel):
    mes: str
    indice: float
    cantidad: float


class Pronostico(BaseModel):
    nivel: float  # promedio mensual de los últimos 12 meses
    consumo_diario: float  # nivel / 30
    meses: list[MesPronostico]
    total: float
    evidencia: str


class Reposicion(BaseModel):
    cantidad: float  # a comprar; 0 si no hace falta
    necesario_para: date
    cobertura_dias: int | None  # días hasta tocar el mínimo; None si ya está por debajo
    evidencia: str


class ProveedorRef(BaseModel):
    id: str
    nombre: str


class ItemInventario(BaseModel):
    producto_id: str
    nombre: str
    nombre_corto: str  # para frases: "resmas", "tóner"
    unidad: str
    tipo: Literal["consumible", "equipamiento"]
    stock_actual: float
    stock_minimo: float
    en_camino: float
    multiplo_compra: float
    modo: Modo
    tope_automatico_uyu: Monto | None  # sin IVA; None = sin tope
    proveedores: list[ProveedorRef]
    historial: list[ConsumoMes]
    pronostico: Pronostico | None  # None: equipamiento, se compra cuando se pide
    reposicion: Reposicion | None
    alerta: Literal["bajo_minimo", "reponer"] | None


class Inventario(BaseModel):
    fecha: date  # la del pedido: "hoy" en la demo
    horizonte_meses: int
    meses_pronostico: list[str]
    plazo_minimo_dias: int
    productos: list[ItemInventario]


class CambioInventario(BaseModel):
    """PATCH /inventario/{producto_id}: solo los campos que vienen. tope null = sin tope."""

    modo: Modo | None = None
    tope_automatico_uyu: float | None = None
    stock_actual: float | None = None
    stock_minimo: float | None = None


class InventarioError(ValueError):
    """Dato inválido (producto inexistente, número negativo, horizonte fuera de rango)."""


# ---------------------------------------------------------------- datos
def _semilla() -> dict[str, Any]:
    return store.semilla("inventario_demo")


def fecha_hoy() -> date:
    return date.fromisoformat(pipeline.datos_pedido()["pedido"]["fecha"])


def horizonte_por_defecto() -> int:
    return int(_semilla().get("horizonte_meses", 1))


def _producto(producto_id: str) -> dict[str, Any]:
    """Los datos del producto con los cambios de Lucía encima."""
    base = next((p for p in _semilla()["productos"] if p["producto_id"] == producto_id), None)
    if base is None:
        raise InventarioError(f"No hay inventario para '{producto_id}'")
    return {**base, **(store.obtener_dict("inventario", producto_id) or {})}


def cambiar(producto_id: str, cambio: CambioInventario) -> ItemInventario:
    _producto(producto_id)
    campos = cambio.model_dump(include=cambio.model_fields_set)
    for clave in ("tope_automatico_uyu", "stock_actual", "stock_minimo"):
        if campos.get(clave) is not None and campos[clave] < 0:
            raise InventarioError(f"{clave} no puede ser negativo")
    if "modo" in campos and campos["modo"] is None:
        raise InventarioError("modo tiene que ser 'automatico' o 'manual'")
    store.guardar_dict("inventario", producto_id, {**(store.obtener_dict("inventario", producto_id) or {}), **campos})
    return item(producto_id, horizonte_por_defecto())


# ---------------------------------------------------------------- pronóstico
def _redondear(valor: float | Decimal, cuanto: str) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal(cuanto), rounding=ROUND_HALF_UP)


def _meses_siguientes(hoy: date, n: int) -> list[str]:
    """Los n meses calendario después del de hoy: la compra mensual cubre el mes que viene."""
    salida, anio, mes = [], hoy.year, hoy.month
    for _ in range(n):
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        salida.append(f"{anio}-{mes:02d}")
    return salida


def _mes_corto(mes: str) -> str:
    anio, m = mes.split("-")
    return f"{MESES_ES[int(m) - 1]}-{anio[2:]}"


def pronosticar(consumo: dict[str, float], meses: list[str]) -> Pronostico:
    historial = sorted(consumo.items())
    valores = [v for _, v in historial]
    ultimos = historial[-12:]
    nivel = _redondear(sum(v for _, v in ultimos) / len(ultimos), "0.1")
    promedio = sum(valores) / len(valores)
    filas, cuentas = [], []
    for mes in meses:
        del_mes = [v for m, v in historial if m[-2:] == mes[-2:]]
        indice = _redondear((sum(del_mes) / len(del_mes)) / promedio, "0.01") if del_mes else Decimal(1)
        cantidad = _redondear(nivel * indice, "1")
        filas.append(MesPronostico(mes=mes, indice=float(indice), cantidad=float(cantidad)))
        nombre = MESES_LARGOS[int(mes[-2:]) - 1]
        cuentas.append(f"{nombre}: {fmt(nivel, 1)} × índice {fmt(indice, 2)} = {fmt(cantidad)}")
    total = sum(f.cantidad for f in filas)
    evidencia = (
        f"Promedio de los últimos 12 meses ({_mes_corto(ultimos[0][0])} a {_mes_corto(ultimos[-1][0])}): "
        f"{fmt(nivel, 1)} por mes. El índice de cada mes es su promedio en el historial contra el promedio "
        f"de los {len(valores)} meses. " + "; ".join(cuentas) + "."
    )
    if len(filas) > 1:
        evidencia += f" Total: {fmt(total)}."
    return Pronostico(
        nivel=float(nivel),
        consumo_diario=float(_redondear(nivel / DIAS_POR_MES, "0.01")),
        meses=filas,
        total=total,
        evidencia=evidencia,
    )


def _multiplo(cantidad: float, multiplo: float) -> float:
    if cantidad <= 0:
        return 0.0
    return math.ceil(round(cantidad / multiplo, 9)) * multiplo


def reponer(
    *,
    pronostico: Pronostico,
    stock: float,
    minimo: float,
    en_camino: float,
    multiplo: float,
    unidad: str,
    hoy: date,
    plazo_minimo_dias: int,
) -> Reposicion:
    disponible = stock + en_camino
    falta = pronostico.total + minimo - disponible
    cantidad = _multiplo(falta, multiplo)
    u = " L" if unidad == "l" else ""
    cuenta = f"Pronóstico {fmt(pronostico.total)} + mínimo {fmt(minimo)} − stock {fmt(stock)}"
    if en_camino:
        cuenta += f" − en camino {fmt(en_camino)}"
    cuenta += f" = {fmt(falta)}{u}"
    if cantidad and cantidad != falta:
        cuenta += f" → {fmt(cantidad)}{u} (se compra de a {fmt(multiplo)})"
    if cantidad <= 0:
        cuenta += ": alcanza, no hay que comprar"
    plazo = hoy + timedelta(days=plazo_minimo_dias)
    if disponible < minimo:
        cobertura, necesario = None, plazo
        cuando = f"Ya está bajo el mínimo: lo antes posible, el {necesario:%d/%m} ({plazo_minimo_dias} días)."
    else:
        cobertura = math.floor((disponible - minimo) / pronostico.consumo_diario) if pronostico.consumo_diario else None
        necesario = max(hoy + timedelta(days=cobertura or 0), plazo)
        cuando = (
            f"Con {fmt(pronostico.consumo_diario, 2)} por día, llega al mínimo en {cobertura} días: "
            f"para el {necesario:%d/%m}."
            if cobertura is not None
            else f"Para el {necesario:%d/%m}."
        )
    return Reposicion(
        cantidad=cantidad,
        necesario_para=necesario,
        cobertura_dias=cobertura,
        evidencia=f"{cuenta}. {cuando}",
    )


# ---------------------------------------------------------------- inventario completo
def en_camino() -> dict[str, float]:
    """Lo que está en órdenes ya enviadas (simuladas) por el agente."""
    total: dict[str, float] = {}
    for corrida in store.valores("agentes"):
        for orden in corrida.get("ordenes", []):
            if orden.get("estado") == "enviada_simulada":
                for linea in orden["lineas"]:
                    total[linea["producto_id"]] = total.get(linea["producto_id"], 0.0) + linea["cantidad"]
    return total


def item(producto_id: str, horizonte_meses: int, *, camino: dict[str, float] | None = None) -> ItemInventario:
    datos = _producto(producto_id)
    catalogo = {p.id: p for p in pipeline.catalogo()}
    provs = pipeline.proveedores()
    hoy = fecha_hoy()
    plazo = int(_semilla().get("plazo_minimo_dias", 3))
    camino = en_camino() if camino is None else camino
    producto = catalogo[producto_id]
    consumo = datos.get("consumo_mensual") or {}
    pron = pronosticar(consumo, _meses_siguientes(hoy, horizonte_meses)) if consumo else None
    stock, minimo = float(datos["stock_actual"]), float(datos["stock_minimo"])
    llegando = camino.get(producto_id, 0.0)
    repo = (
        reponer(
            pronostico=pron,
            stock=stock,
            minimo=minimo,
            en_camino=llegando,
            multiplo=float(datos.get("multiplo_compra") or 1),
            unidad=producto.unidad_canonica,
            hoy=hoy,
            plazo_minimo_dias=plazo,
        )
        if pron
        else None
    )
    alerta = "bajo_minimo" if stock + llegando < minimo else "reponer" if repo and repo.cantidad > 0 else None
    tope = datos.get("tope_automatico_uyu")
    return ItemInventario(
        producto_id=producto_id,
        nombre=producto.nombre,
        nombre_corto=datos.get("nombre_corto") or producto.nombre,
        unidad=producto.unidad_canonica,
        tipo=datos["tipo"],
        stock_actual=stock,
        stock_minimo=minimo,
        en_camino=llegando,
        multiplo_compra=float(datos.get("multiplo_compra") or 1),
        modo=datos["modo"],
        tope_automatico_uyu=Decimal(str(tope)) if tope is not None else None,
        proveedores=[ProveedorRef(id=p, nombre=provs[p].nombre) for p in datos.get("proveedores", []) if p in provs],
        historial=[ConsumoMes(mes=m, cantidad=v) for m, v in sorted(consumo.items())],
        pronostico=pron,
        reposicion=repo,
        alerta=alerta,
    )


def inventario(horizonte_meses: int | None = None) -> Inventario:
    horizonte = horizonte_meses or horizonte_por_defecto()
    if not 1 <= horizonte <= 6:
        raise InventarioError("El horizonte va de 1 a 6 meses")
    hoy = fecha_hoy()
    camino = en_camino()
    return Inventario(
        fecha=hoy,
        horizonte_meses=horizonte,
        meses_pronostico=_meses_siguientes(hoy, horizonte),
        plazo_minimo_dias=int(_semilla().get("plazo_minimo_dias", 3)),
        productos=[item(p["producto_id"], horizonte, camino=camino) for p in _semilla()["productos"]],
    )
