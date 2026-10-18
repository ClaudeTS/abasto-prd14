"""Dashboard (RF-09): KPI de la §4 y recomendaciones de la IA con sus datos y enlace."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import recomendaciones, store
from app.explicacion import numeros_inventados
from app.main import app
from app.models import EstrategiaNegociacion, Negociacion

PEDIDO = "pedido_demo_oct_2026"
KPIS = {
    "tasa_compras_automaticas", "ahorro_cotizacion_inicial", "tiempo_pedido_a_orden",
    "cotizaciones_sin_correccion", "precision_gemelo", "efectividad_negociacion",
    "tasa_respuesta_proveedores", "tiempo_respuesta_por_canal", "tiempo_respuesta_pedidos_internos",
}


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _kpis(client, **params) -> dict[str, dict]:
    r = client.get("/dashboard", params=params)
    assert r.status_code == 200, r.text
    return {k["id"]: k for k in r.json()["kpis"]}


# ---------------------------------------------------------------- KPI
def test_dashboard_trae_los_kpi_de_la_seccion_4_con_meta_y_ejemplo(client):
    r = client.get("/dashboard", params={"desde": "2026-01-01", "hasta": "2026-10-18"}).json()
    kpis = {k["id"]: k for k in r["kpis"]}
    assert set(kpis) == KPIS
    for k in kpis.values():
        assert k["como_se_calcula"] and k["unidad"] in ("%", "h", "min", "pp")
        assert k["valor"] is not None and k["ejemplo"] is True and k["fuentes"]["ejemplo"] > 0
    assert kpis["precision_gemelo"]["meta"]["texto"] == "±2 pp" and kpis["precision_gemelo"]["meta"]["valor"] == 2.0
    assert all(k["meta"] is None for i, k in kpis.items() if i != "precision_gemelo")
    for i in ("tasa_compras_automaticas", "cotizaciones_sin_correccion", "efectividad_negociacion", "tasa_respuesta_proveedores"):
        assert 0 <= kpis[i]["valor"] <= 100
    canales = {t["canal"]: t for t in r["tiempo_por_canal"]}
    assert set(canales) == {"llamada", "whatsapp", "email"}
    assert canales["llamada"]["minutos"] < canales["whatsapp"]["minutos"] < canales["email"]["minutos"]
    assert r["ejemplo"] is True and "historial_compras.json" in r["nota_ejemplo"]


def test_periodo_por_defecto_ultimos_30_dias_y_validaciones(client):
    r = client.get("/dashboard").json()
    from datetime import date

    assert (date.fromisoformat(r["hasta"]) - date.fromisoformat(r["desde"])).days == 29
    assert client.get("/dashboard", params={"desde": "2026-10-10", "hasta": "2026-10-01"}).status_code == 422
    assert client.get("/dashboard", params={"cliente_interno": "gerencia"}).status_code == 422


def test_sin_datos_en_el_periodo_no_inventa_valores(client):
    kpis = _kpis(client, desde="2020-01-01", hasta="2020-01-31")
    assert all(k["valor"] is None and k["ejemplo"] is False for k in kpis.values())


def test_filtro_por_cliente_interno(client):
    params = {"desde": "2025-11-01", "hasta": "2026-10-18"}
    todos = _kpis(client, **params)["tasa_compras_automaticas"]["fuentes"]["ejemplo"]
    ventas = _kpis(client, cliente_interno="ventas", **params)["tasa_compras_automaticas"]["fuentes"]["ejemplo"]
    personal = _kpis(client, cliente_interno="personal", **params)["tasa_compras_automaticas"]["fuentes"]["ejemplo"]
    assert 0 < ventas < todos and ventas + personal == todos


def test_los_datos_reales_del_store_cuentan(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 10
    while time.time() < limite and len(client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()) < 6:
        time.sleep(0.05)
    kpis = _kpis(client)
    assert kpis["cotizaciones_sin_correccion"]["fuentes"]["reales"] == 6
    assert kpis["tasa_respuesta_proveedores"]["fuentes"]["reales"] == 6
    # Compuservice no aclaró el IVA: espera revisión y no cuenta como "sin corrección"
    assert "para revisar" in kpis["cotizaciones_sin_correccion"]["detalle"]
    # el simulador comprime las demoras: no entra en los tiempos de respuesta por canal
    assert kpis["tiempo_respuesta_por_canal"]["fuentes"]["reales"] == 0


# ---------------------------------------------------------------- recomendaciones
def _recos(client, **params) -> list[dict]:
    r = client.get("/dashboard/recomendaciones", params=params)
    assert r.status_code == 200, r.text
    return r.json()["recomendaciones"]


def test_recomendaciones_con_datos_que_las_respaldan_y_enlace(client):
    recos = _recos(client)
    tipos = {r["tipo"] for r in recos}
    assert {"alza_precio", "oferta_otro_proveedor", "canal_mas_rapido"} <= tipos
    for r in recos:
        assert r["datos"] and r["titulo"] and r["texto"] and r["texto_origen"] == "plantilla"
        assert r["enlace"]["ruta"].startswith(("/pedidos/", "/proveedores/", "/negociacion"))
        # nunca inventa números: todo lo del texto sale de sus datos
        datos = {d["etiqueta"]: f"{d['etiqueta']}: {d['valor']}" for d in r["datos"]}
        assert numeros_inventados(r["texto"], datos) == [], r
    alza = next(r for r in recos if r["tipo"] == "alza_precio")
    assert alza["producto_id"] == "toner" and alza["proveedor_id"] == "distribuidora_oriental"
    assert "$ 4.600" in alza["texto"] and alza["ejemplo"] is True
    resma = next(r for r in recos if r["id"] == "oferta.resma_a4.distribuidora_oriental.papelera_del_sur")
    assert resma["enlace"]["ruta"] == "/proveedores/papelera_del_sur"
    sillas = next(r for r in recos if r["tipo"] == "oferta_otro_proveedor" and r["producto_id"] == "silla")
    assert "mínimo de 20" in sillas["texto"]  # Mueblería Rivera exige 20: se avisa
    canal = next(r for r in recos if r["id"].startswith("canal.papelera_del_sur"))
    assert "llamada" in canal["titulo"]


def test_umbral_de_alza_configurable(client):
    assert any(r["tipo"] == "alza_precio" for r in _recos(client, umbral_alza_pct=8))
    assert not any(r["tipo"] == "alza_precio" for r in _recos(client, umbral_alza_pct=50))


def test_descartar_recomendacion(client):
    reco = _recos(client)[0]
    r = client.post(f"/dashboard/recomendaciones/{reco['id']}/descartar")
    assert r.status_code == 200 and r.json()["estado"] == "descartada"
    assert reco["id"] not in {x["id"] for x in _recos(client)}
    todas = client.get("/dashboard/recomendaciones", params={"incluir_descartadas": True}).json()
    assert todas["descartadas"] == 1
    assert next(x for x in todas["recomendaciones"] if x["id"] == reco["id"])["estado"] == "descartada"
    assert client.post("/dashboard/recomendaciones/no.existe/descartar").status_code == 404
    client.post("/reset")
    assert reco["id"] in {x["id"] for x in _recos(client)}


def test_negociacion_para_aprobar_aparece_en_pendientes(client):
    store.guardar("negociaciones", Negociacion(
        id="neg_test", pedido_id=PEDIDO, proveedor_id="ofisillas",
        estrategias=[EstrategiaNegociacion(
            nombre="volumen", descripcion="x", transcripcion=[], concesion_obtenida_pct=5.0,
            ganancia_esperada_uyu=Decimal("8175"), riesgo="bajo",
        )],
        elegida="volumen", mensaje_propuesto="Hola", estado="simulada",
    ))
    pendientes = client.get("/dashboard").json()["pendientes"]
    assert len(pendientes) == 1 and pendientes[0]["enlace"] == "/negociacion"
    assert "Ofisillas" in pendientes[0]["titulo"] and "5,0 %" in pendientes[0]["detalle"]
    primera = _recos(client)[0]
    assert primera["tipo"] == "pendiente_aprobacion" and primera["ejemplo"] is False
    assert primera["enlace"]["ruta"] == "/negociacion"


# ---------------------------------------------------------------- redacción con LLM
def test_el_llm_redacta_pero_no_puede_inventar_numeros(client, monkeypatch):
    from app import llm

    monkeypatch.setattr(recomendaciones, "_hay_llm", lambda: True)

    async def falso(*, system, contenido, esquema, **_):
        import json

        texto = contenido[0]["text"]
        entrada = json.loads(texto[texto.index("["): texto.index("\n\nPara cada")])
        salida = []
        for r in entrada:
            if r["tipo"] == "alza_precio":
                salida.append({"id": r["id"], "titulo": "El tóner subió", "texto": "Subió un 99 %, cambiá ya."})
            else:
                salida.append({"id": r["id"], "titulo": "Redactado por la IA", "texto": r["texto_base"]})
        return esquema.model_validate({"recomendaciones": salida})

    monkeypatch.setattr(llm, "pedir_json", falso)
    primera = _recos(client)
    assert all(r["texto_origen"] == "plantilla" for r in primera)  # se redacta en segundo plano
    limite = time.time() + 5
    while time.time() < limite:
        recos = _recos(client)
        if any(r["texto_origen"] == "llm" for r in recos):
            break
        time.sleep(0.05)
    alza = next(r for r in recos if r["tipo"] == "alza_precio")
    assert alza["texto_origen"] == "plantilla" and "99" not in alza["texto"]  # inventó un número: se descarta
    otras = [r for r in recos if r["tipo"] != "alza_precio"]
    assert otras and all(r["texto_origen"] == "llm" and r["titulo"] == "Redactado por la IA" for r in otras)
