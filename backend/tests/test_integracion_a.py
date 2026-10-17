"""Las capas de A a través de los endpoints de C, con API key de prueba y LLM falso (sin red).

Recorre el guion: cotizar (6 extracciones con `extraer_crudo`), confirmar el IVA, optimizar (con
`explicar_plan`), negociar con Ofisillas (`ensayar`) y aprobar.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import config, explicacion, extraccion, negociacion, pipeline, store
from app.extraccion import ExtraccionLLM
from app.llm import LLMError
from app.main import app
from tests.test_negociacion import CIERRES_DEMO, LLMFalso

PEDIDO = "pedido_demo_oct_2026"
FIJAS = store.semilla("extracciones_fijas")["extracciones"]


def _cotizar_y_confirmar(client: TestClient) -> list[dict]:
    """Como en la demo: cotizar, esperar las 6 respuestas y confirmar el IVA de Compuservice."""
    assert client.post(f"/pedidos/{PEDIDO}/cotizar").json()["estado"] == "cotizando"
    limite = time.time() + 30
    while time.time() < limite:
        mensajes = client.get(f"/pedidos/{PEDIDO}/mensajes").json()
        if len(mensajes) == 6 and all(
            m["estado"] in ("extraido", "error") for m in mensajes
        ):
            break
        time.sleep(0.1)
    assert all(m["estado"] == "extraido" for m in mensajes), mensajes
    cots = client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()
    compu = next(c for c in cots if c["proveedor_id"] == "compuservice")
    r = client.post(
        f"/cotizaciones/{compu['id']}/confirmar", json={"incluye_iva": True}
    )
    assert r.status_code == 200, r.text
    return client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()


class ExtractorFalso:
    """Devuelve la extracción de referencia del proveedor que nombra el prompt."""

    def __init__(self):
        self.canales: dict[str, list[str]] = {}

    async def pedir_json(self, *, contenido, esquema, **_):
        assert esquema is ExtraccionLLM
        texto = contenido[-1]["text"]
        nombre = re.search(r"Proveedor: (.+) \(", texto).group(1)
        pid = next(p.id for p in pipeline.proveedores().values() if p.nombre == nombre)
        self.canales[pid] = [b["type"] for b in contenido]
        return ExtraccionLLM.model_validate(FIJAS[pid])


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(
        config,
        "settings",
        dataclasses.replace(config.settings, anthropic_api_key="test"),
    )
    with TestClient(app) as c:
        c.post(
            "/reset", params={"hard": True}
        )  # sin extracciones cacheadas de otra corrida
        yield c
        c.post("/reset", params={"hard": True})


def test_guion_completo_con_las_capas_de_a(client, monkeypatch):
    extractor = ExtractorFalso()
    monkeypatch.setattr(extraccion, "pedir_json", extractor.pedir_json)

    async def explicar(*, system, mensajes, **_):
        datos = mensajes[0]["content"]
        assert "Distribuidora Oriental" in datos
        return "Comprando a 3 proveedores el pedido cuesta 498.454 y se ahorran $ 43.666 (8,05 %)."

    monkeypatch.setattr(explicacion, "pedir_texto", explicar)
    gemelo = LLMFalso(CIERRES_DEMO)
    monkeypatch.setattr(negociacion, "pedir_texto", gemelo.pedir_texto)
    monkeypatch.setattr(negociacion, "pedir_json", gemelo.pedir_json)

    assert client.get("/health").json()["extraccion"] == "llm"
    cotizaciones = _cotizar_y_confirmar(client)

    assert len(cotizaciones) == 6
    assert extractor.canales["tecnoimport"] == [
        "text"
    ]  # PDF con texto: pdfplumber de C
    assert extractor.canales["muebleria_rivera"] == ["image", "text"]  # foto: visión
    origenes = {r["origen"] for r in store.valores("extracciones")}
    assert origenes == {"llm"}

    plan = client.post(f"/pedidos/{PEDIDO}/optimizar").json()
    assert plan["explicacion_origen"] == "llm"
    assert plan["explicacion"].startswith("Comprando a 3 proveedores")
    assert plan["oportunidad_negociacion"] == "ofisillas"

    r = client.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
    assert r.status_code == 200, r.text
    neg = r.json()
    assert neg["elegida"] == "volumen"
    volumen = next(e for e in neg["estrategias"] if e["nombre"] == "volumen")
    assert volumen["ganancia_esperada_uyu"] == 8175.0
    assert neg["mensaje_propuesto"].startswith("Hola!")

    aprobada = client.post(f"/negociaciones/{neg['id']}/aprobar", json={}).json()
    assert aprobada["estado"] == "enviada_simulada"


def _hasta_el_plan(client, monkeypatch) -> None:
    monkeypatch.setattr(extraccion, "pedir_json", ExtractorFalso().pedir_json)

    async def explicar(**_):
        raise LLMError("sin explicación")  # C usa la plantilla

    monkeypatch.setattr(explicacion, "pedir_texto", explicar)
    _cotizar_y_confirmar(client)
    plan = client.post(f"/pedidos/{PEDIDO}/optimizar").json()
    assert plan["oportunidad_negociacion"] == "ofisillas"


def test_si_el_llm_falla_al_negociar_c_responde_501_con_el_motivo(client, monkeypatch):
    _hasta_el_plan(client, monkeypatch)

    async def sin_cupo(**_):
        raise LLMError(
            "Límite de uso de la API alcanzado; probá de nuevo en un minuto."
        )

    monkeypatch.setattr(negociacion, "pedir_texto", sin_cupo)
    monkeypatch.setattr(negociacion, "pedir_json", sin_cupo)
    r = client.post(
        f"/pedidos/{PEDIDO}/negociar/ofisillas",
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 501, r.text
    assert r.json()["error"].startswith("Límite de uso de la API")
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "optimizado"


def test_si_se_vence_el_plazo_de_a_c_responde_504(client, monkeypatch):
    _hasta_el_plan(client, monkeypatch)
    gemelo = LLMFalso(CIERRES_DEMO)

    async def redactar_colgado(*, system, mensajes, **kw):
        if system.startswith("Redactá"):
            await asyncio.sleep(10)
        return await gemelo.pedir_texto(system=system, mensajes=mensajes, **kw)

    monkeypatch.setattr(negociacion, "pedir_texto", redactar_colgado)
    monkeypatch.setattr(negociacion, "pedir_json", gemelo.pedir_json)
    monkeypatch.setattr(negociacion, "PLAZO_TOTAL_SEGUNDOS", 0.5)
    r = client.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
    assert r.status_code == 504, r.text
    assert client.get(f"/pedidos/{PEDIDO}").json()["estado"] == "optimizado"


def test_si_la_explicacion_inventa_un_numero_c_usa_la_plantilla(client, monkeypatch):
    monkeypatch.setattr(extraccion, "pedir_json", ExtractorFalso().pedir_json)

    async def explicar(**_):
        return "Se ahorran $ 99.999 comprando a 3 proveedores."

    monkeypatch.setattr(explicacion, "pedir_texto", explicar)
    _cotizar_y_confirmar(client)
    plan = client.post(f"/pedidos/{PEDIDO}/optimizar").json()
    assert plan["explicacion_origen"] == "plantilla"
    assert "99.999" not in plan["explicacion"]
