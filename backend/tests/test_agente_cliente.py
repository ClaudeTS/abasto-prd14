"""PRD 1.4 RF-05: la corrida del agente guarda y devuelve su cliente interno (Ventas o Personal)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import agente, store
from app.agente import CorridaAgente
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(agente, "INTERVALO_S", 0.05)
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _iniciar(client: TestClient, **body) -> dict:
    texto = client.get("/agente/ejemplo").json()["texto"]
    r = client.post("/agente", json={"texto": texto, "llamar_si_no_responde": False, **body})
    assert r.status_code == 201, r.text
    return r.json()


def test_por_defecto_es_personal(client):
    corrida = _iniciar(client)
    assert corrida["cliente_interno"] == "personal"
    assert client.get(f"/agente/{corrida['id']}").json()["cliente_interno"] == "personal"
    assert "cliente_interno" not in corrida["opciones"]
    client.post(f"/agente/{corrida['id']}/cancelar")


def test_guarda_ventas_y_lo_devuelve_en_actual(client):
    corrida = _iniciar(client, cliente_interno="ventas")
    assert corrida["cliente_interno"] == "ventas"
    assert client.get(f"/agente/{corrida['id']}").json()["cliente_interno"] == "ventas"
    assert client.get("/agente/actual").json()["cliente_interno"] == "ventas"
    guardada = store.obtener("agentes", corrida["id"], CorridaAgente)
    assert guardada is not None and guardada.cliente_interno == "ventas"
    client.post(f"/agente/{corrida['id']}/cancelar")


def test_cliente_invalido_da_422(client):
    r = client.post("/agente", json={"texto": "x", "cliente_interno": "marketing"})
    assert r.status_code == 422
    assert client.get("/agente/actual").status_code == 404


def test_corrida_vieja_sin_cliente_vale_personal():
    vieja = {
        "id": "ag_vieja",
        "pedido_id": "pedido_demo_oct_2026",
        "texto": None,
        "horizonte_meses": 1,
        "opciones": {},
        "estado": "cancelada",
        "pasos": [],
        "creada_en": "2026-10-20T10:00:00",
        "actualizada_en": "2026-10-20T10:00:00",
    }
    assert CorridaAgente.model_validate(vieja).cliente_interno == "personal"
