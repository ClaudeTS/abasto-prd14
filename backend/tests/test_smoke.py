"""Smoke tests de los endpoints críticos (AGENTS §2: solo lo que rompe la demo).

Corren sin API key y sin demoras: simulador y extracción con los fixtures de data/.
"""

from __future__ import annotations

import dataclasses
import sys
import time
import types

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

PEDIDO = "pedido_demo_oct_2026"


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _esperar_cotizaciones(client: TestClient, n: int = 6, timeout: float = 30) -> list[dict]:
    limite = time.time() + timeout
    while time.time() < limite:
        mensajes = client.get(f"/pedidos/{PEDIDO}/mensajes").json()
        if len(mensajes) == n and all(m["estado"] in ("extraido", "error") for m in mensajes):
            return mensajes
        time.sleep(0.1)
    raise AssertionError(f"No llegaron {n} mensajes extraídos: {mensajes}")


def _cotizar_y_confirmar(client: TestClient) -> list[dict]:
    assert client.post(f"/pedidos/{PEDIDO}/cotizar").json()["estado"] == "cotizando"
    _esperar_cotizaciones(client)
    cots = client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()
    compu = next(c for c in cots if c["proveedor_id"] == "compuservice")
    r = client.post(f"/cotizaciones/{compu['id']}/confirmar", json={"incluye_iva": True})
    assert r.status_code == 200, r.text
    return client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()


def test_health_y_pedido(client):
    assert client.get("/health").json()["ok"] is True
    pedido = client.get("/pedidos/demo").json()
    assert pedido["id"] == PEDIDO and len(pedido["lineas"]) == 5
    assert pedido["tipo_cambio_usd"] == 40.0 and len(pedido["catalogo"]) == 5
    assert len(client.get("/proveedores").json()) == 6


def test_error_con_forma_unica(client):
    r = client.get("/pedidos/no_existe")
    assert r.status_code == 404 and set(r.json()) == {"error", "detalle"}


def test_cotizar_extrae_las_6_con_evidencia(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    mensajes = _esperar_cotizaciones(client)
    assert {m["canal"] for m in mensajes} == {"whatsapp_texto", "whatsapp_audio", "pdf", "foto"}
    assert all(m["estado"] == "extraido" and m["cotizacion_id"] for m in mensajes)
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "cotizado"

    cots = {c["proveedor_id"]: c for c in client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()}
    assert len(cots) == 6
    assert all(i["evidencia"] for c in cots.values() for i in c["items"])  # nunca sin fuente
    assert cots["compuservice"]["estado"] == "revisar" and "iva" in cots["compuservice"]["campos_dudosos"]
    tecno = {i["producto_id"]: i for i in cots["tecnoimport"]["items"]}
    assert tecno["notebook"]["precio_unitario_sin_iva"] == 31200.0
    assert tecno["notebook"]["conversion_aplicada"] == "USD 780 × 40,00 = UYU 31.200"
    papelera = {i["producto_id"]: i for i in cots["papelera_del_sur"]["items"]}
    assert papelera["resma_a4"]["precio_unitario_sin_iva"] == 178.69

    estados = client.get(f"/pedidos/{PEDIDO}/proveedores/estado").json()
    assert all(e["estado"] == "respondio" for e in estados)


def test_cotizar_es_idempotente_mientras_corre(client, monkeypatch):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, sim_delay_seconds=4))
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    segundo = client.post(f"/pedidos/{PEDIDO}/cotizar").json()
    assert segundo.get("ya_estaba_en_curso") is True
    esperando = [e for e in client.get(f"/pedidos/{PEDIDO}/proveedores/estado").json() if e["estado"] == "esperando"]
    assert esperando and all(e["responde_en_segundos"] > 0 for e in esperando)
    r = client.post(f"/pedidos/{PEDIDO}/optimizar")
    assert r.status_code == 409 and "Faltan respuestas" in r.json()["error"]


def test_archivos_servidos(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    mensajes = {m["canal"]: m for m in _esperar_cotizaciones(client)}
    pdf = client.get(mensajes["pdf"]["archivo_url"])
    foto = client.get(mensajes["foto"]["archivo_url"])
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert foto.status_code == 200 and foto.headers["content-type"] == "image/jpeg"
    assert client.get("/archivos/..%2F..%2Fsecreto").status_code == 404


def test_confirmar_iva_corrige_precio(client):
    cots = {c["proveedor_id"]: c for c in _cotizar_y_confirmar(client)}
    compu = cots["compuservice"]
    assert compu["estado"] == "confirmada" and "iva" not in compu["campos_dudosos"]
    notebook = next(i for i in compu["items"] if i["producto_id"] == "notebook")
    assert notebook["precio_unitario_sin_iva"] == 27459.02
    assert notebook["conversion_aplicada"].startswith("con IVA")


def test_optimizar_bloquea_si_hay_que_revisar(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    _esperar_cotizaciones(client)
    r = client.post(f"/pedidos/{PEDIDO}/optimizar")
    assert r.status_code == 409 and "Compuservice" in r.json()["error"]
    forzado = client.post(f"/pedidos/{PEDIDO}/optimizar?forzar=true")
    assert forzado.status_code == 200
    assert any(c.startswith("cot_compuservice") for c in forzado.json()["cotizaciones_excluidas"])


def test_plan_de_la_demo(client):
    _cotizar_y_confirmar(client)
    r = client.post(f"/pedidos/{PEDIDO}/optimizar")
    assert r.status_code == 200, r.text
    plan = r.json()
    asign = {a["producto_id"]: a["proveedor_id"] for a in plan["asignaciones"]}
    assert asign == {
        "notebook": "compuservice",
        "toner": "compuservice",
        "resma_a4": "papelera_del_sur",
        "desinfectante": "papelera_del_sur",
        "silla": "ofisillas",
    }
    assert abs(plan["costo_total"] - 498454) < 2
    assert abs(plan["costo_baseline"] - 542120) < 2
    assert plan["oportunidad_negociacion"] == "ofisillas"
    assert any(n["producto_id"] == "silla" for n in plan["no_mas_barato"])
    assert plan["explicacion"]
    assert client.get(f"/pedidos/{PEDIDO}/plan").json()["costo_total"] == plan["costo_total"]


def test_negociar_sin_capa_5_responde_501_con_contexto(client):
    _cotizar_y_confirmar(client)
    client.post(f"/pedidos/{PEDIDO}/optimizar")
    r = client.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
    assert r.status_code == 501
    contexto = r.json()["detalle"]["contexto"]
    silla = contexto["items"][0]
    assert silla["mejor_alternativa_proveedor_id"] == "muebleria_rivera"
    assert silla["mejor_alternativa_precio"] == 9800.0
    assert "mínimo 20" in silla["mejor_alternativa_condicion"]
    assert contexto["valor_en_juego_uyu"] == 163500.0


def test_negociar_y_aprobar_con_capa_5_falsa(client, monkeypatch):
    """Valida la integración con el rol A: la ganancia y la elección las pone el código."""

    async def ensayar(contexto):
        base = {"descripcion": "x", "transcripcion": [{"rol": "abasto", "texto": "hola"}]}
        return {
            "estrategias": [
                {**base, "nombre": "competencia", "concesion_obtenida_pct": 0.0, "ganancia_esperada_uyu": 999999, "riesgo": "alto"},
                {**base, "nombre": "volumen", "concesion_obtenida_pct": 5.0, "ganancia_esperada_uyu": 1, "riesgo": "bajo"},
                {**base, "nombre": "plazo", "concesion_obtenida_pct": 3.0, "ganancia_esperada_uyu": 1, "riesgo": "medio"},
            ],
            "elegida": "competencia",
            "mensaje_propuesto": "Hola! Si equipamos 10 puestos más, ¿nos dejás la silla a 10.350?",
        }

    monkeypatch.setitem(sys.modules, "app.negociacion", types.SimpleNamespace(ensayar=ensayar))
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test"))
    monkeypatch.setitem(sys.modules, "app.explicacion", types.SimpleNamespace())  # sin explicar_plan
    _cotizar_y_confirmar(client)
    client.post(f"/pedidos/{PEDIDO}/optimizar")
    r = client.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
    assert r.status_code == 200, r.text
    neg = r.json()
    assert neg["elegida"] == "volumen"  # la de "competencia" tiene riesgo alto
    volumen = next(e for e in neg["estrategias"] if e["nombre"] == "volumen")
    assert volumen["ganancia_esperada_uyu"] == 8175.0  # 5 % de 163.500, calculado en código

    aprobada = client.post(f"/negociaciones/{neg['id']}/aprobar", json={"mensaje": "Texto editado"}).json()
    assert aprobada["estado"] == "enviada_simulada" and aprobada["mensaje_propuesto"] == "Texto editado"
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "aprobado"


def test_extraer_directo(client):
    r = client.post("/extraer", data={"proveedor_id": "ofisillas", "texto": "silla a 9 lucas"})
    assert r.status_code == 503  # texto libre necesita la Capa 1 con LLM
    from app import store

    fijo = next(x for x in store.semilla("respuestas_fijas")["respuestas"] if x["proveedor_id"] == "ofisillas")
    r = client.post("/extraer", data={"proveedor_id": "ofisillas", "texto": fijo["contenido"]})
    assert r.status_code == 200 and r.json()["items"][0]["precio_unitario_sin_iva"] == 10900.0
    assert client.get(f"/pedidos/{PEDIDO}/mensajes").json() == []  # no ensucia el feed de la demo


def test_reset_rapido(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    _esperar_cotizaciones(client)
    inicio = time.time()
    assert client.post("/reset").json()["ok"] is True
    assert time.time() - inicio < 10
    assert client.get(f"/pedidos/{PEDIDO}/mensajes").json() == []
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "nuevo"
