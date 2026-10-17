"""Tests de la Capa 4 con los datos de la demo (pedido_demo.json → resultado_esperado_demo)."""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path

import pytest

from app.models import Cotizacion, ItemCotizado, Pedido, Plan, Proveedor
from app.optimizacion import datos_para_explicar, explicacion_plantilla, optimizar

DATA = Path(__file__).resolve().parents[2] / "data"

# proveedor: (envío, mínimo total, plazo de pago, lead time, {producto: mínimo por ítem})
CONDICIONES: dict[str, tuple[int, int | None, int, int, dict[str, float]]] = {
    "tecnoimport": (0, None, 30, 5, {}),
    "compuservice": (0, None, 0, 3, {"notebook": 5}),
    "papelera_del_sur": (0, None, 0, 1, {}),
    "muebleria_rivera": (0, None, 0, 10, {"silla": 20}),
    "ofisillas": (1200, None, 30, 7, {}),
    "distribuidora_oriental": (0, 8000, 30, 2, {}),
}


@pytest.fixture(scope="module")
def demo() -> dict:
    return json.loads((DATA / "pedido_demo.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pedido(demo: dict) -> Pedido:
    return Pedido.model_validate(demo["pedido"])


@pytest.fixture(scope="module")
def nombres(demo: dict) -> dict[str, str]:
    return {p["id"]: p["nombre"] for p in demo["catalogo"]}


@pytest.fixture(scope="module")
def proveedores() -> dict[str, Proveedor]:
    sim = json.loads((DATA / "proveedores_sim.json").read_text(encoding="utf-8"))
    return {
        p["publico"]["id"]: Proveedor.model_validate(p["publico"]) for p in sim["proveedores"]
    }


def _cotizacion(proveedor_id: str, precios: dict[str, float], **cambios) -> Cotizacion:
    envio, minimo_total, plazo, lead, minimos = CONDICIONES[proveedor_id]
    items = [
        ItemCotizado(
            producto_id=producto_id,
            precio_unitario_sin_iva=Decimal(str(precio)),
            precio_original=Decimal(str(precio)),
            moneda_original="UYU",
            incluye_iva_original=False,
            unidad_original="unidad",
            cantidad_minima=minimos.get(producto_id),
            evidencia=f"{producto_id} {precio}",
        )
        for producto_id, precio in precios.items()
    ]
    datos = dict(
        id=f"cot_{proveedor_id}",
        pedido_id="pedido_demo_oct_2026",
        mensaje_id=f"msg_{proveedor_id}",
        proveedor_id=proveedor_id,
        items=items,
        costo_envio=Decimal(envio),
        pedido_minimo_total=Decimal(minimo_total) if minimo_total else None,
        plazo_pago_dias=plazo,
        lead_time_dias=lead,
        confianza=0.9,
    )
    return Cotizacion(**(datos | cambios))


@pytest.fixture(scope="module")
def cotizaciones(demo: dict) -> list[Cotizacion]:
    precios = demo["resultado_esperado_demo"]["precios_normalizados_sin_iva"]
    por_proveedor: dict[str, dict[str, float]] = {}
    for producto_id, ofertas in precios.items():
        for proveedor_id, precio in ofertas.items():
            por_proveedor.setdefault(proveedor_id, {})[producto_id] = precio
    return [_cotizacion(j, por_proveedor[j]) for j in CONDICIONES]


def _optimizar(pedido, cotizaciones, proveedores, nombres) -> Plan:
    return optimizar(
        pedido, cotizaciones, proveedores, tipo_cambio_usd=40.0, nombres_productos=nombres
    )


@pytest.fixture(scope="module")
def plan(pedido, cotizaciones, proveedores, nombres) -> Plan:
    return _optimizar(pedido, cotizaciones, proveedores, nombres)


def _asignado(plan: Plan) -> dict[str, set[str]]:
    resultado: dict[str, set[str]] = {}
    for a in plan.asignaciones:
        resultado.setdefault(a.producto_id, set()).add(a.proveedor_id)
    return resultado


# ---------------------------------------------------------------- demo
def test_asignaciones_demo(plan: Plan) -> None:
    assert _asignado(plan) == {
        "notebook": {"compuservice"},
        "toner": {"compuservice"},
        "resma_a4": {"papelera_del_sur"},
        "desinfectante": {"papelera_del_sur"},
        "silla": {"ofisillas"},
    }
    assert sorted(plan.proveedores_usados) == ["compuservice", "ofisillas", "papelera_del_sur"]
    assert plan.relajaciones == []
    assert plan.cotizaciones_excluidas == []


def test_costos_demo(plan: Plan) -> None:
    assert abs(plan.costo_total - Decimal("498454")) <= 2
    assert abs(plan.costo_baseline - Decimal("542120")) <= 2
    assert abs(plan.ahorro - Decimal("43666")) <= 3
    assert plan.ahorro_pct == pytest.approx(8.05, abs=0.02)
    assert plan.ahorro_pct_comparable == pytest.approx(16.3, abs=0.1)
    assert plan.costo_total.as_tuple().exponent == -2


def test_sillas_no_mas_barato(plan: Plan) -> None:
    sillas = [c for c in plan.no_mas_barato if c.producto_id == "silla"]
    assert len(sillas) == 1
    caso = sillas[0]
    assert (caso.mas_barato_id, caso.elegido_id) == ("muebleria_rivera", "ofisillas")
    assert "mínimo 20" in caso.motivo
    assert any("Mueblería Rivera exige mínimo 20" in r for r in plan.restricciones_activas)


def test_oportunidad_negociacion(plan: Plan) -> None:
    assert plan.oportunidad_negociacion == "ofisillas"
    assert plan.brecha_oportunidad == Decimal("16500.00")


def test_explicacion_plantilla(plan: Plan, proveedores, nombres) -> None:
    texto = plan.explicacion
    assert plan.explicacion_origen == "plantilla"
    assert "$ 498.454" in texto and "$ 43.666" in texto
    assert "Mueblería Rivera" in texto and "mínimo 20" in texto
    assert "Distribuidora Oriental" in texto
    assert 3 <= texto.count(". ") + 1 <= 5
    assert "*" not in texto and "\n" not in texto
    assert explicacion_plantilla(plan, proveedores, nombres)  # firma corta también funciona


def test_datos_para_explicar(plan: Plan, proveedores, nombres) -> None:
    datos = datos_para_explicar(plan, proveedores, nombres, habitual_id="distribuidora_oriental")
    esperadas = {
        "asignaciones",
        "costo_total",
        "tipo_cambio",
        "habitual",
        "baseline",
        "ahorro",
        "ahorro_pct",
        "ahorro_pct_comparable",
        "restricciones_activas",
        "relajaciones",
        "no_mas_barato",
    }
    assert set(datos) == esperadas
    assert all(isinstance(v, str) for v in datos.values())
    assert datos["habitual"] == "Distribuidora Oriental"
    assert datos["costo_total"] == "498.454"
    assert "Ofisillas" in datos["no_mas_barato"]


def test_tarda_menos_de_2_segundos(pedido, cotizaciones, proveedores, nombres) -> None:
    inicio = time.perf_counter()
    _optimizar(pedido, cotizaciones, proveedores, nombres)
    assert time.perf_counter() - inicio < 2


# ---------------------------------------------------------------- casos borde
def test_cotizacion_en_revisar_queda_excluida(pedido, cotizaciones, proveedores, nombres) -> None:
    cotis = [
        c.model_copy(update={"estado": "revisar"}) if c.proveedor_id == "ofisillas" else c
        for c in cotizaciones
    ]
    plan = _optimizar(pedido, cotis, proveedores, nombres)
    assert plan.cotizaciones_excluidas == ["cot_ofisillas"]
    assert "ofisillas" not in plan.proveedores_usados
    assert _asignado(plan)["silla"] == {"distribuidora_oriental"}


def test_infactible_por_plazo_relaja(pedido, proveedores, nombres) -> None:
    # Solo TecnoImport cotiza notebooks y tarda 9 días; se necesitan en 8.
    cotis = [
        _cotizacion("tecnoimport", {"notebook": 31200}, lead_time_dias=9),
        _cotizacion("papelera_del_sur", {"resma_a4": 178.69, "desinfectante": 113.11}),
        _cotizacion("ofisillas", {"silla": 10900}),
        _cotizacion("compuservice", {"toner": 3196.72}),
    ]
    plan = _optimizar(pedido, cotis, proveedores, nombres)
    assert _asignado(plan)["notebook"] == {"tecnoimport"}
    assert len(plan.relajaciones) == 1
    assert "plazo" in plan.relajaciones[0] and "Notebook" in plan.relajaciones[0]
    assert "plazo" in plan.explicacion


def test_producto_sin_cotizaciones(pedido, proveedores, nombres) -> None:
    cotis = [
        _cotizacion("papelera_del_sur", {"resma_a4": 178.69, "desinfectante": 113.11}),
        _cotizacion("ofisillas", {"silla": 10900}),
        _cotizacion("compuservice", {"toner": 3196.72}),
    ]
    plan = _optimizar(pedido, cotis, proveedores, nombres)
    assert "notebook" not in _asignado(plan)
    assert any(r.startswith("Sin cotizaciones para Notebook") for r in plan.relajaciones)


def test_max_prov_se_relaja(pedido, cotizaciones, proveedores, nombres) -> None:
    plan = optimizar(
        pedido,
        cotizaciones,
        proveedores,
        tipo_cambio_usd=40.0,
        nombres_productos=nombres,
        max_prov=2,
    )
    # Con 2 proveedores sí hay solución (p. ej. Compuservice + Distribuidora Oriental).
    assert len(plan.proveedores_usados) <= 2
    assert plan.relajaciones == []
    assert any("Límite de 2 proveedores" in r for r in plan.restricciones_activas)

    plan_1 = optimizar(
        pedido,
        cotizaciones,
        proveedores,
        tipo_cambio_usd=40.0,
        nombres_productos=nombres,
        max_prov=1,
    )
    assert any("límite de 1 proveedor:" in r for r in plan_1.relajaciones)
