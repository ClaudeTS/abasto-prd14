"""Explicación del plan con un LLM falso: prompt con los datos de C y ningún número inventado."""

import asyncio

import pytest

from app import explicacion, optimizacion, pipeline
from app.explicacion import explicar_plan, numeros_inventados
from app.llm import LLMError
from scripts.demo import cotizaciones_fijas, pedido, plan_demo


@pytest.fixture(scope="module")
def datos():
    plan = plan_demo(cotizaciones_fijas())
    return optimizacion.datos_para_explicar(
        plan,
        pipeline.proveedores(),
        {p.id: p.nombre for p in pipeline.catalogo()},
        habitual_id=pedido().proveedor_habitual_id,
    )


def instalar(monkeypatch, respuesta):
    pedidos = []

    async def pedir_texto(*, system, mensajes, **_):
        pedidos.append({"system": system, "mensajes": mensajes})
        return respuesta

    monkeypatch.setattr(explicacion, "pedir_texto", pedir_texto)
    return pedidos


def test_el_prompt_lleva_los_datos_de_c(monkeypatch, datos):
    texto = (
        f"Comprando a 3 proveedores el pedido cuesta $ {datos['costo_total']}, "
        f"{datos['ahorro']} menos que todo a {datos['habitual']} ({datos['ahorro_pct']} %)."
    )
    pedidos = instalar(monkeypatch, texto)
    assert asyncio.run(explicar_plan(datos)) == texto

    [mensaje] = pedidos[0]["mensajes"]
    assert mensaje["role"] == "user"
    for clave in (
        "asignaciones",
        "costo_total",
        "baseline",
        "ahorro_pct_comparable",
        "no_mas_barato",
    ):
        assert datos[clave] in mensaje["content"], clave
    assert "{{" not in mensaje["content"] and "{{" not in pedidos[0]["system"]
    assert "NO cambies ningún número" in pedidos[0]["system"]


def test_un_numero_que_no_esta_en_el_plan_es_error(monkeypatch, datos):
    instalar(monkeypatch, "Se ahorran $ 51.234 comprando a 3 proveedores.")
    with pytest.raises(LLMError, match="51.234"):
        asyncio.run(explicar_plan(datos))


def test_numeros_inventados():
    datos = {
        "costo_total": "498.454",
        "ahorro_pct": "8,05",
        "asignaciones": "- Sillas: 15 a Ofisillas",
    }
    assert (
        numeros_inventados(
            "Cuesta 498.454, un 8,05 % menos (8,1 % redondeado; 8 %).", datos
        )
        == []
    )
    assert numeros_inventados("15 sillas a 3 proveedores", datos) == []
    assert numeros_inventados("Cuesta 498.455 y ahorra 8,06 %", datos) == [
        "498.455",
        "8,06",
    ]
    assert numeros_inventados("Se compran 150 resmas", datos) == ["150"]


def test_porcentajes_y_decimales_con_punto():
    datos = {"costo_total": "1.234.567,89", "ahorro_pct": "8,05"}
    assert numeros_inventados("Cuesta 1.234.567,89 y ahorra 8.05%.", datos) == []
    assert numeros_inventados("Ahorra 8 por ciento.", datos) == []  # 8,05 redondeado
    assert numeros_inventados("Ahorra 12.75% sobre 1.234.568", datos) == ["12.75"]
    assert numeros_inventados("Ahorra un 7 % con 3 proveedores", datos) == ["7"]


def test_un_porcentaje_solo_vale_si_es_un_porcentaje_de_los_datos(datos):
    # Con los datos de la demo: 15 sillas, 10 notebooks, 20 de mínimo, "HP 85A", ahorro 8,05 %.
    assert numeros_inventados("Se ahorra un 8 %, o un 16 % comparable.", datos) == []
    assert numeros_inventados("Se ahorra un 15 % con 3 proveedores.", datos) == ["15"]
    assert numeros_inventados("Ahorra el 20 por ciento.", datos) == ["20"]


def test_un_monto_chico_no_pasa_por_conteo(datos):
    assert numeros_inventados("El envío sale $ 50 y el tóner USD 80.", datos) == [
        "50",
        "80",
    ]
    assert numeros_inventados("Cuesta U$S 95 o 90 dólares.", datos) == ["95", "90"]
    assert numeros_inventados("Se compran 15 sillas a 3 proveedores.", datos) == []
    # Otras formas de escribir la moneda.
    assert numeros_inventados("Sale usd 80, u$s 70, U$D 65 o $U 50.", datos) == [
        "80",
        "70",
        "65",
        "50",
    ]


def test_los_miles_escritos_con_palabras_son_montos(datos):
    # Ahorro $ 43.666 y total 498.454: "44 mil" y "498 mil" son esos montos redondeados.
    assert numeros_inventados("Se ahorran casi 44 mil pesos.", datos) == []
    assert numeros_inventados("Unos 43,7 mil de ahorro sobre 498 mil.", datos) == []
    assert numeros_inventados("Se ahorran 30 mil pesos.", datos) == ["30"]
    assert numeros_inventados("Se ahorran 16 mil.", datos) == ["16"]
    assert numeros_inventados("Cuesta medio millón: 2 millones menos.", datos) == ["2"]


def test_el_tipo_de_cambio_se_puede_escribir_completo(datos):
    assert numeros_inventados("Al cambio de 1 USD = $ 40,00.", datos) == []
