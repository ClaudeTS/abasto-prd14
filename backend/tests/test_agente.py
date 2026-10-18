"""Agente de compras e inventario (docs/AGENTE.md), sin LLM y sin red: la frase de la demo se entiende
con su interpretación fija y la negociación es un gemelo falso."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import sys
import time
import types
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import agente, config, interpretacion, pipeline
from app.main import app

PEDIDO = "pedido_demo_oct_2026"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(agente, "INTERVALO_S", 0.05)
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


@pytest.fixture()
def gemelo(monkeypatch):
    """Negociación falsa (Capa 5) y extracción e interpretación con fixtures aunque haya "key"."""

    async def ensayar(contexto):
        base = {"descripcion": "x", "transcripcion": [{"rol": "abasto", "texto": "hola"}]}
        return {
            "estrategias": [
                {**base, "nombre": "competencia", "concesion_obtenida_pct": 0.0, "riesgo": "alto"},
                {**base, "nombre": "volumen", "concesion_obtenida_pct": 5.0, "riesgo": "bajo"},
                {**base, "nombre": "plazo", "concesion_obtenida_pct": 3.0, "riesgo": "medio"},
            ],
            "elegida": "volumen",
            "mensaje_propuesto": "Hola! Si equipamos 10 puestos más, ¿nos dejás la silla a 10.350?",
        }

    monkeypatch.setitem(sys.modules, "app.negociacion", types.SimpleNamespace(ensayar=ensayar))
    monkeypatch.setitem(sys.modules, "app.explicacion", types.SimpleNamespace())  # plantilla
    monkeypatch.setattr(
        config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test", extraccion_mode="fijo")
    )


def _esperar(client: TestClient, corrida_id: str, estados: tuple[str, ...], timeout: float = 20) -> dict:
    limite = time.time() + timeout
    while time.time() < limite:
        corrida = client.get(f"/agente/{corrida_id}").json()
        if corrida["estado"] in estados:
            return corrida
        time.sleep(0.05)
    raise AssertionError(f"La corrida no llegó a {estados}: {corrida['estado']} · {corrida['pasos']}")


def _paso(corrida: dict, paso_id: str) -> dict:
    return next(p for p in corrida["pasos"] if p["id"] == paso_id)


def _demo(client: TestClient, **opciones) -> dict:
    texto = client.get("/agente/ejemplo").json()["texto"]
    r = client.post("/agente", json={"texto": texto, "llamar_si_no_responde": False, **opciones})
    assert r.status_code == 201, r.text
    return r.json()


def test_la_reposicion_da_el_pedido_de_la_demo(client):
    """Con data/inventario_demo.json, los consumibles a 1 mes son las líneas de pedido_demo.json."""
    inv = client.get("/inventario").json()
    assert inv["fecha"] == "2026-10-20" and inv["meses_pronostico"] == ["2026-11"]
    repos = {p["producto_id"]: p["reposicion"] for p in inv["productos"] if p["reposicion"]}
    pedido = json.loads((config.REPO_DIR / "data" / "pedido_demo.json").read_text(encoding="utf-8"))["pedido"]
    esperado = {l["producto_id"]: l for l in pedido["lineas"] if l["producto_id"] in repos}
    assert set(esperado) == {"resma_a4", "toner", "desinfectante"}
    for producto_id, linea in esperado.items():
        assert repos[producto_id]["cantidad"] == linea["cantidad"], producto_id
        assert repos[producto_id]["necesario_para"] == linea["necesario_para"], producto_id
    resma = next(p for p in inv["productos"] if p["producto_id"] == "resma_a4")
    assert len(resma["historial"]) == 24 and resma["alerta"] == "bajo_minimo"
    assert "105,1 × índice 1,14 = 120" in resma["pronostico"]["evidencia"]
    assert "120 + mínimo 40 − stock 10 = 150" in resma["reposicion"]["evidencia"]
    notebook = next(p for p in inv["productos"] if p["producto_id"] == "notebook")
    assert notebook["pronostico"] is None and notebook["modo"] == "manual"
    dos = {p["producto_id"]: p["reposicion"] for p in client.get("/inventario?horizonte_meses=2").json()["productos"] if p["reposicion"]}
    assert dos["resma_a4"]["cantidad"] > 150  # noviembre + diciembre
    assert client.get("/inventario?horizonte_meses=9").status_code == 422


def test_cambiar_modo_y_tope(client):
    r = client.patch("/inventario/toner", json={"modo": "manual", "tope_automatico_uyu": 50000})
    assert r.status_code == 200, r.text
    assert r.json()["modo"] == "manual" and r.json()["tope_automatico_uyu"] == 50000
    assert client.patch("/inventario/toner", json={"tope_automatico_uyu": None}).json()["tope_automatico_uyu"] is None
    assert client.patch("/inventario/toner", json={"stock_actual": -1}).status_code == 422
    assert client.patch("/inventario/zzz", json={"modo": "manual"}).status_code == 404
    client.post("/reset")
    assert client.get("/inventario").json()["productos"][3]["modo"] == "automatico"


def test_compra_entera_con_la_frase_de_la_demo(client, gemelo):
    corrida = _esperar(client, _demo(client)["id"], ("esperando_confirmacion",))
    assert _paso(corrida, "entender")["detalle"] == "Pediste 10 notebooks para el 28/10 y 15 sillas para el 03/11."
    propuesta = [(l["producto_id"], l["cantidad"], l["necesario_para"], l["origen"]) for l in corrida["propuesta"]]
    assert propuesta == [
        ("notebook", 10, "2026-10-28", "pedido"),
        ("silla", 15, "2026-11-03", "pedido"),
        ("resma_a4", 150, "2026-10-23", "reposicion"),
        ("toner", 8, "2026-10-28", "reposicion"),
        ("desinfectante", 60, "2026-10-23", "reposicion"),
    ]
    assert all(not l["dudas"] for l in corrida["propuesta"])
    assert client.post("/agente", json={"texto": "otra"}).status_code == 409  # una compra a la vez

    assert client.post(f"/agente/{corrida['id']}/confirmar").status_code == 200
    corrida = _esperar(client, corrida["id"], ("esperando_revision",))
    pedido = client.get(f"/pedidos/{PEDIDO}").json()
    assert [(l["producto_id"], l["cantidad"]) for l in pedido["lineas"]] == [(p[0], p[1]) for p in propuesta]
    (duda,) = corrida["revision"]
    assert duda["proveedor_id"] == "compuservice" and duda["pide_iva"] is True

    r = client.post(f"/cotizaciones/{duda['cotizacion_id']}/confirmar", json={"incluye_iva": True})
    assert r.status_code == 200, r.text
    corrida = _esperar(client, corrida["id"], ("esperando_aprobacion",))
    assert _paso(corrida, "negociar")["estado"] == "hecho" and corrida["negociacion_id"]
    plan = client.get(f"/pedidos/{PEDIDO}/plan").json()
    assert abs(plan["costo_total"] - 498454) < 50
    ordenes = {o["proveedor_id"]: o for o in corrida["ordenes"]}
    assert set(ordenes) == {"compuservice", "ofisillas", "papelera_del_sur"}

    papelera = ordenes["papelera_del_sur"]  # resmas y desinfectante: automáticos y bajo su tope
    assert papelera["estado"] == "enviada_simulada" and papelera["aprobada_por"] == "agente"
    assert {l["aprobacion"] for l in papelera["lineas"]} == {"automatica"}
    assert all(l["evidencia"] for l in papelera["lineas"])
    compu = ordenes["compuservice"]  # notebooks en manual; tóner (25.574) supera el tope de 20.000
    assert compu["estado"] == "esperando_aprobacion"
    assert {l["producto_id"]: l["aprobacion"] for l in compu["lineas"]} == {"notebook": "manual", "toner": "supera_tope"}
    assert ordenes["ofisillas"]["negociacion_id"] == corrida["negociacion_id"]
    assert ordenes["ofisillas"]["envio"] == 1200

    inv = {p["producto_id"]: p for p in client.get("/inventario").json()["productos"]}
    assert inv["resma_a4"]["en_camino"] == 150 and inv["resma_a4"]["reposicion"]["cantidad"] == 0

    assert client.post(f"/agente/{corrida['id']}/ordenes/oc_compuservice/aprobar").status_code == 200
    r = client.post(f"/agente/{corrida['id']}/ordenes/oc_ofisillas/rechazar")
    corrida = r.json()
    assert corrida["estado"] == "completada" and "Rechazaste la de Ofisillas" in corrida["resumen"]
    assert client.post(f"/agente/{corrida['id']}/ordenes/oc_ofisillas/aprobar").status_code == 409
    assert client.get("/agente/actual").json()["id"] == corrida["id"]


DICTADO = (
    "abasto arma la compra del mes entran 10 personas nuevas el 28 y necesitan notebook y para la "
    "oficina nueva 15 sillas ergonomicas para el 3 de noviembre"
)


def _interpretar(texto: str):
    return asyncio.run(
        interpretacion.interpretar(texto, catalogo=pipeline.catalogo(), fecha=date(2026, 10, 20), negocio="Tecnova S.A.")
    )


def test_la_frase_dictada_tambien_se_entiende_sin_llm():
    leido = _interpretar(DICTADO)  # el dictado del navegador: sin puntuación y con cifras
    assert leido.origen == "fijo" and not leido.dudas
    assert [(i.producto_id, i.cantidad, i.necesario_para) for i in leido.items] == [
        ("notebook", 10, date(2026, 10, 28)),
        ("silla", 15, date(2026, 11, 3)),
    ]


def test_si_el_llm_falla_la_frase_de_la_demo_tiene_respaldo(monkeypatch):
    async def sin_credito(**_):
        raise RuntimeError("sin crédito")

    monkeypatch.setattr(interpretacion, "pedir_json", sin_credito)
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test"))
    assert _interpretar(DICTADO).origen == "fijo"
    with pytest.raises(RuntimeError, match="sin crédito"):
        _interpretar("Comprame tres sillas para el viernes")


def test_sin_llm_solo_entiende_la_frase_de_la_demo(client):
    r = client.post("/agente", json={"texto": "Comprame tres sillas para el viernes"})
    corrida = _esperar(client, r.json()["id"], ("error",))
    assert _paso(corrida, "entender")["estado"] == "error" and "LLM" in corrida["error"]
    # el pedido sigue sin cotizar: se puede volver a empezar sin resetear
    assert client.post("/agente", json={}).status_code == 201


def test_sin_texto_repone_y_sin_key_la_negociacion_no_frena_la_compra(client):
    corrida = client.post("/agente", json={"esperar_confirmacion": False, "llamar_si_no_responde": False}).json()
    corrida = _esperar(client, corrida["id"], ("esperando_revision",))
    assert _paso(corrida, "entender")["estado"] == "omitido" and _paso(corrida, "confirmar")["estado"] == "omitido"
    assert [l["producto_id"] for l in corrida["propuesta"]] == ["resma_a4", "toner", "desinfectante"]
    client.post(f"/cotizaciones/{corrida['revision'][0]['cotizacion_id']}/confirmar", json={"incluye_iva": True})
    corrida = _esperar(client, corrida["id"], ("esperando_aprobacion", "completada"))
    assert _paso(corrida, "negociar")["estado"] in ("error", "omitido")  # sin key: 501, sigue igual
    assert corrida["ordenes"] and corrida["error"] is None


def test_el_modo_que_cambia_en_plena_compra_vale_para_las_ordenes(client):
    opciones = {"esperar_confirmacion": False, "llamar_si_no_responde": False, "negociar": False}
    corrida = _esperar(client, client.post("/agente", json=opciones).json()["id"], ("esperando_revision",))
    assert client.patch("/inventario/desinfectante", json={"modo": "manual"}).status_code == 200
    client.post(f"/cotizaciones/{corrida['revision'][0]['cotizacion_id']}/confirmar", json={"incluye_iva": True})
    corrida = _esperar(client, corrida["id"], ("esperando_aprobacion",))
    assert _paso(corrida, "negociar")["estado"] == "omitido"
    papelera = next(o for o in corrida["ordenes"] if o["proveedor_id"] == "papelera_del_sur")
    assert papelera["estado"] == "esperando_aprobacion"
    assert papelera["motivos"] == ["Desinfectante: está en modo manual, la aprobás vos."]


def test_llama_al_que_no_responde(client, monkeypatch):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, sim_delay_seconds=0.4))
    monkeypatch.setattr(agente, "UMBRAL_MINIMO_S", 0.0)  # insiste a los 2,5 s; papelera responde a los 4
    corrida = client.post("/agente", json={"esperar_confirmacion": False}).json()
    corrida = _esperar(client, corrida["id"], ("esperando_revision",), timeout=30)
    insistir = _paso(corrida, "insistir")
    assert insistir["estado"] == "hecho" and "Papelera del Sur cotizó por teléfono" in insistir["detalle"]
    (llamada,) = client.get(f"/pedidos/{PEDIDO}/llamadas").json()
    assert llamada["id"] in corrida["llamada_ids"] and llamada["modo"] == "simulada"
    canales = {m["proveedor_id"]: m["canal"] for m in client.get(f"/pedidos/{PEDIDO}/mensajes").json()}
    assert canales["papelera_del_sur"] == "llamada"


def test_cancelar(client):
    corrida = _esperar(client, _demo(client)["id"], ("esperando_confirmacion",))
    corrida = client.post(f"/agente/{corrida['id']}/cancelar").json()
    assert corrida["estado"] == "cancelada" and _paso(corrida, "cotizar")["estado"] == "omitido"
    assert client.post(f"/agente/{corrida['id']}/confirmar").status_code == 409
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "nuevo"
