"""Llamadas del agente (docs/LLAMADAS.md): simuladas, y reales con ElevenLabs reemplazado en la
frontera HTTP (_disparar / _consultar) para verificar qué se manda y cómo se interpreta."""

from __future__ import annotations

import dataclasses
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import config, llamadas, store
from app.main import app
from app.models import EstrategiaNegociacion, Negociacion

PEDIDO = "pedido_demo_oct_2026"
TELEFONOS = {"papelera_del_sur": "+59899111222", "ofisillas": "+59899333444"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(llamadas, "INTERVALO_CONSULTA_S", 0.01)
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _ajustes(monkeypatch, **cambios):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, **cambios))


def _modo_real(monkeypatch, **extra):
    ajustes = {
        "llamadas_modo": "real",
        "elevenlabs_api_key": "xi-test",
        "elevenlabs_agent_id": "agent_test",
        "elevenlabs_phone_number_id": "phnum_test",
        "telefonos_proveedores": TELEFONOS,
    }
    _ajustes(monkeypatch, **{**ajustes, **extra})


def _cotizar_menos_papelera(client, monkeypatch):
    """Cotiza con demoras reales escaladas: todos responden menos la papelera (que tarda 40 s × escala)."""
    _ajustes(monkeypatch, sim_delay_seconds=0.4)  # papelera a los 4 s, el resto antes de 1 s
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 10
    while time.time() < limite:
        respondieron = {m["proveedor_id"] for m in client.get(f"/pedidos/{PEDIDO}/mensajes").json()}
        if len(respondieron) == 5:
            break
        time.sleep(0.05)
    assert "papelera_del_sur" not in respondieron


def _esperar_llamada(client, llamada_id, timeout=15):
    limite = time.time() + timeout
    while time.time() < limite:
        llamada = client.get(f"/llamadas/{llamada_id}").json()
        if llamada["estado"] in ("terminada", "fallida"):
            return llamada
        time.sleep(0.05)
    raise AssertionError(f"La llamada no terminó: {llamada}")


def _esperar_mensaje_llamada(client, proveedor_id, timeout=10):
    limite = time.time() + timeout
    while time.time() < limite:
        for m in client.get(f"/pedidos/{PEDIDO}/mensajes").json():
            if m["proveedor_id"] == proveedor_id and m["canal"] == "llamada" and m["estado"] in ("extraido", "error"):
                return m
        time.sleep(0.05)
    raise AssertionError("No llegó el mensaje de la llamada")


# ---------------------------------------------------------------- configuración
def test_config_por_defecto_simulada(client, monkeypatch):
    _ajustes(monkeypatch, llamadas_modo="simulada", telefonos_proveedores={})  # sin depender del .env local
    cfg = client.get("/llamadas/config").json()
    assert cfg == {"modo": "simulada", "lista": True, "faltan": [], "proveedores_con_telefono": []}


def test_modo_real_sin_configurar_responde_409_con_lo_que_falta(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _ajustes(monkeypatch, llamadas_modo="real")
    cfg = client.get("/llamadas/config").json()
    assert cfg["lista"] is False and "ELEVENLABS_API_KEY" in cfg["faltan"]
    r = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur")
    assert r.status_code == 409 and "Faltan variables" in r.json()["error"]


def test_enmascarar():
    assert llamadas.enmascarar("+59899111222") == "+598 99• ••• 222"
    assert llamadas.enmascarar(None) is None


# ---------------------------------------------------------------- llamada simulada de cotización
def test_llamada_simulada_trae_la_cotizacion_al_feed(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    llamada = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    assert llamada["modo"] == "simulada" and llamada["estado"] == "sonando"
    fin = _esperar_llamada(client, llamada["id"])
    assert fin["estado"] == "terminada" and len(fin["transcripcion"]) == 3
    assert fin["transcripcion"][0]["rol"] == "abasto" and "Tecnova" in fin["transcripcion"][0]["texto"]
    mensaje = _esperar_mensaje_llamada(client, "papelera_del_sur")
    assert mensaje["estado"] == "extraido" and mensaje["id"] == client.get(f"/llamadas/{llamada['id']}").json()["mensaje_id"]
    cot = next(c for c in client.get(f"/pedidos/{PEDIDO}/cotizaciones").json() if c["proveedor_id"] == "papelera_del_sur")
    assert {i["producto_id"]: i["precio_unitario_sin_iva"] for i in cot["items"]} == {"resma_a4": 178.69, "desinfectante": 113.11}
    # ya respondió: no se vuelve a llamar, y la respuesta simulada tardía no se duplica
    assert client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").status_code == 409
    time.sleep(4.5)
    papelera = [m for m in client.get(f"/pedidos/{PEDIDO}/mensajes").json() if m["proveedor_id"] == "papelera_del_sur"]
    assert len(papelera) == 1
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "cotizado"


def test_llamar_dos_veces_seguidas_devuelve_la_misma_llamada(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _ajustes(monkeypatch, sim_delay_seconds=4)  # que la llamada dure
    a = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    b = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    assert a["id"] == b["id"]


# ---------------------------------------------------------------- llamada real (ElevenLabs simulado)
def _elevenlabs_falso(monkeypatch, conversaciones: list[dict], enviado: dict):
    async def disparar(numero, variables):
        enviado.update(numero=numero, variables=variables)
        return {"success": True, "message": "ok", "conversation_id": "conv_123", "callSid": "CA123"}

    respuestas = iter(conversaciones)
    ultima = {}

    async def consultar(conversation_id):
        assert conversation_id == "conv_123"
        nonlocal ultima
        ultima = next(respuestas, ultima)
        return ultima

    monkeypatch.setattr(llamadas, "_disparar", disparar)
    monkeypatch.setattr(llamadas, "_consultar", consultar)


def test_llamada_real_cotizacion_interpreta_elevenlabs(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _modo_real(monkeypatch)
    turnos = [
        {"role": "agent", "message": "Hola, ¿hablo con Papelera del Sur?", "time_in_call_secs": 0},
        {"role": "user", "message": "Sí. La caja de cinco resmas te la dejo a mil noventa, con IVA.", "time_in_call_secs": 6},
    ]
    enviado: dict = {}
    _elevenlabs_falso(
        monkeypatch,
        [
            {"status": "initiated", "transcript": [], "metadata": {"call_duration_secs": 0}},
            {"status": "in-progress", "transcript": turnos[:1], "metadata": {"call_duration_secs": 3}},
            {"status": "processing", "transcript": turnos, "metadata": {"call_duration_secs": 41}},
            {
                "status": "done",
                "transcript": turnos,
                "metadata": {"call_duration_secs": 41, "phone_call": {"call_sid": "CA123", "call_result": "answered"}},
                "analysis": {"call_successful": "success", "transcript_summary": "Pasó el precio de las resmas."},
            },
        ],
        enviado,
    )
    llamada = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    assert llamada["modo"] == "real" and llamada["telefono"] == "+598 99• ••• 222"
    assert llamada["conversation_id"] == "conv_123" and llamada["call_sid"] == "CA123"
    # qué se le mandó a ElevenLabs: el número real y las instrucciones del pedido para ese proveedor
    assert enviado["numero"] == "+59899111222"
    v = enviado["variables"]
    assert v["tipo_llamada"] == "cotizacion" and v["proveedor_nombre"] == "Papelera del Sur"
    assert "Resma papel A4" in v["instrucciones"] and "Desinfectante" in v["instrucciones"]
    assert "Notebook" not in v["instrucciones"]  # solo lo que vende
    assert v["primer_mensaje"].startswith("Hola, ¿hablo con Papelera del Sur?")
    fin = _esperar_llamada(client, llamada["id"])
    assert fin["estado"] == "terminada" and fin["duracion_segundos"] == 41
    assert [t["rol"] for t in fin["transcripcion"]] == ["abasto", "proveedor"]
    assert fin["resultado"]["resumen"] == "Pasó el precio de las resmas."
    # Sin extracción con LLM no se inventa una lectura de lo que se dijo: el mensaje queda en error
    mensaje = _esperar_mensaje_llamada(client, "papelera_del_sur")
    assert mensaje["estado"] == "error" and "extracción con LLM" in mensaje["error"]
    assert "Papelera del Sur: Sí. La caja de cinco resmas" in mensaje["contenido_texto"]


def test_llamada_real_no_atendida_queda_fallida(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _modo_real(monkeypatch)
    _elevenlabs_falso(
        monkeypatch,
        [{"status": "done", "transcript": [], "metadata": {"call_duration_secs": 0, "phone_call": {"call_result": "no_answer"}}}],
        {},
    )
    llamada = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    fin = _esperar_llamada(client, llamada["id"])
    assert fin["estado"] == "fallida" and "no atendió" in fin["error"]
    assert not [m for m in client.get(f"/pedidos/{PEDIDO}/mensajes").json() if m["proveedor_id"] == "papelera_del_sur" and m["canal"] == "llamada"]


def test_llamada_real_sin_telefono_cargado_es_409(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _modo_real(monkeypatch, telefonos_proveedores={"ofisillas": "+59899333444"})
    r = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur")
    assert r.status_code == 409 and "No hay teléfono" in r.json()["error"]


def test_si_elevenlabs_rechaza_la_llamada_queda_fallida_con_el_motivo(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _modo_real(monkeypatch)

    async def disparar(numero, variables):
        raise RuntimeError("ElevenLabs respondió 422: to_number inválido")

    monkeypatch.setattr(llamadas, "_disparar", disparar)
    llamada = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    assert llamada["estado"] == "fallida" and "422" in llamada["error"]
    # respaldo en vivo: la misma llamada, simulada
    respaldo = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur?simulada=true").json()
    assert respaldo["modo"] == "simulada"
    assert _esperar_llamada(client, respaldo["id"])["estado"] == "terminada"


# ---------------------------------------------------------------- negociación por teléfono
def _negociacion_lista(client) -> Negociacion:
    """Plan de la demo + una negociación ensayada guardada (como la dejaría la Capa 5)."""
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 10
    while time.time() < limite and len(client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()) < 6:
        time.sleep(0.05)
    compu = next(c for c in client.get(f"/pedidos/{PEDIDO}/cotizaciones").json() if c["proveedor_id"] == "compuservice")
    client.post(f"/cotizaciones/{compu['id']}/confirmar", json={"incluye_iva": True})
    assert client.post(f"/pedidos/{PEDIDO}/optimizar").status_code == 200
    base = {"descripcion": "x", "riesgo": "bajo"}
    neg = Negociacion(
        id="neg_ofisillas_test",
        pedido_id=PEDIDO,
        proveedor_id="ofisillas",
        estrategias=[
            EstrategiaNegociacion(nombre="volumen", transcripcion=[
                {"rol": "abasto", "texto": "Vamos a equipar 10 puestos más."},
                {"rol": "proveedor", "texto": "Si confirmás, te la dejo a $ 10.355."},
            ], concesion_obtenida_pct=5.0, ganancia_esperada_uyu=Decimal("8175"), **base),
        ],
        elegida="volumen",
        mensaje_propuesto="Hola! Si equipamos 10 puestos más, ¿nos dejás la silla a $ 10.355?",
        estado="simulada",
    )
    store.guardar("negociaciones", neg)
    return neg


def test_aprobar_y_llamar_simulado(client):
    neg = _negociacion_lista(client)
    r = client.post(f"/negociaciones/{neg.id}/llamar", json={"mensaje": "Mensaje editado por Lucía"})
    assert r.status_code == 200, r.text
    llamada = r.json()
    assert llamada["tipo"] == "negociacion" and llamada["negociacion_id"] == neg.id
    guardada = client.get(f"/negociaciones/{neg.id}").json()
    assert guardada["estado"] == "aprobada" and guardada["llamada_id"] == llamada["id"]
    assert guardada["mensaje_propuesto"] == "Mensaje editado por Lucía"
    fin = _esperar_llamada(client, llamada["id"])
    assert fin["estado"] == "terminada"
    assert fin["resultado"]["acuerdo"] is True and fin["resultado"]["precio_acordado"] == 10355.0
    assert [t["rol"] for t in fin["transcripcion"]] == ["abasto", "abasto", "proveedor", "abasto"]
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "aprobado"


def test_aprobar_y_llamar_real_manda_estrategia_y_mensaje_aprobado(client, monkeypatch):
    neg = _negociacion_lista(client)
    _modo_real(monkeypatch)
    enviado: dict = {}
    _elevenlabs_falso(
        monkeypatch,
        [{
            "status": "done",
            "transcript": [{"role": "agent", "message": "Hola", "time_in_call_secs": 0}],
            "metadata": {"call_duration_secs": 95, "phone_call": {"call_result": "answered"}},
            "analysis": {
                "transcript_summary": "Ofisillas acepta 10.355 si se confirman los puestos.",
                "data_collection_results": {
                    "acuerdo": {"data_collection_id": "acuerdo", "rationale": "", "value": True},
                    "precio_acordado": {"data_collection_id": "precio_acordado", "rationale": "", "value": 10355},
                    "condicion": {"data_collection_id": "condicion", "rationale": "", "value": "equipar 10 puestos más"},
                },
            },
        }],
        enviado,
    )
    llamada = client.post(f"/negociaciones/{neg.id}/llamar", json={"mensaje": "Guion aprobado"}).json()
    assert enviado["numero"] == "+59899333444"
    v = enviado["variables"]
    assert v["tipo_llamada"] == "negociacion" and "volumen" in v["instrucciones"]
    assert "«Guion aprobado»" in v["instrucciones"] and "15 × Silla ergonómica" in v["instrucciones"]
    assert "no inventes competidores" in v["instrucciones"]
    fin = _esperar_llamada(client, llamada["id"])
    assert fin["resultado"] == {
        "resumen": "Ofisillas acepta 10.355 si se confirman los puestos.",
        "acuerdo": True,
        "precio_acordado": 10355.0,
        "condicion": "equipar 10 puestos más",
    }


def test_reset_cancela_llamadas_en_curso(client, monkeypatch):
    _cotizar_menos_papelera(client, monkeypatch)
    _ajustes(monkeypatch, sim_delay_seconds=4)
    llamada = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    client.post("/reset")
    time.sleep(0.5)
    assert client.get(f"/llamadas/{llamada['id']}").status_code == 404


def test_el_whatsapp_no_llega_encima_de_una_llamada_en_curso(client, monkeypatch):
    """Si el proveedor iba a contestar mientras Abasto lo llama, el simulador espera a que corte:
    la llamada trae la cotización y el mensaje del simulador no se duplica."""
    import asyncio
    from datetime import datetime

    from app import simulador
    from app.models import MensajeCrudo

    consultas = []

    def activa_falsa(pedido_id, proveedor_id):
        consultas.append(proveedor_id)
        if len(consultas) == 1:  # la llamada "termina" y deja su mensaje
            store.guardar("mensajes", MensajeCrudo(
                id="msg_llamada_test", pedido_id=pedido_id, proveedor_id=proveedor_id, canal="llamada",
                contenido_texto="Proveedor: resma a 290", recibido_en=datetime.now(), estado="pendiente",
            ))
            return object()
        return None

    monkeypatch.setattr(llamadas, "activa", activa_falsa)
    papelera = next(p for p in simulador._proveedores_sim() if p["publico"]["id"] == "papelera_del_sur")
    asyncio.run(simulador._responder(PEDIDO, papelera, 0))

    de_papelera = [m for m in store.valores("mensajes") if m["proveedor_id"] == "papelera_del_sur"]
    assert [m["canal"] for m in de_papelera] == ["llamada"]
    assert len(consultas) == 2
