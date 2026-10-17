"""Capa 5 con un LLM guionado: valida la lógica, los números y el paralelismo sin gastar API.

El gemelo guionado imita el perfil de Ofisillas (data/proveedores_sim.json): insensible a la
competencia, cede ~3 % por pago contado y hasta 6 % por compromiso de más puestos.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import config, llm, negociacion
from app.main import app
from app.models import ContextoNegociacion

PEDIDO = "pedido_demo_oct_2026"
PRECIO_SILLA = 10900.0
ENVIADOS: list[str] = []


def _estrategia(texto: str) -> str | None:
    m = re.search(r"\[(competencia|volumen|plazo)\]", texto)
    return m.group(1) if m else None


def _guion(precio_volumen: float = PRECIO_SILLA * 0.94, demora: float = 0.02, falla: str | None = None):
    """Devuelve un pedir_json falso que responde según el esquema pedido."""

    async def pedir_json(*, system, contenido, esquema, max_tokens=16000, effort="low"):
        user = contenido[0]["text"]
        ENVIADOS.extend([system, user])
        await asyncio.sleep(demora)
        if esquema is negociacion.TurnoAbasto:
            estrategia = re.search(r"Estrategia asignada para esta simulación: (\w+)", system).group(1)
            if estrategia == falla:
                raise llm.LLMError("El LLM no respondió en 60 s.")
            ronda = user.count("Abasto:") + 1
            return esquema(texto=f"[{estrategia}] propuesta ronda {ronda}")
        if esquema is negociacion.TurnoGemelo:
            estrategia = _estrategia(user)
            rondas = user.count("Abasto:")
            cierra = {"competencia": rondas >= 1, "volumen": rondas >= 2, "plazo": False}[estrategia]
            return esquema(texto=f"respuesta a {estrategia}", cierra_trato=cierra, molesto=False)
        if esquema is negociacion.Cierre:
            estrategia = _estrategia(user)
            precio = {"competencia": PRECIO_SILLA, "volumen": precio_volumen, "plazo": PRECIO_SILLA * 0.97}
            return esquema(
                acepta_negociar=estrategia != "competencia",
                precio_final_por_item=[{"producto_id": "silla", "precio": precio[estrategia]}],
                condicion="si confirman los puestos" if estrategia == "volumen" else None,
                animo="neutral",
            )
        if esquema is negociacion.Redaccion:
            return esquema(mensaje="Hola! Si equipamos 10 puestos más este trimestre, ¿nos dejás la silla a $ 10.246?")
        return esquema(texto="Explicación del plan.")  # explicacion.Explicacion

    return pedir_json


@pytest.fixture()
def contexto() -> ContextoNegociacion:
    """El contexto real que arma el backend para negociar con Ofisillas."""
    with TestClient(app) as c:
        c.post("/reset")
        c.post(f"/pedidos/{PEDIDO}/cotizar")
        _esperar(c)
        _confirmar_compuservice(c)
        c.post(f"/pedidos/{PEDIDO}/optimizar")
        r = c.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")  # sin key: 501 con el contexto
        assert r.status_code == 501
        c.post("/reset")
    return ContextoNegociacion.model_validate(r.json()["detalle"]["contexto"])


def _esperar(c: TestClient) -> None:
    limite = time.time() + 20
    while time.time() < limite:
        m = c.get(f"/pedidos/{PEDIDO}/mensajes").json()
        if len(m) == 6 and all(x["estado"] == "extraido" for x in m):
            return
        time.sleep(0.05)
    raise AssertionError("no llegaron las cotizaciones")


def _confirmar_compuservice(c: TestClient) -> None:
    cot = next(x for x in c.get(f"/pedidos/{PEDIDO}/cotizaciones").json() if x["proveedor_id"] == "compuservice")
    assert c.post(f"/cotizaciones/{cot['id']}/confirmar", json={"campo": "iva", "valor": True}).status_code == 200


def test_ensayar_elige_volumen_para_ofisillas(contexto, monkeypatch):
    ENVIADOS.clear()
    monkeypatch.setattr(llm, "pedir_json", _guion())
    resultado = asyncio.run(negociacion.ensayar(contexto))

    por_nombre = {e["nombre"]: e for e in resultado["estrategias"]}
    assert set(por_nombre) == {"competencia", "volumen", "plazo"}
    assert resultado["elegida"] == "volumen"
    assert por_nombre["volumen"]["concesion_obtenida_pct"] == pytest.approx(6.0, abs=0.01)
    assert por_nombre["plazo"]["concesion_obtenida_pct"] == pytest.approx(3.0, abs=0.01)
    assert por_nombre["competencia"]["concesion_obtenida_pct"] == 0.0
    # riesgo: cerró en ≤2 rondas → bajo; usó las 3 → medio
    assert por_nombre["volumen"]["riesgo"] == "bajo"
    assert por_nombre["plazo"]["riesgo"] == "medio"
    transcripcion = por_nombre["volumen"]["transcripcion"]
    assert [t["rol"] for t in transcripcion] == ["abasto", "proveedor", "abasto", "proveedor"]
    assert resultado["mensaje_propuesto"].startswith("Hola!")
    # Ningún prompt sale con variables sin reemplazar
    assert not [p for p in ENVIADOS if "{{" in p]
    # El gemelo recibe su perfil privado y Abasto la alternativa real con su condición
    assert any("hasta 8% por debajo" in p for p in ENVIADOS)
    assert any("Mueblería Rivera cotiza Silla ergonómica de oficina a $ 9.800" in p and "mínimo 20" in p for p in ENVIADOS)


def test_concesion_acotada_al_piso(contexto, monkeypatch):
    # El gemelo "se pasa" y ofrece 20 % menos: el código lo acota al piso de Ofisillas (8 %).
    monkeypatch.setattr(llm, "pedir_json", _guion(precio_volumen=PRECIO_SILLA * 0.80))
    resultado = asyncio.run(negociacion.ensayar(contexto))
    volumen = next(e for e in resultado["estrategias"] if e["nombre"] == "volumen")
    assert volumen["concesion_obtenida_pct"] == pytest.approx(8.0, abs=0.01)


def test_corridas_en_paralelo(contexto, monkeypatch):
    # 31 llamadas de 0,1 s: en serie serían ~3,1 s; en paralelo, la corrida más larga (7) + redacción.
    monkeypatch.setattr(llm, "pedir_json", _guion(demora=0.1))
    inicio = time.perf_counter()
    asyncio.run(negociacion.ensayar(contexto))
    assert time.perf_counter() - inicio < 1.5


def test_si_falla_una_estrategia_se_muestran_las_otras(contexto, monkeypatch):
    monkeypatch.setattr(llm, "pedir_json", _guion(falla="competencia"))
    resultado = asyncio.run(negociacion.ensayar(contexto))
    assert {e["nombre"] for e in resultado["estrategias"]} == {"volumen", "plazo"}


def test_si_fallan_todas_se_propaga_el_error(contexto, monkeypatch):
    async def siempre_falla(**_):
        raise llm.LLMError("Límite de uso de la API alcanzado; probá de nuevo en un minuto.")

    monkeypatch.setattr(llm, "pedir_json", siempre_falla)
    with pytest.raises(llm.LLMError):
        asyncio.run(negociacion.ensayar(contexto))


def test_endpoint_negociar_con_capa_5_real(monkeypatch):
    """De punta a punta por la API: confirmar con {campo, valor}, optimizar, negociar, aprobar."""
    monkeypatch.setattr(llm, "pedir_json", _guion())
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test"))
    with TestClient(app) as c:
        c.post("/reset")
        c.post(f"/pedidos/{PEDIDO}/cotizar")
        _esperar(c)
        _confirmar_compuservice(c)
        plan = c.post(f"/pedidos/{PEDIDO}/optimizar").json()
        assert plan["explicacion_origen"] == "llm" and plan["explicacion"] == "Explicación del plan."
        r = c.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
        assert r.status_code == 200, r.text
        neg = r.json()
        assert neg["elegida"] == "volumen"
        volumen = next(e for e in neg["estrategias"] if e["nombre"] == "volumen")
        assert volumen["ganancia_esperada_uyu"] == pytest.approx(9810.0, abs=0.01)  # 6 % de 163.500
        aprobada = c.post(f"/negociaciones/{neg['id']}/aprobar", json={"mensaje": neg["mensaje_propuesto"]})
        assert aprobada.json()["estado"] == "enviada_simulada"
        c.post("/reset")


def test_endpoint_negociar_error_del_llm_es_502(monkeypatch):
    async def siempre_falla(**_):
        raise llm.LLMError("No hay conexión con la API del LLM.")

    monkeypatch.setattr(llm, "pedir_json", siempre_falla)
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test"))
    with TestClient(app) as c:
        c.post("/reset")
        c.post(f"/pedidos/{PEDIDO}/cotizar")
        _esperar(c)
        _confirmar_compuservice(c)
        c.post(f"/pedidos/{PEDIDO}/optimizar")
        r = c.post(f"/pedidos/{PEDIDO}/negociar/ofisillas")
        assert r.status_code == 502 and "No hay conexión" in r.json()["error"]
        assert c.get(f"/pedidos/{PEDIDO}").json()["estado"] == "optimizado"
        c.post("/reset")


def test_confirmar_con_campo_desconocido_es_422():
    with TestClient(app) as c:
        c.post("/reset")
        c.post(f"/pedidos/{PEDIDO}/cotizar")
        _esperar(c)
        cot = c.get(f"/pedidos/{PEDIDO}/cotizaciones").json()[0]
        r = c.post(f"/cotizaciones/{cot['id']}/confirmar", json={"campo": "plazo", "valor": True})
        assert r.status_code == 422
        c.post("/reset")
