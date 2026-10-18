"""Secuencia de contacto de RF-06 (PRD 1.4 §11.1): llamada → reintento → WhatsApp → email.

Simulada con `?simular_no_atiende=true` y real con ElevenLabs reemplazado en la frontera HTTP.
Cada contacto enviado queda en la colección compartida `contactos` con el esquema que lee el bloque 1.
"""

from __future__ import annotations

import dataclasses
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app import config, llamadas, simulador, store
from app.main import app
from app.models import MensajeCrudo

PEDIDO = "pedido_demo_oct_2026"
CLAVES_CONTACTO = {"id", "pedido_id", "proveedor_id", "canal", "sentido", "texto", "enviado_en", "motivo"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(llamadas, "INTERVALO_CONSULTA_S", 0.01)
    monkeypatch.setenv("LLAMADA_REINTENTO_MINUTOS", "5")
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _ajustes(monkeypatch, **cambios):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, **cambios))


def _esperar_secuencia(llamada_id, estados, timeout=10):
    limite = time.time() + timeout
    sec = None
    while time.time() < limite:
        sec = llamadas.secuencia_de(llamada_id)
        if sec is not None and sec.estado in estados:
            return sec
        time.sleep(0.05)
    raise AssertionError(f"La secuencia no llegó a {estados}: {sec}")


def _contactos(proveedor_id):
    return sorted(
        (c for c in store.valores("contactos") if c["proveedor_id"] == proveedor_id), key=lambda c: c["enviado_en"]
    )


def _sin_simulador(client, monkeypatch):
    """Cotiza y corta el simulador cuando respondieron todos menos la papelera: nunca contesta."""
    _ajustes(monkeypatch, sim_delay_seconds=0.4)
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 10
    while time.time() < limite:
        if len({m["proveedor_id"] for m in client.get(f"/pedidos/{PEDIDO}/mensajes").json()}) == 5:
            break
        time.sleep(0.05)
    simulador.cancelar_todo()


# ---------------------------------------------------------------- presentación (RF-06)
def test_el_agente_se_presenta_como_ia_y_avisa_que_graba():
    from app import pedidos

    pedido = pedidos.obtener(PEDIDO)
    v = llamadas.instrucciones_cotizacion(pedido, "papelera_del_sur")
    assert v["primer_mensaje"].startswith("Hola, ¿hablo con Papelera del Sur? Soy el asistente de inteligencia artificial de Tecnova S.A.")
    assert "esta llamada se graba" in v["primer_mensaje"]
    assert "inteligencia artificial" in v["instrucciones"] and "no tiene duración máxima" in v["instrucciones"]


# ---------------------------------------------------------------- secuencia simulada
def test_no_atiende_dos_veces_y_se_avisa_por_whatsapp(client, monkeypatch):
    _sin_simulador(client, monkeypatch)
    r = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur?simular_no_atiende=true")
    assert r.status_code == 200, r.text
    primera = r.json()
    assert primera["modo"] == "simulada"
    # mientras suena, GET /llamadas/{id} trae la forma de siempre más la secuencia
    detalle = client.get(f"/llamadas/{primera['id']}").json()
    assert {"id", "estado", "transcripcion", "resultado", "iniciada_en"} <= set(detalle)
    assert detalle["intento"] == 1 and detalle["secuencia"]["estado"] == "en_curso"
    assert detalle["secuencia"]["tiene_whatsapp"] is True

    programada = _esperar_secuencia(primera["id"], ("reintento_programado",))
    assert programada.reintento_en is not None and programada.reintento_minutos == 5
    assert [p.estado for p in programada.pasos] == ["no_atendida", "programado", "pendiente", "pendiente"]
    detalle = client.get(f"/llamadas/{primera['id']}").json()
    assert detalle["estado"] == "fallida" and detalle["atendida"] is False and "no atendió" in detalle["error"]

    sec = _esperar_secuencia(primera["id"], ("aviso_enviado",))
    assert [p.estado for p in sec.pasos] == ["no_atendida", "no_atendida", "enviado", "omitido"]
    assert len(sec.llamada_ids) == 2
    segunda = client.get(f"/llamadas/{sec.llamada_ids[1]}").json()
    assert segunda["intento"] == 2 and segunda["atendida"] is False

    contactos = _contactos("papelera_del_sur")
    assert [(c["canal"], c["motivo"]) for c in contactos] == [
        ("llamada", "solicitud_cotizacion"),
        ("llamada", "reintento"),
        ("whatsapp", "aviso_no_atendio"),
    ]
    for c in contactos:
        assert set(c) == CLAVES_CONTACTO and c["sentido"] == "enviado" and c["pedido_id"] == PEDIDO
        assert datetime.fromisoformat(c["enviado_en"]).tzinfo is None
    whatsapp = contactos[-1]["texto"]
    assert "inteligencia artificial" in whatsapp and "Resma papel A4" in whatsapp and "Notebook" not in whatsapp
    assert sec.pasos[2].contacto_id == contactos[-1]["id"]


def test_sin_whatsapp_se_manda_email_con_la_solicitud(client):
    r = client.post(f"/pedidos/{PEDIDO}/llamar/tecnoimport?simular_no_atiende=true")
    sec = _esperar_secuencia(r.json()["id"], ("aviso_enviado",))
    assert sec.tiene_whatsapp is False
    assert [p.estado for p in sec.pasos] == ["no_atendida", "no_atendida", "omitido", "enviado"]
    email = _contactos("tecnoimport")[-1]
    assert email["canal"] == "email" and email["motivo"] == "aviso_no_atendio"
    assert "Asunto: Solicitud de cotización — Tecnova S.A." in email["texto"]
    assert "Notebook" in email["texto"] and "Tóner" in email["texto"]
    assert "cotizaciones@tecnoimport.example" in email["texto"]


def test_si_responde_antes_del_reintento_no_se_vuelve_a_llamar(client, monkeypatch):
    _sin_simulador(client, monkeypatch)
    monkeypatch.setenv("LLAMADA_REINTENTO_MINUTOS", "30")  # 3 s con sim_delay 0,4
    primera = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur?simular_no_atiende=true").json()
    _esperar_secuencia(primera["id"], ("reintento_programado",))
    store.guardar("mensajes", MensajeCrudo(
        id="msg_papelera_whatsapp", pedido_id=PEDIDO, proveedor_id="papelera_del_sur", canal="whatsapp_audio",
        contenido_texto="te paso los precios", recibido_en=datetime.now(), estado="extraido",
    ))
    sec = _esperar_secuencia(primera["id"], ("respondio",))
    assert [p.estado for p in sec.pasos] == ["no_atendida", "omitido", "omitido", "omitido"]
    assert len(sec.llamada_ids) == 1
    assert [c["motivo"] for c in _contactos("papelera_del_sur")] == ["solicitud_cotizacion"]


def test_llamada_atendida_cierra_la_secuencia(client, monkeypatch):
    _sin_simulador(client, monkeypatch)
    _ajustes(monkeypatch, sim_delay_seconds=0)
    primera = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    sec = _esperar_secuencia(primera["id"], ("atendida",))
    assert [p.estado for p in sec.pasos] == ["atendida", "omitido", "omitido", "omitido"]
    assert client.get(f"/llamadas/{primera['id']}").json()["atendida"] is True


def test_reset_cancela_el_reintento_programado(client, monkeypatch):
    _sin_simulador(client, monkeypatch)
    monkeypatch.setenv("LLAMADA_REINTENTO_MINUTOS", "20")  # 2 s
    primera = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur?simular_no_atiende=true").json()
    _esperar_secuencia(primera["id"], ("reintento_programado",))
    assert llamadas._reintentos
    client.post("/reset")
    assert not llamadas._reintentos
    time.sleep(2.5)
    assert store.valores("llamadas") == [] and store.valores("contactos") == []


def test_llamar_a_mano_con_el_reintento_programado_lo_adelanta(client, monkeypatch):
    _sin_simulador(client, monkeypatch)
    monkeypatch.setenv("LLAMADA_REINTENTO_MINUTOS", "60")  # 6 s: no llega a dispararse solo
    primera = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur?simular_no_atiende=true").json()
    _esperar_secuencia(primera["id"], ("reintento_programado",))
    _ajustes(monkeypatch, sim_delay_seconds=0)
    segunda = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    sec = _esperar_secuencia(primera["id"], ("atendida",))
    assert sec.llamada_ids == [primera["id"], segunda["id"]]
    assert [p.estado for p in sec.pasos] == ["no_atendida", "atendida", "omitido", "omitido"]
    assert not llamadas._reintentos
    assert [c["motivo"] for c in _contactos("papelera_del_sur")] == ["solicitud_cotizacion", "reintento"]


# ---------------------------------------------------------------- secuencia real (ElevenLabs falso)
def test_real_no_atiende_y_el_reintento_atiende(client, monkeypatch):
    _sin_simulador(client, monkeypatch)
    monkeypatch.setenv("LLAMADA_REINTENTO_MINUTOS", "0")
    _ajustes(
        monkeypatch,
        llamadas_modo="real", elevenlabs_api_key="xi", elevenlabs_agent_id="ag", elevenlabs_phone_number_id="ph",
        telefonos_proveedores={"papelera_del_sur": "+59899111222"},
    )
    disparos = []

    async def disparar(numero, variables):
        disparos.append(variables["primer_mensaje"])
        return {"success": True, "conversation_id": f"conv_{len(disparos)}", "callSid": "CA1"}

    async def consultar(conversation_id):
        if conversation_id == "conv_1":
            return {"status": "done", "transcript": [], "metadata": {"phone_call": {"call_result": "busy"}}}
        return {
            "status": "done",
            "transcript": [{"role": "agent", "message": "Hola", "time_in_call_secs": 0}],
            "metadata": {"call_duration_secs": 30, "phone_call": {"call_result": "answered"}},
            "analysis": {"transcript_summary": "Pasó precios."},
        }

    monkeypatch.setattr(llamadas, "_disparar", disparar)
    monkeypatch.setattr(llamadas, "_consultar", consultar)
    primera = client.post(f"/pedidos/{PEDIDO}/llamar/papelera_del_sur").json()
    sec = _esperar_secuencia(primera["id"], ("atendida",))
    assert len(disparos) == 2 and all("se graba" in m for m in disparos)
    assert [p.estado for p in sec.pasos] == ["no_atendida", "atendida", "omitido", "omitido"]
    uno = client.get(f"/llamadas/{primera['id']}").json()
    assert "ocupado" in uno["error"] and uno["atendida"] is False
    assert uno["audio_disponible_hasta"] is not None  # real: el audio vence a los 60 días
    assert [c["motivo"] for c in _contactos("papelera_del_sur")] == ["solicitud_cotizacion", "reintento"]


def test_la_llamada_de_negociacion_queda_como_contacto(client):
    from tests.test_llamadas import _negociacion_lista

    neg = _negociacion_lista(client)
    llamada = client.post(f"/negociaciones/{neg.id}/llamar").json()
    contactos = _contactos("ofisillas")
    assert [(c["canal"], c["motivo"]) for c in contactos] == [("llamada", "negociacion")]
    assert "inteligencia artificial" in contactos[0]["texto"]
    assert client.get(f"/llamadas/{llamada['id']}").json()["secuencia"] is None
