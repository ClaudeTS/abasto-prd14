"""Cache de la extracción (pipeline.py): la transcripción de una llamada no se mezcla con la respuesta
por WhatsApp del mismo proveedor, que comparte la clave del cache."""

import asyncio
import dataclasses
from datetime import datetime

import pytest

from app import config, pipeline, store
from app.models import MensajeCrudo

PEDIDO = "pedido_demo_oct_2026"


@pytest.fixture()
def extractor(monkeypatch):
    """Extracción con LLM (con un extractor falso que devuelve lo que leyó) y sin cache previo."""
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, anthropic_api_key="test"))
    leidos: list[str] = []

    async def extraer(*, texto, **_):
        leidos.append(texto)
        return {"leido": texto}

    monkeypatch.setattr(pipeline, "_extractor_llm", lambda: extraer)
    store.reset(borrar_cache=True)
    yield leidos
    store.reset(borrar_cache=True)


def _extraer(canal: str, texto: str) -> tuple[dict, str]:
    mensaje = MensajeCrudo(
        id=f"msg_papelera_del_sur_{canal}",
        pedido_id=PEDIDO,
        proveedor_id="papelera_del_sur",
        canal=canal,
        contenido_texto=texto,
        recibido_en=datetime.now(),
        estado="pendiente",
    )
    return asyncio.run(pipeline.extraer_crudo(mensaje))


def test_la_llamada_no_lee_ni_pisa_la_extraccion_cacheada_del_audio(extractor):
    assert _extraer("whatsapp_audio", "la caja te la dejo a mil noventa") == (
        {"leido": "la caja te la dejo a mil noventa"},
        "llm",
    )
    # Por teléfono dijo otro precio: se lee la transcripción, no el audio cacheado
    assert _extraer("llamada", "Papelera del Sur: la caja, mil cincuenta") == (
        {"leido": "Papelera del Sur: la caja, mil cincuenta"},
        "llm",
    )
    assert store.cache_leer(f"extraccion_{PEDIDO}_papelera_del_sur") == {"leido": "la caja te la dejo a mil noventa"}
    # El audio sigue saliendo del cache
    assert _extraer("whatsapp_audio", "la caja te la dejo a mil noventa")[1] == "cache"
    assert len(extractor) == 2
