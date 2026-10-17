"""llm.py contra una API simulada (transporte HTTP falso): forma del pedido, reintento y errores."""

import asyncio
import dataclasses
import json
import os

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from app import config, llm

MENSAJES = [{"role": "user", "content": "hola"}]


class Oferta(BaseModel):
    precio: float


def instalar(monkeypatch, responder) -> list[dict]:
    pedidos = []

    def handler(request):
        pedidos.append(
            {
                "url": str(request.url),
                "beta": request.headers.get("anthropic-beta", ""),
                "body": json.loads(request.content),
            }
        )
        return responder(request)

    cliente = anthropic.AsyncAnthropic(
        api_key="test",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )
    monkeypatch.setattr(llm, "_cliente", cliente)
    return pedidos


def respuesta(*bloques, stop="end_turn"):
    return lambda _: httpx2.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": llm.MODEL,
            "content": list(bloques),
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
        headers={"request-id": "req_test"},
    )


def error(status, tipo):
    return lambda _: httpx2.Response(
        status, json={"type": "error", "error": {"type": tipo, "message": "x"}}
    )


def texto(t):
    return {"type": "text", "text": t}


def test_pedir_texto_sin_temperature_y_sin_pensamiento(monkeypatch):
    pensamiento = {"type": "thinking", "thinking": "", "signature": "x"}
    pedidos = instalar(
        monkeypatch, respuesta(pensamiento, texto(" Dale, te hago 3 %. "))
    )
    resultado = asyncio.run(llm.pedir_texto(system="s", mensajes=MENSAJES))

    assert resultado == "Dale, te hago 3 %."
    body = pedidos[0]["body"]
    assert "/v1/messages" in pedidos[0]["url"]
    assert llm.FALLBACK_BETA in pedidos[0]["beta"]
    assert body["model"] == llm.MODEL
    assert body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "low"}
    assert "temperature" not in body
    assert body["messages"] == MENSAJES


def test_pedir_json_pone_el_historial_antes_del_mensaje(monkeypatch):
    pedidos = instalar(monkeypatch, respuesta(texto('{"precio": 10355}')))
    historial = [
        {"role": "user", "content": "¿5 %?"},
        {"role": "assistant", "content": "Te hago 5."},
    ]
    oferta = asyncio.run(
        llm.pedir_json(
            system="s", historial=historial, contenido=[texto("cierre")], esquema=Oferta
        )
    )

    assert oferta.precio == 10355
    body = pedidos[0]["body"]
    assert body["messages"] == historial + [
        {"role": "user", "content": [texto("cierre")]}
    ]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"


def test_json_invalido_reintenta_una_vez_y_avisa(monkeypatch):
    pedidos = instalar(monkeypatch, respuesta(texto('{"precio": "mucho"}')))
    with pytest.raises(llm.LLMError, match="después de reintentar"):
        asyncio.run(llm.pedir_json(system="s", contenido=[texto("x")], esquema=Oferta))
    assert len(pedidos) == 2
    reintento = pedidos[1]["body"]["messages"][-1]["content"][-1]["text"]
    assert reintento.startswith("Respondé solo con JSON")


@pytest.mark.parametrize(
    "responder, mensaje",
    [
        (respuesta(texto("No puedo ayudar con eso."), stop="refusal"), "refusal"),
        (respuesta(texto('{"precio": 103'), stop="max_tokens"), "max_tokens"),
    ],
)
def test_pedir_json_informa_refusal_y_max_tokens_sin_reintentar(
    monkeypatch, responder, mensaje
):
    pedidos = instalar(monkeypatch, responder)
    with pytest.raises(llm.LLMError, match=mensaje):
        asyncio.run(llm.pedir_json(system="s", contenido=[texto("x")], esquema=Oferta))
    assert len(pedidos) == 1


def test_el_cliente_reintenta_una_vez_y_conecta_en_5_s(monkeypatch):
    monkeypatch.setattr(
        config,
        "settings",
        dataclasses.replace(config.settings, anthropic_api_key="test"),
    )
    monkeypatch.setattr(llm, "_cliente", None)
    c = llm.cliente()
    assert c.max_retries == llm.MAX_REINTENTOS == 1
    assert c.timeout.read == llm.TIMEOUT_SEGUNDOS and c.timeout.connect == 5.0


def test_el_tope_de_tiempo_incluye_los_reintentos(monkeypatch):
    async def lento(request):
        await asyncio.sleep(5)

    instalar(monkeypatch, lento)
    monkeypatch.setattr(llm, "TIMEOUT_SEGUNDOS", 0.2)
    with pytest.raises(llm.LLMError, match="no respondió"):
        asyncio.run(llm.pedir_texto(system="s", mensajes=MENSAJES))


@pytest.mark.parametrize(
    "responder, mensaje",
    [
        (respuesta(texto("  ")), "vacía"),
        (respuesta(texto(""), stop="refusal"), "refusal"),
        (respuesta(texto("Hola"), stop="max_tokens"), "max_tokens"),
        (error(429, "rate_limit_error"), "Límite de uso"),
        (error(401, "authentication_error"), "API key de Anthropic inválida"),
        (error(400, "invalid_request_error"), "Pedido inválido"),
        (error(529, "overloaded_error"), "respondió 529"),
    ],
)
def test_errores_legibles(monkeypatch, responder, mensaje):
    instalar(monkeypatch, responder)
    with pytest.raises(llm.LLMError, match=mensaje):
        asyncio.run(llm.pedir_texto(system="s", mensajes=MENSAJES))


def test_completar_del_simulador_ignora_temperature_y_sube_max_tokens(monkeypatch):
    """Contrato con C: llm.completar(system, user, temperature=0.7, max_tokens=900)."""
    pedidos = instalar(monkeypatch, respuesta(texto("Buenas! Te paso precios.")))
    resultado = asyncio.run(
        llm.completar("sos un proveedor", "cotizá", temperature=0.7, max_tokens=900)
    )

    assert resultado == "Buenas! Te paso precios."
    body = pedidos[0]["body"]
    assert "temperature" not in body
    assert body["max_tokens"] == llm.MAX_TOKENS
    assert body["system"] == "sos un proveedor"
    assert body["messages"] == [{"role": "user", "content": "cotizá"}]


def test_sin_api_key_el_error_dice_como_configurarla(monkeypatch, tmp_path):
    # Sin key, el SDK busca credenciales en variables ANTHROPIC_* y en el perfil del usuario.
    for variable in [v for v in os.environ if v.startswith("ANTHROPIC_")]:
        monkeypatch.delenv(variable)
    for variable in ("APPDATA", "USERPROFILE", "HOME"):
        monkeypatch.setenv(variable, str(tmp_path))

    def sin_red(request):
        raise AssertionError("no debería salir ningún pedido")

    cliente = anthropic.AsyncAnthropic(
        api_key=None,
        http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(sin_red)
        ),
    )
    monkeypatch.setattr(llm, "_cliente", cliente)
    with pytest.raises(llm.LLMError, match="Falta ANTHROPIC_API_KEY"):
        asyncio.run(llm.pedir_texto(system="s", mensajes=MENSAJES))


def test_credenciales_ilegibles_dan_un_error_legible(monkeypatch):
    def sin_credenciales():
        raise anthropic.CredentialsError("Config file not found")

    monkeypatch.setattr(llm, "cliente", sin_credenciales)
    with pytest.raises(llm.LLMError, match="credenciales de Anthropic"):
        asyncio.run(llm.pedir_texto(system="s", mensajes=MENSAJES))
