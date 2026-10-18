"""Ranking de proveedores (RF-07, §11.1) y evaluación de la negociación ensayada (RF-16, §11.5).

Todo se calcula al leer, a partir de lo que ya hay en el store (pedido, cotizaciones, plan y
negociaciones): no se cambian `negociacion.py` ni `models.py`.

Ranking por producto, regla en cascada:
1. menor costo comparable (sin IVA, UYU, unidad del producto: `precio_unitario_sin_iva`);
2. ante empate en precio (diferencia de hasta TOLERANCIA_EMPATE_PCT), mejor cumplimiento de los
   demás atributos: plazo de entrega, condiciones de pago, garantía y especificaciones;
3. ante empate en atributos, mayor antigüedad y mejor cumplimiento histórico.
Quedan excluidos, con su motivo, los que no se pueden elegir: el pedido no llega a su mínimo, la
entrega es posterior a la fecha requerida o la cotización tiene dudas sin confirmar.

Evaluación (§11.5): por estrategia, la oferta resultante (precio con la concesión; pago contado si
la estrategia es "plazo") se compara contra cada uno de los demás proveedores en precio, entrega,
pago y garantía. Riesgo de plazo: aceptable si la entrega supera en hasta MARGEN_RIESGO_DIAS la de
un proveedor regular (el habitual si cotiza esos productos; si no, la mediana del resto).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from app import pedidos, perfiles, pipeline, store
from app.models import Cotizacion, ItemCotizado, Negociacion, Pedido, Plan
from app.normalizacion import fmt

TOLERANCIA_EMPATE_PCT = 1.0
MIN_PROVEEDORES = 3  # si hay menos elegibles, el agente sugiere dar de alta uno nuevo (RF-19)
MARGEN_RIESGO_DIAS = 15
REGLA = [
    "1. Menor costo comparable (sin IVA, en pesos y en la unidad del producto).",
    f"2. Si empatan en precio (hasta {fmt(TOLERANCIA_EMPATE_PCT, 0)} % de diferencia): mejor cumplimiento de "
    "plazo de entrega, condiciones de pago, garantía y especificaciones.",
    "3. Si persiste el empate: mayor antigüedad y mejor cumplimiento histórico.",
]
DATOS_EJEMPLO = ["antigüedad", "cumplimiento histórico", "garantía"]

Resultado = Literal["mejora", "iguala", "peor", "sin_dato"]


class NoEncontrado(KeyError):
    """Pedido, producto o negociación inexistente (404)."""


# ---------------------------------------------------------------- helpers
def _pedido(pedido_id: str) -> Pedido:
    pedido = pedidos.obtener(pedido_id)
    if pedido is None:
        raise NoEncontrado(f"No existe el pedido '{pedido_id}'")
    return pedido


def _cotizaciones(pedido_id: str) -> dict[str, Cotizacion]:
    """La última cotización de cada proveedor para el pedido (como el optimizador)."""
    ultimas: dict[str, Cotizacion] = {}
    for c in store.listar("cotizaciones", Cotizacion, pedido_id=pedido_id):
        ultimas[c.proveedor_id] = c
    return ultimas


def _plan(pedido_id: str) -> Plan | None:
    datos = store.obtener_dict("planes", pedido_id)
    return Plan.model_validate(datos) if datos else None


def _nombre(proveedor_id: str) -> str:
    try:
        return perfiles.ficha(proveedor_id)["nombre"]
    except KeyError:
        return proveedor_id


def _item(c: Cotizacion, producto_id: str) -> ItemCotizado | None:
    return next((i for i in c.items if i.producto_id == producto_id), None)


def _dias(n: int) -> str:
    return "1 día" if n == 1 else f"{n} días"


def _pago(n: int) -> str:
    return "contado" if n == 0 else f"{n} días"


def _precio(valor: Decimal | float) -> str:
    d = Decimal(str(valor))
    return f"$ {fmt(d, 0 if d == d.to_integral_value() or abs(d) >= 1000 else 2)}"


def _unidad(unidad: str) -> str:
    return {"unidad": "por unidad", "l": "por litro", "kg": "por kg"}.get(unidad, "por unidad")


def _punto(texto: str) -> str:
    """Evita el ".." cuando la oración termina en un nombre como "TecnoImport S.A."."""
    return texto[:-1] if texto.endswith("..") else texto


def motivo_exclusion(
    c: Cotizacion, item: ItemCotizado, cantidad: float, dias_requeridos: int
) -> tuple[str, str] | None:
    """(tipo, motivo) si el proveedor no se puede elegir para esa línea; None si es elegible."""
    if c.estado == "revisar":
        dudas = ", ".join(c.campos_dudosos) or "datos"
        return "revisar", f"La cotización tiene dudas sin confirmar ({dudas}): no entra al ranking hasta confirmarla."
    if item.cantidad_minima and item.cantidad_minima > cantidad:
        return (
            "minimo",
            f"No cumple el mínimo: exige {fmt(item.cantidad_minima)} y el pedido es de {fmt(cantidad)}.",
        )
    if c.lead_time_dias > dias_requeridos:
        return (
            "plazo",
            f"Plazo mayor al requerido: entrega en {_dias(c.lead_time_dias)} y se necesita en {_dias(dias_requeridos)}.",
        )
    return None


# ---------------------------------------------------------------- RF-07: ranking
def _candidato(c: Cotizacion, item: ItemCotizado, cantidad: float) -> dict[str, Any]:
    f = perfiles.ficha(c.proveedor_id)
    precio = Decimal(item.precio_unitario_sin_iva)
    return {
        "proveedor_id": c.proveedor_id,
        "nombre": f["nombre"],
        "cotizacion_id": c.id,
        "costo_comparable": float(precio),
        "subtotal": float(precio * Decimal(str(cantidad))),
        "costo_envio": float(c.costo_envio),
        "entrega_dias": c.lead_time_dias,
        "pago_dias": c.plazo_pago_dias,
        "garantia_meses": f["garantia_meses"],
        # Especificaciones: la Capa 1 mapeó el ítem a este producto del catálogo; si no, no estaría acá.
        "especificaciones": "cumple",
        "descripcion_original": item.descripcion_original,
        "evidencia": item.evidencia,
        "antiguedad_dias": f["antiguedad"]["dias"],
        "antiguedad": f["antiguedad"]["texto"],
        "cumplimiento_historico_pct": f["cumplimiento_historico_pct"],
        "datos_ejemplo": f["datos_ejemplo"],
    }


def _atributos_ganados(c: dict[str, Any], grupo: list[dict[str, Any]]) -> list[str]:
    """Atributos en los que `c` es el mejor (o empata con el mejor) dentro de su grupo de empate."""
    ganados = []
    if c["entrega_dias"] <= min(g["entrega_dias"] for g in grupo):
        ganados.append(f"entrega en {_dias(c['entrega_dias'])}")
    if c["pago_dias"] >= max(g["pago_dias"] for g in grupo):
        ganados.append(f"pago {_pago(c['pago_dias'])}")
    garantias = [g["garantia_meses"] or 0 for g in grupo]
    if (c["garantia_meses"] or 0) >= max(garantias) and max(garantias) > 0:
        ganados.append(f"garantía {c['garantia_meses']} meses")
    if c["especificaciones"] == "cumple":
        ganados.append("cumple especificaciones")
    return ganados


def _grupos_empate(candidatos: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grupos: list[list[dict[str, Any]]] = []
    for c in sorted(candidatos, key=lambda c: c["costo_comparable"]):
        if grupos and c["costo_comparable"] <= grupos[-1][0]["costo_comparable"] * (1 + TOLERANCIA_EMPATE_PCT / 100):
            grupos[-1].append(c)
        else:
            grupos.append([c])
    return grupos


def ordenar(candidatos: list[dict[str, Any]], unidad: str = "unidad") -> list[dict[str, Any]]:
    """Aplica la regla en cascada y completa posición, criterio y motivo de cada candidato."""
    ordenados: list[dict[str, Any]] = []
    for grupo in _grupos_empate(candidatos):
        for c in grupo:
            c["atributos_ganados"] = _atributos_ganados(c, grupo)
        grupo.sort(
            key=lambda c: (
                -len(c["atributos_ganados"]),
                -(c["antiguedad_dias"] or 0),
                -(c["cumplimiento_historico_pct"] or 0),
                c["costo_comparable"],
            )
        )
        for k, c in enumerate(grupo):
            c["empate_con"] = [g["nombre"] for g in grupo if g is not c]
            c["adelante_en_empate"] = k == 0
            if len(grupo) == 1:
                c["criterio"] = "precio"
            else:
                vecino = grupo[k + 1] if k + 1 < len(grupo) else grupo[k - 1]
                c["criterio"] = (
                    "atributos" if len(c["atributos_ganados"]) != len(vecino["atributos_ganados"]) else "antiguedad"
                )
        ordenados += grupo
    lider = ordenados[0] if ordenados else None
    for pos, c in enumerate(ordenados, start=1):
        c["posicion"] = pos
    for c in ordenados:
        c["motivo"] = _punto(_motivo(c, c["posicion"], lider, ordenados, unidad))
    return ordenados


def _motivo(c: dict[str, Any], pos: int, lider: dict[str, Any] | None, todos: list[dict[str, Any]], unidad: str) -> str:
    precio = f"{_precio(c['costo_comparable'])} {_unidad(unidad)} sin IVA"
    if c["criterio"] == "atributos":
        otros = " y ".join(c["empate_con"])
        if c["adelante_en_empate"]:
            return (
                f"Empata en precio con {otros} ({precio}) y queda adelante por atributos: "
                f"{', '.join(c['atributos_ganados'])}."
            )
        return f"Empata en precio con {otros} ({precio}), pero cumple menos atributos ({len(c['atributos_ganados'])} de 4)."
    if c["criterio"] == "antiguedad":
        otros = " y ".join(c["empate_con"])
        historial = f"{c['antiguedad']} de antigüedad"
        if c["cumplimiento_historico_pct"] is not None:
            historial += f", {fmt(c['cumplimiento_historico_pct'])} % de cumplimiento"
        return f"Empata en precio y atributos con {otros}; se ordena por antigüedad y cumplimiento histórico ({historial})."
    if pos == 1:
        siguiente = next((t for t in todos if t["posicion"] == 2), None) if len(todos) > 1 else None
        if siguiente is None:
            return f"Único proveedor elegible: {precio}."
        diferencia = siguiente["costo_comparable"] - c["costo_comparable"]
        return f"Menor costo comparable: {precio}, {_precio(diferencia)} menos que {siguiente['nombre']}."
    assert lider is not None
    pct = (c["costo_comparable"] / lider["costo_comparable"] - 1) * 100 if lider["costo_comparable"] else 0
    return f"Costo comparable {precio}: {fmt(pct, 1)} % más caro que {lider['nombre']} (1.º)."


def ranking(pedido_id: str, producto_id: str | None = None) -> dict[str, Any]:
    pedido = _pedido(pedido_id)
    lineas = [l for l in pedido.lineas if producto_id is None or l.producto_id == producto_id]
    if producto_id is not None and not lineas:
        raise NoEncontrado(f"El pedido '{pedido_id}' no incluye el producto '{producto_id}'")
    catalogo = {p.id: p for p in pipeline.catalogo()}
    cots = _cotizaciones(pedido_id)
    plan = _plan(pedido_id)
    en_plan = {(a.producto_id, a.proveedor_id) for a in plan.asignaciones} if plan else set()
    productos = []
    for linea in lineas:
        prod = catalogo.get(linea.producto_id)
        unidad = prod.unidad_canonica if prod else "unidad"
        dias = (linea.necesario_para - pedido.fecha).days
        candidatos, excluidos = [], []
        for c in cots.values():
            item = _item(c, linea.producto_id)
            if item is None:
                continue
            datos = _candidato(c, item, linea.cantidad)
            datos["en_plan"] = (linea.producto_id, c.proveedor_id) in en_plan
            exclusion = motivo_exclusion(c, item, linea.cantidad, dias)
            if exclusion:
                datos["tipo_exclusion"], datos["motivo"] = exclusion
                excluidos.append(datos)
            else:
                candidatos.append(datos)
        ordenados = ordenar(candidatos, unidad)
        sin_cotizar = sorted(
            _nombre(pid) for pid in pipeline.proveedores() if pid not in cots or _item(cots[pid], linea.producto_id) is None
        )
        pocos = len(ordenados) < MIN_PROVEEDORES
        productos.append(
            {
                "producto_id": linea.producto_id,
                "nombre": prod.nombre if prod else linea.producto_id,
                "unidad": unidad,
                "cantidad": linea.cantidad,
                "necesario_para": linea.necesario_para.isoformat(),
                "dias_requeridos": dias,
                "ranking": ordenados,
                "excluidos": sorted(excluidos, key=lambda e: e["costo_comparable"]),
                "sin_cotizar": sin_cotizar,
                "pocos_proveedores": pocos,
                "sugerencia_alta": (
                    f"Solo {len(ordenados)} proveedor{'es' if len(ordenados) != 1 else ''} elegible"
                    f"{'s' if len(ordenados) != 1 else ''} (se buscan al menos {MIN_PROVEEDORES}): "
                    "el agente puede contactar y dar de alta uno nuevo."
                    if pocos
                    else None
                ),
            }
        )
    return {
        "pedido_id": pedido_id,
        "calculado_en": datetime.now().isoformat(timespec="seconds"),
        "regla": REGLA,
        "tolerancia_empate_pct": TOLERANCIA_EMPATE_PCT,
        "minimo_proveedores": MIN_PROVEEDORES,
        "hay_plan": plan is not None,
        "datos_ejemplo": DATOS_EJEMPLO,
        "productos": productos,
    }


# ---------------------------------------------------------------- RF-16: evaluación
def _comparar(propio: float | None, otro: float | None, mayor_es_mejor: bool) -> Resultado:
    if propio is None or otro is None:
        return "sin_dato"
    if abs(propio - otro) < 1e-6:
        return "iguala"
    mejor = propio > otro if mayor_es_mejor else propio < otro
    return "mejora" if mejor else "peor"


def _referencia_regular(
    pedido: Pedido, propio_id: str, productos: list[str], cots: dict[str, Cotizacion]
) -> dict[str, Any] | None:
    """El "proveedor regular" de §11.5: el habitual si cotiza algo de lo que se negocia."""
    habitual = pedido.proveedor_habitual_id
    c = cots.get(habitual)
    if habitual != propio_id and c is not None and any(_item(c, p) for p in productos):
        return {
            "proveedor_id": habitual,
            "nombre": _nombre(habitual),
            "entrega_dias": c.lead_time_dias,
            "criterio": "proveedor habitual",
        }
    leads = [
        c.lead_time_dias
        for pid, c in cots.items()
        if pid != propio_id and c.estado != "revisar" and any(_item(c, p) for p in productos)
    ]
    if not leads:
        return None
    return {
        "proveedor_id": None,
        "nombre": "mediana del resto",
        "entrega_dias": median(leads),
        "criterio": "mediana de la entrega de los demás proveedores que cotizan estos productos",
    }


def _riesgo_plazo(entrega: int, referencia: dict[str, Any] | None) -> dict[str, Any]:
    if referencia is None:
        return {"nivel": "sin_dato", "diferencia_dias": None, "texto": "No hay otro proveedor con el que comparar la entrega."}
    diferencia = entrega - referencia["entrega_dias"]
    ref = f"{referencia['nombre']} ({_dias(int(referencia['entrega_dias']))})"
    if diferencia <= 0:
        return {"nivel": "bajo", "diferencia_dias": diferencia, "texto": f"Entrega igual o antes que {ref}."}
    if diferencia <= MARGEN_RIESGO_DIAS:
        return {
            "nivel": "aceptable",
            "diferencia_dias": diferencia,
            "texto": f"Entrega {_dias(int(diferencia))} después que {ref}: dentro del margen de {MARGEN_RIESGO_DIAS} días.",
        }
    return {
        "nivel": "alto",
        "diferencia_dias": diferencia,
        "texto": f"Entrega {_dias(int(diferencia))} después que {ref}: supera el margen de {MARGEN_RIESGO_DIAS} días.",
    }


def evaluacion(negociacion_id: str) -> dict[str, Any]:
    neg = store.obtener("negociaciones", negociacion_id, Negociacion)
    if neg is None:
        raise NoEncontrado(f"No existe la negociación '{negociacion_id}'")
    pedido = _pedido(neg.pedido_id)
    cots = _cotizaciones(neg.pedido_id)
    propia = cots.get(neg.proveedor_id)
    if propia is None:
        raise NoEncontrado(f"{_nombre(neg.proveedor_id)} no tiene cotización en el pedido '{neg.pedido_id}'")
    plan = _plan(neg.pedido_id)
    lineas = {l.producto_id: l for l in pedido.lineas}
    catalogo = {p.id: p.nombre for p in pipeline.catalogo()}
    # Lo que se negocia: lo que el plan le compra; sin plan, lo que cotizó de este pedido.
    if plan and any(a.proveedor_id == neg.proveedor_id for a in plan.asignaciones):
        items = [
            {"producto_id": a.producto_id, "cantidad": a.cantidad, "precio": Decimal(a.precio_unitario_sin_iva)}
            for a in plan.asignaciones
            if a.proveedor_id == neg.proveedor_id
        ]
    else:
        items = [
            {"producto_id": i.producto_id, "cantidad": lineas[i.producto_id].cantidad, "precio": Decimal(i.precio_unitario_sin_iva)}
            for i in propia.items
            if i.producto_id in lineas
        ]
    productos = [i["producto_id"] for i in items]
    garantia_propia = perfiles.ficha(neg.proveedor_id)["garantia_meses"]

    competidores = []
    for pid, c in cots.items():
        if pid == neg.proveedor_id:
            continue
        comunes = [(i, _item(c, i["producto_id"])) for i in items]
        comunes = [(i, it) for i, it in comunes if it is not None]
        if not comunes:
            continue
        exclusiones = [
            ex
            for i, it in comunes
            if (ex := motivo_exclusion(c, it, i["cantidad"], (lineas[i["producto_id"]].necesario_para - pedido.fecha).days))
        ]
        competidores.append(
            {
                "proveedor_id": pid,
                "nombre": _nombre(pid),
                "productos": [i["producto_id"] for i, _ in comunes],
                "precios": {i["producto_id"]: float(it.precio_unitario_sin_iva) for i, it in comunes},
                "total_comparable": float(
                    sum((Decimal(it.precio_unitario_sin_iva) * Decimal(str(i["cantidad"])) for i, it in comunes), Decimal(0))
                ),
                "entrega_dias": c.lead_time_dias,
                "pago_dias": c.plazo_pago_dias,
                "garantia_meses": perfiles.ficha(pid)["garantia_meses"],
                "elegible": not exclusiones,
                "motivo_no_elegible": exclusiones[0][1] if exclusiones else None,
            }
        )
    referencia = _referencia_regular(pedido, neg.proveedor_id, productos, cots)

    estrategias = []
    for e in neg.estrategias:
        pct = Decimal(str(e.concesion_obtenida_pct))
        precios = {i["producto_id"]: i["precio"] * (1 - pct / 100) for i in items}
        pago = 0 if e.nombre == "plazo" and pct > 0 else propia.plazo_pago_dias
        oferta = {
            "precios": {p: float(round(v, 2)) for p, v in precios.items()},
            "total": float(round(sum((precios[i["producto_id"]] * Decimal(str(i["cantidad"])) for i in items), Decimal(0)), 2)),
            "entrega_dias": propia.lead_time_dias,
            "pago_dias": pago,
            "garantia_meses": garantia_propia,
        }
        comparaciones = []
        for comp in competidores:
            propio_total = float(
                sum((precios[p] * Decimal(str(next(i["cantidad"] for i in items if i["producto_id"] == p))) for p in comp["productos"]), Decimal(0))
            )
            dims = {
                "precio": _comparar(propio_total, comp["total_comparable"], mayor_es_mejor=False),
                "entrega": _comparar(oferta["entrega_dias"], comp["entrega_dias"], mayor_es_mejor=False),
                "pago": _comparar(oferta["pago_dias"], comp["pago_dias"], mayor_es_mejor=True),
                "garantia": _comparar(oferta["garantia_meses"], comp["garantia_meses"], mayor_es_mejor=True),
            }
            comparaciones.append(
                {
                    "proveedor_id": comp["proveedor_id"],
                    "nombre": comp["nombre"],
                    "elegible": comp["elegible"],
                    "motivo_no_elegible": comp["motivo_no_elegible"],
                    "propio_total": round(propio_total, 2),
                    "otro_total": round(comp["total_comparable"], 2),
                    "otro_entrega_dias": comp["entrega_dias"],
                    "otro_pago_dias": comp["pago_dias"],
                    "otro_garantia_meses": comp["garantia_meses"],
                    "resultado": dims,
                    "supera": dims["precio"] != "peor" and "peor" not in dims.values() and "mejora" in dims.values(),
                }
            )
        elegibles = [c for c in comparaciones if c["elegible"]]
        resumen = _resumen_dimensiones(oferta, competidores, elegibles, items, precios)
        riesgo_plazo = _riesgo_plazo(oferta["entrega_dias"], referencia)
        riesgo = "alto" if "alto" in (e.riesgo, riesgo_plazo["nivel"]) else e.riesgo
        gana = bool(e.transcripcion) and all(c["supera"] for c in elegibles) and float(pct) > 0
        estrategias.append(
            {
                "nombre": e.nombre,
                "ensayada": bool(e.transcripcion),
                "recomendada": e.nombre == neg.elegida,
                "concesion_obtenida_pct": e.concesion_obtenida_pct,
                "ganancia_esperada_uyu": float(e.ganancia_esperada_uyu),
                "oferta": oferta,
                "dimensiones": resumen,
                "comparaciones": comparaciones,
                "supera_a": sum(1 for c in elegibles if c["supera"]),
                "elegibles": len(elegibles),
                "gana": gana,
                "riesgo_gemelo": e.riesgo,
                "riesgo_plazo": riesgo_plazo,
                "riesgo": riesgo,
                "conclusion": _conclusion(e.nombre, e.transcripcion, float(pct), elegibles, gana),
            }
        )
    return {
        "negociacion_id": neg.id,
        "pedido_id": neg.pedido_id,
        "proveedor_id": neg.proveedor_id,
        "proveedor_nombre": _nombre(neg.proveedor_id),
        "elegida": neg.elegida,
        "items": [
            {
                "producto_id": i["producto_id"],
                "nombre": catalogo.get(i["producto_id"], i["producto_id"]),
                "cantidad": i["cantidad"],
                "precio_cotizado": float(i["precio"]),
            }
            for i in items
        ],
        "condiciones_actuales": {
            "entrega_dias": propia.lead_time_dias,
            "pago_dias": propia.plazo_pago_dias,
            "garantia_meses": garantia_propia,
        },
        "referencia_regular": referencia,
        "margen_riesgo_dias": MARGEN_RIESGO_DIAS,
        "estrategias": estrategias,
        "datos_ejemplo": ["garantía"],
        "regla": (
            "La estrategia gana si la oferta resultante no queda peor que ningún otro proveedor elegible en "
            "precio, entrega, pago y garantía, y mejora al menos uno. Riesgo aceptable: entrega hasta "
            f"{MARGEN_RIESGO_DIAS} días más que un proveedor regular."
        ),
    }


def _resumen_dimensiones(
    oferta: dict[str, Any],
    competidores: list[dict[str, Any]],
    elegibles: list[dict[str, Any]],
    items: list[dict[str, Any]],
    precios: dict[str, Decimal],
) -> dict[str, Any]:
    """Cada dimensión contra el mejor de los demás proveedores elegibles (lo que muestran las tarjetas)."""
    ids = {c["proveedor_id"] for c in elegibles}
    rivales = [c for c in competidores if c["proveedor_id"] in ids]

    def mejor(clave: str, mayor: bool) -> dict[str, Any] | None:
        con_dato = [c for c in rivales if c[clave] is not None]
        if not con_dato:
            return None
        return (max if mayor else min)(con_dato, key=lambda c: c[clave])

    # Precio: por unidad contra el mejor precio unitario del resto en cada producto (primer producto).
    principal = items[0]["producto_id"] if items else None
    rival_precio = min(
        (c for c in rivales if principal in c["precios"]), key=lambda c: c["precios"][principal], default=None
    )
    propio_precio = float(round(precios[principal], 2)) if principal else None
    filas = {
        "precio": {
            "propio": propio_precio,
            "mejor_del_resto": rival_precio["precios"][principal] if rival_precio else None,
            "proveedor": rival_precio["nombre"] if rival_precio else None,
            "resultado": _comparar(
                propio_precio, rival_precio["precios"][principal] if rival_precio else None, mayor_es_mejor=False
            ),
        }
    }
    for dim, clave, mayor in (("entrega", "entrega_dias", False), ("pago", "pago_dias", True), ("garantia", "garantia_meses", True)):
        m = mejor(clave, mayor)
        filas[dim] = {
            "propio": oferta[clave],
            "mejor_del_resto": m[clave] if m else None,
            "proveedor": m["nombre"] if m else None,
            "resultado": _comparar(oferta[clave], m[clave] if m else None, mayor_es_mejor=mayor),
        }
    return filas


def _conclusion(nombre: str, transcripcion: list, pct: float, elegibles: list[dict[str, Any]], gana: bool) -> str:
    if not transcripcion:
        return "No se ensayó: no hay oferta resultante para comparar."
    if pct <= 0:
        return "El gemelo no cedió: la oferta queda igual a la cotizada."
    if not elegibles:
        return "No hay otros proveedores elegibles con los que comparar: la mejora es solo sobre lo cotizado."
    if gana:
        return f"La oferta resultante supera a los {len(elegibles)} proveedores elegibles del resto."
    peores = sorted(
        {dim for c in elegibles for dim, r in c["resultado"].items() if r == "peor"},
        key=["precio", "entrega", "pago", "garantia"].index,
    )
    texto = {"precio": "precio", "entrega": "entrega", "pago": "pago", "garantia": "garantía"}
    return "Mejora lo cotizado, pero queda peor que algún otro proveedor en " + ", ".join(texto[p] for p in peores) + "."
