"""Bloque 4 — Proveedores y negociación (RF-07, RF-16, RF-17, RF-19). Sin LLM ni demoras."""

from __future__ import annotations

import dataclasses
import sys
import time
import types
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import auth, config, perfiles, pipeline, ranking, store
from app.main import app
from app.models import Llamada, ResultadoLlamada

PEDIDO = "pedido_demo_oct_2026"


@pytest.fixture()
def client():
    # Editar perfiles y aprobar altas pide sesión de administrador (RF-21): el cliente entra como Lucía.
    with TestClient(app, headers={"Authorization": f"Bearer {auth.emitir_token('u_lucia')}"}) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _cotizar_y_confirmar(client: TestClient) -> None:
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 30
    while time.time() < limite:
        mensajes = client.get(f"/pedidos/{PEDIDO}/mensajes").json()
        if len(mensajes) == 6 and all(m["estado"] in ("extraido", "error") for m in mensajes):
            break
        time.sleep(0.1)
    cots = client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()
    compu = next(c for c in cots if c["proveedor_id"] == "compuservice")
    client.post(f"/cotizaciones/{compu['id']}/confirmar", json={"incluye_iva": True})


def _negociar(client: TestClient, monkeypatch) -> dict:
    async def ensayar(contexto):
        base = {"descripcion": "x", "transcripcion": [{"rol": "abasto", "texto": "hola"}]}
        return {
            "estrategias": [
                {**base, "nombre": "competencia", "concesion_obtenida_pct": 0.0, "riesgo": "medio"},
                {**base, "nombre": "volumen", "concesion_obtenida_pct": 5.0, "riesgo": "bajo"},
                {**base, "nombre": "plazo", "concesion_obtenida_pct": 3.0, "riesgo": "bajo"},
            ],
            "elegida": "volumen",
            "mensaje_propuesto": "Hola!",
        }

    monkeypatch.setitem(sys.modules, "app.negociacion", types.SimpleNamespace(ensayar=ensayar))
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test"))
    monkeypatch.setitem(sys.modules, "app.explicacion", types.SimpleNamespace())
    _cotizar_y_confirmar(client)
    assert client.post(f"/pedidos/{PEDIDO}/optimizar").status_code == 200
    r = client.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- RF-17
def test_listado_con_perfil_y_confianza(client):
    datos = client.get("/proveedores/listado").json()
    provs = {p["id"]: p for p in datos["proveedores"]}
    assert len(provs) == 6
    assert len(client.get("/proveedores").json()) == 6  # el endpoint viejo no cambia
    ofi = provs["ofisillas"]
    assert ofi["rubro"] and ofi["canal_preferido"] == "whatsapp_texto"
    assert ofi["antiguedad"]["texto"].endswith("años") and ofi["cumplimiento_historico_pct"] == 84
    assert ofi["datos_ejemplo"] is True
    assert ofi["perfil"]["concesion_tipica_rango"] == "2–6 %" and ofi["perfil"]["precio_piso_pct"] == 8
    assert "pago contado" in ofi["perfil"]["sensible_a"]
    assert ofi["confianza"]["nivel"] == "media"  # desvío 2,1 pp en 4 negociaciones de ejemplo
    assert provs["distribuidora_oriental"]["confianza"]["nivel"] == "alta"
    assert provs["distribuidora_oriental"]["habitual"] is True
    assert provs["compuservice"]["confianza"]["nivel"] == "baja"  # menos de 3 negociaciones


def test_confianza_umbrales():
    fila = lambda d: {"cuenta_para_confianza": True, "desvio_pp": d}  # noqa: E731
    assert perfiles.confianza([fila(1), fila(-2), fila(2)])["nivel"] == "alta"
    assert perfiles.confianza([fila(4), fila(-5), fila(3)])["nivel"] == "media"
    assert perfiles.confianza([fila(6), fila(-7), fila(5)])["nivel"] == "baja"
    assert perfiles.confianza([fila(0), fila(0)])["nivel"] == "baja"  # menos de 3
    assert perfiles.confianza([])["nivel"] == "baja"
    assert perfiles.confianza([], es_nuevo=True)["nivel"] == "sin_datos"


def test_perfil_editable_alimenta_al_gemelo(client):
    perfil = client.get("/proveedores/ofisillas/perfil").json()
    assert perfil["precio_piso_pct"] == 8 and perfil["editado"] is False
    assert perfil["tiempo_respuesta"]["canales"] == [] and perfil["tiempo_respuesta"]["llamadas"] is None
    r = client.patch(
        "/proveedores/ofisillas/perfil",
        json={"precio_piso_pct": 6, "sensible_a": ["pago contado"], "motivo": "última negociación", "usuario": "Lucía"},
    )
    assert r.status_code == 200, r.text
    editado = r.json()
    assert editado["precio_piso_pct"] == 6 and editado["sensible_a"] == ["pago contado"]
    assert editado["version"] == 1 and editado["actualizado_por"] == "Lucía"
    assert editado["historial_ediciones"][0]["cambios"]["precio_piso_pct"] == {"antes": 8, "despues": 6}
    privado = pipeline.perfil_privado("ofisillas")
    assert privado["precio_piso_pct"] == 6 and privado["sensible_a"] == ["pago contado"]
    assert privado["tabla_precios"]  # lo no editable queda igual
    assert client.patch("/proveedores/no_existe/perfil", json={}).status_code == 404
    assert client.patch("/proveedores/ofisillas/perfil", json={"precio_piso_pct": -1}).status_code == 422


def test_historial_y_tiempos_con_negociacion_real(client, monkeypatch):
    neg = _negociar(client, monkeypatch)
    perfil = client.get("/proveedores/ofisillas/perfil").json()
    canales = {c["canal"]: c for c in perfil["tiempo_respuesta"]["canales"]}
    assert "whatsapp_texto" in canales and canales["whatsapp_texto"]["respuestas"] == 1
    fila = next(h for h in perfil["historial_negociaciones"] if h["negociacion_id"] == neg["id"])
    assert fila["concesion_simulada_pct"] == 5.0 and fila["concesion_real_pct"] is None
    antes = perfil["confianza"]["negociaciones"]

    # Una llamada REAL que cerró a 10.464 (−4 %): desvío 1 pp, cuenta para la confianza.
    llamada = Llamada(
        id="lla_test", pedido_id=PEDIDO, proveedor_id="ofisillas", tipo="negociacion", negociacion_id=neg["id"],
        modo="real", estado="terminada", iniciada_en=datetime.now(), duracion_segundos=90,
        resultado=ResultadoLlamada(acuerdo=True, precio_acordado=10464),
    )
    store.guardar("llamadas", llamada)
    perfil = client.get("/proveedores/ofisillas/perfil").json()
    fila = next(h for h in perfil["historial_negociaciones"] if h["negociacion_id"] == neg["id"])
    assert fila["concesion_real_pct"] == 4.0 and fila["desvio_pp"] == 1.0 and fila["cuenta_para_confianza"]
    assert perfil["confianza"]["negociaciones"] == antes + 1
    assert perfil["tiempo_respuesta"]["llamadas"]["atendidas"] == 1

    # La misma llamada pero simulada repite al gemelo: no cuenta.
    store.guardar("llamadas", llamada.model_copy(update={"modo": "simulada"}))
    fila = next(
        h for h in client.get("/proveedores/ofisillas/perfil").json()["historial_negociaciones"]
        if h["negociacion_id"] == neg["id"]
    )
    assert fila["cuenta_para_confianza"] is False and "simulada" in fila["nota"]


# ---------------------------------------------------------------- RF-19
def test_alta_por_agente_queda_en_revision_y_se_aprueba(client):
    r = client.post(
        "/proveedores/alta-agente",
        json={"nombre": "Distribuidora Norte", "telefono": "+59899000111", "productos": ["silla"], "pedido_id": PEDIDO},
    )
    assert r.status_code == 201, r.text
    alta = r.json()
    assert alta["estado"] == "en_revision" and alta["alta_por"] == "agente" and alta["simulada"] is True
    assert alta["razon_social"] == "Distribuidora Norte S.R.L."
    textos = " ".join(t["texto"] for t in alta["conversacion"]).lower()
    for dato in ("razón social", "contacto", "canales", "condiciones", "productos"):
        assert dato in textos
    assert alta["condiciones"]["plazo_pago_dias"] == 30 and alta["productos"] == ["silla"]

    provs = {p["id"]: p for p in client.get("/proveedores/listado").json()["proveedores"]}
    nuevo = provs[alta["id"]]
    assert nuevo["estado"] == "en_revision" and nuevo["confianza"]["nivel"] == "sin_datos"
    assert nuevo["antiguedad"]["texto"] == "nuevo"
    perfil = client.get(f"/proveedores/{alta['id']}/perfil").json()
    assert perfil["alta"]["conversacion"] and perfil["confianza"]["nivel"] == "sin_datos"
    assert "mínimo sin mínimo" not in perfil["condiciones_habituales"]
    assert client.get("/proveedores/ofisillas/perfil").json()["alta"] is None

    aprobada = client.post(f"/proveedores/{alta['id']}/aprobar-alta", json={"usuario": "Lucía"}).json()
    assert aprobada["estado"] == "activo" and aprobada["aprobado_por"] == "Lucía"
    assert client.post(f"/proveedores/{alta['id']}/aprobar-alta").status_code == 409
    assert client.post("/proveedores/no_existe/aprobar-alta").status_code == 404
    assert len(client.get("/proveedores").json()) == 6  # no entra al simulador ni al optimizador


def test_alta_manual_queda_activa(client):
    r = client.post(
        "/proveedores/alta",
        json={"nombre": "Insumos del Este", "rubro": "limpieza", "condiciones": {"plazo_pago_dias": 15}},
    )
    assert r.status_code == 201 and r.json()["estado"] == "activo" and r.json()["alta_por"] == "usuario"
    assert client.post("/proveedores/alta", json={"nombre": ""}).status_code == 422


# ---------------------------------------------------------------- RF-07
def test_ranking_sillas_en_cascada(client):
    _cotizar_y_confirmar(client)
    r = client.get(f"/pedidos/{PEDIDO}/ranking", params={"producto_id": "silla"})
    assert r.status_code == 200, r.text
    (silla,) = r.json()["productos"]
    assert [p["proveedor_id"] for p in silla["ranking"]] == ["ofisillas", "distribuidora_oriental"]
    primero = silla["ranking"][0]
    assert primero["posicion"] == 1 and primero["criterio"] == "precio" and "Menor costo comparable" in primero["motivo"]
    assert primero["garantia_meses"] == 12 and primero["antiguedad"] and primero["cumplimiento_historico_pct"] == 84
    (rivera,) = silla["excluidos"]
    assert rivera["proveedor_id"] == "muebleria_rivera" and rivera["tipo_exclusion"] == "minimo"
    assert "mínimo" in rivera["motivo"] and "20" in rivera["motivo"]
    notebook = client.get(f"/pedidos/{PEDIDO}/ranking", params={"producto_id": "notebook"}).json()["productos"][0]
    assert not any(c["motivo"].endswith("..") for c in notebook["ranking"])  # "TecnoImport S.A."
    assert silla["pocos_proveedores"] is True and silla["sugerencia_alta"]


def test_ranking_todo_el_pedido_y_errores(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    time.sleep(0.5)
    cots_listas = False
    for _ in range(100):
        ms = client.get(f"/pedidos/{PEDIDO}/mensajes").json()
        if len(ms) == 6 and all(m["estado"] == "extraido" for m in ms):
            cots_listas = True
            break
        time.sleep(0.1)
    assert cots_listas
    datos = client.get(f"/pedidos/{PEDIDO}/ranking").json()
    por_producto = {p["producto_id"]: p for p in datos["productos"]}
    assert set(por_producto) == {"notebook", "silla", "resma_a4", "toner", "desinfectante"}
    notebook = por_producto["notebook"]  # Compuservice con IVA sin confirmar: excluido por "revisar"
    assert [p["proveedor_id"] for p in notebook["ranking"]] == ["tecnoimport"]
    assert notebook["excluidos"][0]["tipo_exclusion"] == "revisar"
    assert datos["regla"] and datos["datos_ejemplo"]
    assert client.get("/pedidos/no_existe/ranking").status_code == 404
    assert client.get(f"/pedidos/{PEDIDO}/ranking", params={"producto_id": "nada"}).status_code == 404


def test_ranking_desempata_por_atributos_y_antiguedad():
    base = dict(especificaciones="cumple", garantia_meses=None, cumplimiento_historico_pct=80)
    a = dict(base, proveedor_id="a", nombre="A", costo_comparable=100.0, entrega_dias=5, pago_dias=30, antiguedad_dias=100, antiguedad="x")
    b = dict(base, proveedor_id="b", nombre="B", costo_comparable=100.5, entrega_dias=2, pago_dias=30, antiguedad_dias=100, antiguedad="x")
    c = dict(base, proveedor_id="c", nombre="C", costo_comparable=150.0, entrega_dias=2, pago_dias=0, antiguedad_dias=10, antiguedad="x")
    d = dict(base, proveedor_id="d", nombre="D", costo_comparable=150.0, entrega_dias=2, pago_dias=0, antiguedad_dias=900, antiguedad="x")
    orden = ranking.ordenar([a, b, c, d])
    assert [x["nombre"] for x in orden] == ["B", "A", "D", "C"]
    assert orden[0]["criterio"] == "atributos" and "entrega en 2 días" in orden[0]["motivo"]
    assert orden[2]["criterio"] == "antiguedad" and "antigüedad" in orden[2]["motivo"]


# ---------------------------------------------------------------- RF-16
def test_evaluacion_de_la_negociacion(client, monkeypatch):
    neg = _negociar(client, monkeypatch)
    r = client.get(f"/negociaciones/{neg['id']}/evaluacion")
    assert r.status_code == 200, r.text
    ev = r.json()
    assert ev["proveedor_id"] == "ofisillas" and ev["items"][0]["producto_id"] == "silla"
    assert ev["referencia_regular"]["proveedor_id"] == "distribuidora_oriental"  # el habitual vende sillas
    est = {e["nombre"]: e for e in ev["estrategias"]}
    volumen = est["volumen"]
    assert volumen["recomendada"] and volumen["oferta"]["precios"]["silla"] == 10355.0
    assert volumen["oferta"]["pago_dias"] == 30
    assert volumen["riesgo_plazo"]["nivel"] == "aceptable" and volumen["riesgo_plazo"]["diferencia_dias"] == 5
    dist = next(c for c in volumen["comparaciones"] if c["proveedor_id"] == "distribuidora_oriental")
    assert dist["resultado"]["precio"] == "mejora" and dist["resultado"]["entrega"] == "peor"
    assert dist["supera"] is False and volumen["gana"] is False
    rivera = next(c for c in volumen["comparaciones"] if c["proveedor_id"] == "muebleria_rivera")
    assert rivera["elegible"] is False and "mínimo" in rivera["motivo_no_elegible"]
    assert est["plazo"]["oferta"]["pago_dias"] == 0  # pago contado
    assert est["plazo"]["dimensiones"]["pago"]["resultado"] == "peor"
    assert est["competencia"]["conclusion"].startswith("El gemelo no cedió")
    assert client.get("/negociaciones/no_existe/evaluacion").status_code == 404


def test_riesgo_plazo_regla_15_dias():
    ref = {"nombre": "Habitual", "entrega_dias": 2}
    assert ranking._riesgo_plazo(2, ref)["nivel"] == "bajo"
    assert ranking._riesgo_plazo(17, ref)["nivel"] == "aceptable"
    assert ranking._riesgo_plazo(18, ref)["nivel"] == "alto"
    assert ranking._riesgo_plazo(5, None)["nivel"] == "sin_dato"


def test_editar_perfil_y_aprobar_alta_piden_administrador():
    with TestClient(app) as c:
        assert c.patch("/proveedores/ofisillas/perfil", json={"precio_piso_pct": 6}).status_code == 401
        consulta = {"Authorization": f"Bearer {auth.emitir_token('u_martin')}"}
        assert c.patch("/proveedores/ofisillas/perfil", json={"precio_piso_pct": 6}, headers=consulta).status_code == 403
        assert c.post("/proveedores/x/aprobar-alta", headers=consulta).status_code == 403
