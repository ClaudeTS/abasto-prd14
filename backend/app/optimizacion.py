"""Capa 4 — Optimización del plan de compra (MILP con PuLP). ARQUITECTURA §6.

El solver decide; la explicación (plantilla acá, o LLM en el endpoint) solo cuenta lo que salió.

Precisiones respecto de §6:
- El plazo de entrega se aplica por ítem (`z[i,j] = 0` si el lead time de `j` no llega a la
  fecha de esa línea), no sobre `y[j]`: cada línea del pedido tiene su propia fecha.
- `costo_total` es el costo real (precios × cantidades + envíos), no el objetivo con pesos.
- Si es infactible se relaja en orden max_prov → mínimos (penalización) → plazo, y después se
  deshacen las relajaciones que resultaron innecesarias, para que `relajaciones` sea honesta.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pulp

from app.models import (
    Asignacion,
    Cotizacion,
    ItemCotizado,
    NoMasBarato,
    Pedido,
    Plan,
    Proveedor,
)

CENTAVO = Decimal("0.01")
PENALIZACION_MINIMO = 500.0  # UYU por mínimo incumplido cuando se relajan los mínimos
TIME_LIMIT_S = 10
EPS = 1e-6
MEJORA_RELEVANTE = 1.0  # UYU: por debajo, una restricción no "afectó" el plan

Par = tuple[str, str]  # (producto_id, proveedor_id)


# ---------------------------------------------------------------- estructuras internas
@dataclass(frozen=True)
class _Oferta:
    producto_id: str
    proveedor_id: str
    precio: Decimal
    cantidad_minima: float | None
    unidad: str  # para textos: "unidades", "L", "kg"


@dataclass(frozen=True)
class _Condiciones:
    envio: Decimal
    minimo_total: Decimal | None
    plazo_pago: int
    lead: int
    confiabilidad: float


@dataclass
class _Instancia:
    fecha: date
    demanda: dict[str, float]  # en el orden del pedido
    dias: dict[str, int]  # días disponibles hasta necesario_para
    ofertas: dict[Par, _Oferta]
    condiciones: dict[str, _Condiciones]
    w_riesgo: float
    w_plazo: float

    def proveedores(self) -> list[str]:
        return list(dict.fromkeys(j for _, j in self.ofertas))

    def ofertas_de(self, producto_id: str) -> list[_Oferta]:
        return [o for (i, _), o in self.ofertas.items() if i == producto_id]

    def mejor_precio(self, producto_id: str) -> _Oferta:
        return min(self.ofertas_de(producto_id), key=lambda o: o.precio)


@dataclass(frozen=True)
class _Opciones:
    max_prov: int | None
    minimos_blandos: bool = False
    plazo_relajado: frozenset[str] = frozenset()  # productos sin ninguna oferta a tiempo
    sin_minimo_item: frozenset[Par] = frozenset()
    sin_minimo_total: frozenset[str] = frozenset()
    sin_plazo: frozenset[Par] = frozenset()


@dataclass
class _Solucion:
    cantidades: dict[Par, float]
    objetivo: float
    minimos_incumplidos: list[tuple[str, str | None]] = field(default_factory=list)

    def usados(self) -> list[str]:
        return list(dict.fromkeys(j for (_, j) in self.cantidades))

    def elegido(self, producto_id: str) -> str:
        pares = [(q, j) for (i, j), q in self.cantidades.items() if i == producto_id]
        return max(pares)[1]


# ---------------------------------------------------------------- formato
def _fmt_num(valor: Decimal | float | int, decimales: int = 0) -> str:
    """Formato uruguayo: 498.454 · 8,05."""
    cuanto = Decimal(1).scaleb(-decimales)
    d = Decimal(str(valor)).quantize(cuanto, rounding=ROUND_HALF_UP)
    entero, _, frac = f"{d:,.{decimales}f}".partition(".")
    entero = entero.replace(",", ".")
    return f"{entero},{frac}" if decimales else entero


def _fmt_monto(valor: Decimal | float) -> str:
    return f"$ {_fmt_num(valor)}"


def _fmt_precio(valor: Decimal | float) -> str:
    """Precio unitario: sin decimales salvo que sea chico y los tenga ($ 178,69)."""
    d = Decimal(str(valor))
    return f"$ {_fmt_num(d, 2)}" if d < 1000 and d != d.to_integral_value() else _fmt_monto(d)


def _fmt_cantidad(valor: float) -> str:
    return _fmt_num(valor) if float(valor).is_integer() else _fmt_num(valor, 2)


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _nombre_prov(proveedores: dict[str, Proveedor], proveedor_id: str) -> str:
    p = proveedores.get(proveedor_id)
    return p.nombre if p else proveedor_id


def _enumerar(partes: list[str]) -> str:
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _unidad_texto(item: ItemCotizado) -> str:
    """Unidad canónica inferida para los textos (el modelo no la trae)."""
    pistas = f"{item.conversion_aplicada or ''} {item.unidad_original}".lower().split()
    if pistas and pistas[-1] in ("l", "lt", "litro", "litros"):
        return "L"
    if pistas and pistas[-1] in ("kg", "kilo", "kilos"):
        return "kg"
    return "unidades"


# ---------------------------------------------------------------- armado de la instancia
def _cotizaciones_validas(
    cotizaciones: list[Cotizacion],
) -> tuple[dict[str, Cotizacion], list[str]]:
    """Por proveedor, la última cotización no marcada "revisar"; y los ids excluidos."""
    validas: dict[str, Cotizacion] = {}
    excluidas: list[str] = []
    for c in cotizaciones:
        if c.estado == "revisar":
            excluidas.append(c.id)
        else:
            validas[c.proveedor_id] = c
    return validas, excluidas


def _condiciones(c: Cotizacion, proveedores: dict[str, Proveedor]) -> _Condiciones:
    prov = proveedores.get(c.proveedor_id)
    return _Condiciones(
        envio=Decimal(c.costo_envio),
        minimo_total=Decimal(c.pedido_minimo_total) if c.pedido_minimo_total else None,
        plazo_pago=c.plazo_pago_dias,
        lead=c.lead_time_dias,
        confiabilidad=prov.confiabilidad if prov else 1.0,
    )


def _armar_instancia(
    pedido: Pedido,
    validas: dict[str, Cotizacion],
    proveedores: dict[str, Proveedor],
    w_riesgo: float,
    w_plazo: float,
) -> _Instancia:
    demanda = {linea.producto_id: linea.cantidad for linea in pedido.lineas}
    ofertas: dict[Par, _Oferta] = {}
    for c in validas.values():
        for item in c.items:
            if item.producto_id in demanda:
                ofertas[(item.producto_id, c.proveedor_id)] = _Oferta(
                    producto_id=item.producto_id,
                    proveedor_id=c.proveedor_id,
                    precio=Decimal(item.precio_unitario_sin_iva),
                    cantidad_minima=item.cantidad_minima,
                    unidad=_unidad_texto(item),
                )
    cotizados = {i for i, _ in ofertas}
    return _Instancia(
        fecha=pedido.fecha,
        demanda={i: d for i, d in demanda.items() if i in cotizados},
        dias={l.producto_id: (l.necesario_para - pedido.fecha).days for l in pedido.lineas},
        ofertas=ofertas,
        condiciones={j: _condiciones(c, proveedores) for j, c in validas.items()},
        w_riesgo=w_riesgo,
        w_plazo=w_plazo,
    )


# ---------------------------------------------------------------- modelo MILP
def _permitido(inst: _Instancia, op: _Opciones, par: Par) -> bool:
    """Plazo de entrega por ítem: el proveedor tiene que llegar a la fecha de esa línea."""
    i, j = par
    lead = inst.condiciones[j].lead
    if lead <= inst.dias[i] or par in op.sin_plazo:
        return True
    if i in op.plazo_relajado:  # relajación mínima: solo la(s) entrega(s) más rápida(s)
        return lead <= min(inst.condiciones[o.proveedor_id].lead for o in inst.ofertas_de(i))
    return False


def _precio_efectivo(inst: _Instancia, oferta: _Oferta) -> float:
    cond = inst.condiciones[oferta.proveedor_id]
    ajuste = inst.w_riesgo * (1 - cond.confiabilidad) - inst.w_plazo * cond.plazo_pago
    return float(oferta.precio) * (1 + ajuste)


def _resolver(inst: _Instancia, op: _Opciones) -> _Solucion | None:
    prob = pulp.LpProblem("plan_compra", pulp.LpMinimize)
    pares = list(inst.ofertas)
    provs = inst.proveedores()
    # Nombres por índice: los ids de dominio pueden traer caracteres que PuLP no acepta.
    x = {
        p: pulp.LpVariable(
            f"x_{k}",
            lowBound=0,
            cat="Integer" if float(inst.demanda[p[0]]).is_integer() else "Continuous",
        )
        for k, p in enumerate(pares)
    }
    z = {p: pulp.LpVariable(f"z_{k}", cat="Binary") for k, p in enumerate(pares)}
    y = {j: pulp.LpVariable(f"y_{k}", cat="Binary") for k, j in enumerate(provs)}
    v_item = {p: pulp.LpVariable(f"vi_{k}", cat="Binary") for k, p in enumerate(pares)}
    v_total = {j: pulp.LpVariable(f"vt_{k}", cat="Binary") for k, j in enumerate(provs)}

    penal = PENALIZACION_MINIMO if op.minimos_blandos else 0.0
    prob += (
        pulp.lpSum(_precio_efectivo(inst, inst.ofertas[p]) * x[p] for p in pares)
        + pulp.lpSum(float(inst.condiciones[j].envio) * y[j] for j in provs)
        + penal * (pulp.lpSum(v_item.values()) + pulp.lpSum(v_total.values()))
    )

    for i, d in inst.demanda.items():
        prob += pulp.lpSum(x[p] for p in pares if p[0] == i) == d
    for p in pares:
        i, j = p
        prob += x[p] <= inst.demanda[i] * z[p]
        prob += z[p] <= y[j]
        if not _permitido(inst, op, p):
            prob += z[p] == 0
        minimo = inst.ofertas[p].cantidad_minima
        if minimo and p not in op.sin_minimo_item:
            prob += x[p] >= minimo * (z[p] - v_item[p])
        if not op.minimos_blandos or not minimo:
            prob += v_item[p] == 0
    for j in provs:
        prob += y[j] <= pulp.lpSum(z[p] for p in pares if p[1] == j)
        minimo_total = inst.condiciones[j].minimo_total
        if minimo_total and j not in op.sin_minimo_total:
            gasto = pulp.lpSum(float(inst.ofertas[p].precio) * x[p] for p in pares if p[1] == j)
            prob += gasto >= float(minimo_total) * (y[j] - v_total[j])
        if not op.minimos_blandos or not minimo_total:
            prob += v_total[j] == 0
    if op.max_prov is not None:
        prob += pulp.lpSum(y.values()) <= op.max_prov

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=TIME_LIMIT_S))
    if prob.status != pulp.LpStatusOptimal:
        return None
    cantidades = {p: round(x[p].value(), 6) for p in pares if (x[p].value() or 0) > EPS}
    incumplidos = [(p[1], p[0]) for p in pares if (v_item[p].value() or 0) > 0.5]
    incumplidos += [(j, None) for j in provs if (v_total[j].value() or 0) > 0.5]
    return _Solucion(cantidades, pulp.value(prob.objective), incumplidos)


# ---------------------------------------------------------------- relajaciones
def _opciones_relajadas(inst: _Instancia, max_prov: int, niveles: set[str]) -> _Opciones:
    sin_oferta_a_tiempo = frozenset(
        i
        for i in inst.demanda
        if all(inst.condiciones[o.proveedor_id].lead > inst.dias[i] for o in inst.ofertas_de(i))
    )
    return _Opciones(
        max_prov=None if "max_prov" in niveles else max_prov,
        minimos_blandos="minimos" in niveles,
        plazo_relajado=sin_oferta_a_tiempo if "plazo" in niveles else frozenset(),
    )


def _resolver_con_relajaciones(
    inst: _Instancia, max_prov: int
) -> tuple[_Solucion, _Opciones, set[str]]:
    orden = ["max_prov", "minimos", "plazo"]
    for k in range(len(orden) + 1):
        niveles = set(orden[:k])
        sol = _resolver(inst, _opciones_relajadas(inst, max_prov, niveles))
        if sol is None:
            continue
        for nivel in orden[: max(k - 1, 0)]:  # deshacer las que no hacían falta
            sol_sin = _resolver(inst, _opciones_relajadas(inst, max_prov, niveles - {nivel}))
            if sol_sin is not None:
                niveles.discard(nivel)
                sol = sol_sin
        return sol, _opciones_relajadas(inst, max_prov, niveles), niveles
    raise ValueError("No hay plan factible ni relajando todas las restricciones")


def _textos_relajaciones(
    inst: _Instancia,
    sol: _Solucion,
    op: _Opciones,
    niveles: set[str],
    max_prov: int,
    nombres: dict[str, str],
    proveedores: dict[str, Proveedor],
) -> list[str]:
    textos: list[str] = []
    if "max_prov" in niveles:
        textos.append(
            f"Se quitó el límite de {max_prov} proveedor{'' if max_prov == 1 else 'es'}: con ese tope no había plan "
            f"factible (se usan {len(sol.usados())})"
        )
    if "minimos" in niveles:
        partes = [
            f"{_nombre_prov(proveedores, j)} ({nombres.get(i, i) if i else 'pedido mínimo total'})"
            for j, i in sol.minimos_incumplidos
        ]
        textos.append(
            "Se permitió no cumplir mínimos de compra, con penalización de "
            f"{_fmt_monto(PENALIZACION_MINIMO)} cada uno: {_enumerar(partes) or 'ninguno'}"
        )
    for i in sorted(op.plazo_relajado, key=list(inst.demanda).index):
        j = sol.elegido(i)
        textos.append(
            f"Ningún proveedor entrega {nombres.get(i, i)} en {inst.dias[i]} días: se relajó el "
            f"plazo y se eligió la entrega más rápida, {_nombre_prov(proveedores, j)} en "
            f"{inst.condiciones[j].lead} días"
        )
    return textos


# ---------------------------------------------------------------- restricciones activas
def _precio_elegido(inst: _Instancia, sol: _Solucion, producto_id: str) -> Decimal:
    return inst.ofertas[(producto_id, sol.elegido(producto_id))].precio


def _candidatas(inst: _Instancia, sol: _Solucion, op: _Opciones) -> list[_Opciones]:
    """Variantes del modelo sin una restricción que pudo haber dejado afuera algo más barato."""
    variantes: list[_Opciones] = []
    for par, oferta in inst.ofertas.items():
        i, j = par
        mas_barato = oferta.precio < _precio_elegido(inst, sol, i)
        en_minimo = oferta.cantidad_minima and math.isclose(
            sol.cantidades.get(par, 0), oferta.cantidad_minima
        )
        if oferta.cantidad_minima and not op.minimos_blandos and (mas_barato or en_minimo):
            variantes.append(replace(op, sin_minimo_item=frozenset({par})))
        if mas_barato and not _permitido(inst, op, par):
            variantes.append(replace(op, sin_plazo=frozenset({par})))
    for j, cond in inst.condiciones.items():
        if cond.minimo_total and not op.minimos_blandos and _le_conviene(inst, sol, j):
            variantes.append(replace(op, sin_minimo_total=frozenset({j})))
    if op.max_prov is not None and len(sol.usados()) >= op.max_prov:
        variantes.append(replace(op, max_prov=None))
    return variantes


def _le_conviene(inst: _Instancia, sol: _Solucion, proveedor_id: str) -> bool:
    """El proveedor tiene algo más barato que lo elegido, o se le compra justo el mínimo."""
    cond = inst.condiciones[proveedor_id]
    gasto = sum(
        inst.ofertas[p].precio * Decimal(str(q))
        for p, q in sol.cantidades.items()
        if p[1] == proveedor_id
    )
    if gasto and cond.minimo_total and abs(gasto - cond.minimo_total) < 1:
        return True
    return any(
        o.precio < _precio_elegido(inst, sol, o.producto_id)
        for (_, j), o in inst.ofertas.items()
        if j == proveedor_id
    )


def _texto_restriccion(
    inst: _Instancia,
    base: _Opciones,
    variante: _Opciones,
    nombres: dict[str, str],
    proveedores: dict[str, Proveedor],
) -> str:
    if variante.sin_minimo_item:
        (i, j) = next(iter(variante.sin_minimo_item))
        o = inst.ofertas[(i, j)]
        return (
            f"{_nombre_prov(proveedores, j)} exige mínimo {_fmt_cantidad(o.cantidad_minima)} "
            f"{o.unidad} de {nombres.get(i, i)}; el pedido es de "
            f"{_fmt_cantidad(inst.demanda[i])}"
        )
    if variante.sin_plazo:
        (i, j) = next(iter(variante.sin_plazo))
        return (
            f"{_nombre_prov(proveedores, j)} entrega en {inst.condiciones[j].lead} días y "
            f"{nombres.get(i, i)} se necesita en {inst.dias[i]}"
        )
    if variante.sin_minimo_total:
        j = next(iter(variante.sin_minimo_total))
        minimo = inst.condiciones[j].minimo_total or Decimal(0)
        return f"{_nombre_prov(proveedores, j)} tiene pedido mínimo de {_fmt_monto(minimo)}"
    return f"Límite de {base.max_prov} proveedores por pedido"


def _restricciones_activas(
    inst: _Instancia,
    sol: _Solucion,
    op: _Opciones,
    nombres: dict[str, str],
    proveedores: dict[str, Proveedor],
) -> list[str]:
    """Solo las que afectaron: sacarlas mejora el objetivo (contrafáctico con el solver)."""
    textos: list[str] = []
    for variante in _candidatas(inst, sol, op):
        alternativa = _resolver(inst, variante)
        if alternativa and alternativa.objetivo < sol.objetivo - MEJORA_RELEVANTE:
            textos.append(_texto_restriccion(inst, op, variante, nombres, proveedores))
    return list(dict.fromkeys(textos))


# ---------------------------------------------------------------- no el más barato
def _motivo(
    inst: _Instancia,
    sol: _Solucion,
    op: _Opciones,
    barato: _Oferta,
    elegido_id: str,
    proveedores: dict[str, Proveedor],
) -> str:
    i, c = barato.producto_id, barato.proveedor_id
    nom_c, nom_e = _nombre_prov(proveedores, c), _nombre_prov(proveedores, elegido_id)
    cond_c, cond_e = inst.condiciones[c], inst.condiciones[elegido_id]
    usado = c in sol.usados()
    if not _permitido(inst, op, (i, c)):
        return f"{nom_c} entrega en {cond_c.lead} días y se necesita en {inst.dias[i]}"
    if barato.cantidad_minima and barato.cantidad_minima > inst.demanda[i]:
        return (
            f"{nom_c} exige mínimo {_fmt_cantidad(barato.cantidad_minima)} {barato.unidad} "
            f"y se necesitan {_fmt_cantidad(inst.demanda[i])}"
        )
    if cond_c.minimo_total and not usado:
        return f"{nom_c} tiene pedido mínimo de {_fmt_monto(cond_c.minimo_total)}"
    if cond_c.envio > 0 and not usado:
        return f"{nom_c} cobra {_fmt_monto(cond_c.envio)} de envío"
    if op.max_prov is not None and not usado and len(sol.usados()) >= op.max_prov:
        return f"el plan tiene un límite de {op.max_prov} proveedor{'' if op.max_prov == 1 else 'es'}"
    partes: list[str] = []
    if cond_c.confiabilidad < cond_e.confiabilidad:
        partes.append(
            f"{nom_c} tiene menor confiabilidad ({_fmt_num(cond_c.confiabilidad, 2)} vs "
            f"{_fmt_num(cond_e.confiabilidad, 2)})"
        )
    if cond_e.plazo_pago > cond_c.plazo_pago:
        partes.append(f"{nom_e} da {cond_e.plazo_pago} días de plazo de pago")
    return _enumerar(partes) or "la combinación con el resto del plan sale más barata"


def _no_mas_barato(
    inst: _Instancia, sol: _Solucion, op: _Opciones, proveedores: dict[str, Proveedor]
) -> list[NoMasBarato]:
    casos: list[NoMasBarato] = []
    for i in inst.demanda:
        barato = inst.mejor_precio(i)
        elegido_id = sol.elegido(i)
        precio_elegido = inst.ofertas[(i, elegido_id)].precio
        if precio_elegido <= barato.precio:
            continue
        casos.append(
            NoMasBarato(
                producto_id=i,
                mas_barato_id=barato.proveedor_id,
                precio_mas_barato=_redondear(barato.precio),
                elegido_id=elegido_id,
                precio_elegido=_redondear(precio_elegido),
                motivo=_motivo(inst, sol, op, barato, elegido_id, proveedores),
            )
        )
    return casos


# ---------------------------------------------------------------- costos
def _asignaciones(inst: _Instancia, sol: _Solucion) -> list[Asignacion]:
    orden = list(inst.demanda)
    filas = sorted(sol.cantidades.items(), key=lambda kv: (orden.index(kv[0][0]), -kv[1]))
    return [
        Asignacion(
            producto_id=i,
            proveedor_id=j,
            cantidad=q,
            precio_unitario_sin_iva=_redondear(inst.ofertas[(i, j)].precio),
            subtotal=_redondear(inst.ofertas[(i, j)].precio * Decimal(str(q))),
        )
        for (i, j), q in filas
    ]


def _costo(
    asignaciones: list[Asignacion],
    envios: dict[str, Decimal],
    productos: set[str] | None = None,
) -> Decimal:
    """Σ subtotales + envíos. Con `productos`, el envío de cada proveedor se prorratea por la
    parte de su subtotal que cae en esos productos."""
    total = Decimal(0)
    for j in dict.fromkeys(a.proveedor_id for a in asignaciones):
        propias = [a for a in asignaciones if a.proveedor_id == j]
        sub_total = sum((a.subtotal for a in propias), Decimal(0))
        sub_parcial = sum(
            (a.subtotal for a in propias if productos is None or a.producto_id in productos),
            Decimal(0),
        )
        total += sub_parcial
        if sub_total:
            total += envios.get(j, Decimal(0)) * sub_parcial / sub_total
    return _redondear(total)


def _asignaciones_baseline(inst: _Instancia, habitual_id: str) -> list[Asignacion]:
    """Todo al habitual; lo que no cotiza, al más barato restante (sin otras restricciones)."""
    filas: list[Asignacion] = []
    for i, d in inst.demanda.items():
        oferta = inst.ofertas.get((i, habitual_id)) or inst.mejor_precio(i)
        filas.append(
            Asignacion(
                producto_id=i,
                proveedor_id=oferta.proveedor_id,
                cantidad=d,
                precio_unitario_sin_iva=_redondear(oferta.precio),
                subtotal=_redondear(oferta.precio * Decimal(str(d))),
            )
        )
    return filas


def _pct(parte: Decimal, total: Decimal) -> float:
    return round(float(parte / total * 100), 2) if total else 0.0


def _oportunidad(inst: _Instancia, sol: _Solucion) -> tuple[str | None, Decimal | None]:
    brechas: dict[str, Decimal] = {}
    for (i, j), q in sol.cantidades.items():
        brecha = (inst.ofertas[(i, j)].precio - inst.mejor_precio(i).precio) * Decimal(str(q))
        brechas[j] = brechas.get(j, Decimal(0)) + brecha
    if not brechas:
        return None, None
    j, brecha = max(brechas.items(), key=lambda kv: kv[1])
    return (j, _redondear(brecha)) if brecha > 0 else (None, None)


# ---------------------------------------------------------------- API pública
def optimizar(
    pedido: Pedido,
    cotizaciones: list[Cotizacion],
    proveedores: dict[str, Proveedor],
    *,
    tipo_cambio_usd: float,
    nombres_productos: dict[str, str],
    w_riesgo: float = 0.03,
    w_plazo: float = 0.0005,
    max_prov: int = 4,
) -> Plan:
    validas, excluidas = _cotizaciones_validas(cotizaciones)
    inst = _armar_instancia(pedido, validas, proveedores, w_riesgo, w_plazo)
    sin_cotizar = [
        f"Sin cotizaciones para {nombres_productos.get(l.producto_id, l.producto_id)}: "
        "no se incluyó en el plan"
        for l in pedido.lineas
        if l.producto_id not in inst.demanda
    ]
    if not inst.demanda:
        raise ValueError("Ningún producto del pedido tiene cotizaciones válidas")

    sol, op, niveles = _resolver_con_relajaciones(inst, max_prov)
    envios = {j: c.envio for j, c in inst.condiciones.items()}
    asignaciones = _asignaciones(inst, sol)
    costo_total = _costo(asignaciones, envios)

    habitual = pedido.proveedor_habitual_id
    base = _asignaciones_baseline(inst, habitual)
    costo_baseline = _costo(base, envios)
    comparables = {i for i in inst.demanda if (i, habitual) in inst.ofertas}
    base_comparable = _costo(base, envios, comparables)
    ahorro_comparable = base_comparable - _costo(asignaciones, envios, comparables)
    oportunidad, brecha = _oportunidad(inst, sol)

    plan = Plan(
        pedido_id=pedido.id,
        asignaciones=asignaciones,
        costo_total=costo_total,
        costo_baseline=costo_baseline,
        ahorro=costo_baseline - costo_total,
        ahorro_pct=_pct(costo_baseline - costo_total, costo_baseline),
        ahorro_comparable=ahorro_comparable,
        ahorro_pct_comparable=_pct(ahorro_comparable, base_comparable),
        proveedores_usados=sol.usados(),
        restricciones_activas=_restricciones_activas(
            inst, sol, op, nombres_productos, proveedores
        ),
        relajaciones=sin_cotizar
        + _textos_relajaciones(inst, sol, op, niveles, max_prov, nombres_productos, proveedores),
        no_mas_barato=_no_mas_barato(inst, sol, op, proveedores),
        explicacion="",
        explicacion_origen="plantilla",
        oportunidad_negociacion=oportunidad,
        brecha_oportunidad=brecha,
        tipo_cambio_usd=tipo_cambio_usd,
        cotizaciones_excluidas=excluidas,
    )
    plan.explicacion = explicacion_plantilla(
        plan, proveedores, nombres_productos, habitual_id=habitual
    )
    return plan


# ---------------------------------------------------------------- explicación
def _nombre_habitual(proveedores: dict[str, Proveedor], habitual_id: str | None) -> str:
    # `Plan` no guarda el habitual (está en el Pedido): por eso el kwarg opcional.
    return _nombre_prov(proveedores, habitual_id) if habitual_id else "el proveedor habitual"


def _oracion_ahorro(plan: Plan, proveedores: dict[str, Proveedor], habitual: str) -> str:
    nombres = [_nombre_prov(proveedores, j) for j in plan.proveedores_usados]
    cantidad = f"{len(nombres)} proveedor" + ("es" if len(nombres) != 1 else "")
    inicio = (
        f"Comprando a {cantidad} ({_enumerar(nombres)}) el pedido cuesta "
        f"{_fmt_monto(plan.costo_total)} sin IVA"
    )
    if plan.ahorro == 0:
        comparacion = f", lo mismo que comprar todo a {habitual}"
    elif plan.ahorro > 0:
        comparacion = (
            f", {_fmt_monto(plan.ahorro)} menos ({_fmt_num(plan.ahorro_pct, 1)} %) que "
            f"comprar todo a {habitual}"
        )
    else:
        comparacion = f", {_fmt_monto(-plan.ahorro)} más que comprar todo a {habitual}"
    if plan.ahorro_comparable > 0 and abs(plan.ahorro_pct_comparable - plan.ahorro_pct) > 0.05:
        comparacion += (
            f"; si se mira solo lo que vende {habitual}, el ahorro es del "
            f"{_fmt_num(plan.ahorro_pct_comparable, 1)} %"
        )
    return inicio + comparacion + "."


def _oracion_caso(
    caso: NoMasBarato, proveedores: dict[str, Proveedor], nombres: dict[str, str]
) -> str:
    producto = nombres.get(caso.producto_id, caso.producto_id)
    return (
        f"En {producto} no se eligió al más barato: "
        f"{_nombre_prov(proveedores, caso.mas_barato_id)} cotiza "
        f"{_fmt_precio(caso.precio_mas_barato)} pero {_sin_nombre(caso, proveedores)}, así que "
        f"conviene {_nombre_prov(proveedores, caso.elegido_id)} a "
        f"{_fmt_precio(caso.precio_elegido)}."
    )


def _sin_nombre(caso: NoMasBarato, proveedores: dict[str, Proveedor]) -> str:
    """El motivo sin repetir el nombre del proveedor al principio."""
    nombre = _nombre_prov(proveedores, caso.mas_barato_id)
    motivo = caso.motivo
    return motivo[len(nombre) + 1 :] if motivo.startswith(nombre + " ") else motivo


def _oraciones_casos(
    plan: Plan, proveedores: dict[str, Proveedor], nombres: dict[str, str], cupo: int
) -> list[str]:
    if not plan.no_mas_barato:
        return ["En todos los productos se eligió el precio más bajo cotizado."]
    if len(plan.no_mas_barato) <= cupo:
        return [_oracion_caso(c, proveedores, nombres) for c in plan.no_mas_barato]
    explicitos = [_oracion_caso(c, proveedores, nombres) for c in plan.no_mas_barato[: cupo - 1]]
    resto = [nombres.get(c.producto_id, c.producto_id) for c in plan.no_mas_barato[cupo - 1 :]]
    return explicitos + [
        f"Tampoco se eligió al más barato en {_enumerar(resto)}, por mínimos, plazos o "
        "condiciones de pago."
    ]


def _oracion_relajaciones(plan: Plan) -> str | None:
    if not plan.relajaciones:
        return None
    return "Para poder armar el plan hubo que ceder en algo: " + "; ".join(
        r[0].lower() + r[1:] for r in plan.relajaciones
    ) + "."


def _oracion_oportunidad(plan: Plan, proveedores: dict[str, Proveedor]) -> str | None:
    if not plan.oportunidad_negociacion or plan.brecha_oportunidad is None:
        return None
    return (
        f"La mayor oportunidad de negociación está con "
        f"{_nombre_prov(proveedores, plan.oportunidad_negociacion)}: "
        f"{_fmt_monto(plan.brecha_oportunidad)} de diferencia contra el mejor precio cotizado."
    )


def explicacion_plantilla(
    plan: Plan,
    proveedores: dict[str, Proveedor],
    nombres_productos: dict[str, str],
    *,
    habitual_id: str | None = None,
) -> str:
    """3–5 oraciones con la estructura del prompt `explicar_plan`, sin LLM."""
    relaj = _oracion_relajaciones(plan)
    oport = _oracion_oportunidad(plan, proveedores)
    cupo = 4 - (relaj is not None) - (oport is not None)
    oraciones = [_oracion_ahorro(plan, proveedores, _nombre_habitual(proveedores, habitual_id))]
    oraciones += _oraciones_casos(plan, proveedores, nombres_productos, max(cupo, 1))
    oraciones += [o for o in (relaj, oport) if o]
    return " ".join(oraciones[:5])


def datos_para_explicar(
    plan: Plan,
    proveedores: dict[str, Proveedor],
    nombres_productos: dict[str, str],
    *,
    habitual_id: str | None = None,
) -> dict[str, str]:
    """Variables del prompt `explicar_plan` (PROMPTS.md §6), ya formateadas en español."""
    asignaciones = "\n".join(
        f"- {nombres_productos.get(a.producto_id, a.producto_id)}: "
        f"{_fmt_cantidad(a.cantidad)} a {_nombre_prov(proveedores, a.proveedor_id)}, "
        f"{_fmt_precio(a.precio_unitario_sin_iva)} c/u, subtotal {_fmt_monto(a.subtotal)}"
        for a in plan.asignaciones
    )
    casos = "\n".join(
        f"- {nombres_productos.get(c.producto_id, c.producto_id)}: más barato "
        f"{_nombre_prov(proveedores, c.mas_barato_id)} ({_fmt_precio(c.precio_mas_barato)}), "
        f"elegido {_nombre_prov(proveedores, c.elegido_id)} ({_fmt_precio(c.precio_elegido)}); "
        f"motivo: {c.motivo}"
        for c in plan.no_mas_barato
    )
    return {
        "asignaciones": asignaciones,
        "costo_total": _fmt_num(plan.costo_total),
        "tipo_cambio": _fmt_num(plan.tipo_cambio_usd, 2),
        "habitual": _nombre_habitual(proveedores, habitual_id),
        "baseline": _fmt_monto(plan.costo_baseline),
        "ahorro": _fmt_monto(plan.ahorro),
        "ahorro_pct": _fmt_num(plan.ahorro_pct, 2),
        "ahorro_pct_comparable": _fmt_num(plan.ahorro_pct_comparable, 2),
        "restricciones_activas": "; ".join(plan.restricciones_activas) or "ninguna",
        "relajaciones": "; ".join(plan.relajaciones) or "ninguna",
        "no_mas_barato": casos or "ninguno",
    }
