"""Negociación ensayada con un LLM falso: cuentas, piso, riesgo, elección y armado de los turnos.

El contexto es el mismo que arma C para POST /negociar (`scripts.demo.contexto_demo`).
"""

import asyncio
import dataclasses
import re
from decimal import Decimal

import pytest

from app import config, integracion_a, negociacion
from app.integracion_a import CapaNoDisponible
from app.llm import LLMError
from app.models import EstrategiaNegociacion
from app.negociacion import (
    CierreGemelo,
    PrecioFinal,
    compromiso_volumen,
    ensayar,
    items_negociados,
    texto_alternativas,
)
from scripts.demo import contexto_demo


def cierre(
    precio=None, *, acepta=True, animo="cordial", condicion=None, producto="silla"
):
    precios = (
        [] if precio is None else [PrecioFinal(producto_id=producto, precio=precio)]
    )
    return CierreGemelo(
        acepta_negociar=acepta,
        precios_finales=precios,
        condicion=condicion,
        animo=animo,
    )


# Lo que se espera en la demo con Ofisillas: competencia no funciona, plazo 3 %, volumen 5 %.
CIERRES_DEMO = {
    "competencia": cierre(10900, acepta=False, animo="neutral"),
    "volumen": cierre(10355, condicion="si confirman los próximos puestos"),
    "plazo": cierre(10573, condicion="si pagan contado."),
}


def _alterna(mensajes: list[dict], ultimo: str):
    roles = [m["role"] for m in mensajes]
    assert roles[0] == "user"
    assert all(a != b for a, b in zip(roles, roles[1:])), roles
    assert roles[-1] == ultimo


class LLMFalso:
    """Reemplaza a pedir_texto/pedir_json. El cierre depende de la estrategia de la corrida."""

    def __init__(self, cierres):
        self.cierres = cierres
        self.textos, self.jsons, self.prompts = [], [], []
        self.system_redactar = ""

    async def pedir_texto(self, *, system, mensajes, **_):
        self.textos.append(mensajes)
        self.prompts += [system] + [m["content"] for m in mensajes]
        _alterna(mensajes, "user")
        estrategia = re.search(
            r"Estrategia asignada para esta simulación: (\w+)", system
        )
        if estrategia:
            return f"[{estrategia.group(1)}] propuesta {len(mensajes)}"
        if system.startswith("Redactá"):
            self.system_redactar = system
            return "Hola! ¿Nos hacés 5 % si sumamos los próximos puestos?"
        return "Dejame ver qué puedo hacer."

    async def pedir_json(self, *, system, contenido, esquema, historial, **_):
        self.jsons.append(historial)
        self.prompts += [system] + [c["text"] for c in contenido]
        _alterna(historial, "assistant")
        assert esquema is CierreGemelo
        estrategia = re.search(r"\[(\w+)\]", historial[0]["content"]).group(1)
        resultado = self.cierres[estrategia]
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


@pytest.fixture
def llm(monkeypatch):
    def instalar(cierres):
        falso = LLMFalso(cierres)
        monkeypatch.setattr(negociacion, "pedir_texto", falso.pedir_texto)
        monkeypatch.setattr(negociacion, "pedir_json", falso.pedir_json)
        return falso

    return instalar


@pytest.fixture(scope="module")
def contexto():
    return contexto_demo("ofisillas")


def correr(contexto):
    return asyncio.run(ensayar(contexto))


def por_nombre(resultado):
    return {e["nombre"]: e for e in resultado["estrategias"]}


def test_el_contexto_de_c_es_el_de_la_demo(contexto):
    assert contexto.valor_en_juego_uyu == Decimal("163500.00")
    [silla] = contexto.items
    assert silla.mejor_alternativa_nombre == "Mueblería Rivera"
    assert "mínimo 20" in silla.mejor_alternativa_condicion


def test_ofisillas_gana_volumen(llm, contexto):
    falso = llm(CIERRES_DEMO)
    resultado = correr(contexto)
    e = por_nombre(resultado)

    assert set(resultado) == {"estrategias", "elegida", "mensaje_propuesto"}
    assert resultado["elegida"] == "volumen"
    assert resultado["mensaje_propuesto"].startswith("Hola!")
    assert e["volumen"]["concesion_obtenida_pct"] == 5.0  # 545 de 10.900
    assert e["volumen"]["riesgo"] == "bajo"
    assert e["plazo"]["concesion_obtenida_pct"] == 3.0
    assert e["plazo"]["descripcion"].endswith(
        "Condición del proveedor: si pagan contado."
    )
    assert e["competencia"]["concesion_obtenida_pct"] == 0
    assert e["competencia"]["riesgo"] == "medio"
    # 3 estrategias × 2 corridas × (3 turnos de Abasto + 3 del gemelo) + el mensaje final.
    assert len(falso.textos) == 37
    assert len(falso.jsons) == 6
    roles = [t["rol"] for t in e["volumen"]["transcripcion"]]
    assert roles == ["abasto", "proveedor"] * 3
    assert not [p for p in falso.prompts if "{{" in p]


def test_cada_estrategia_cumple_el_modelo_de_c(llm, contexto):
    llm(CIERRES_DEMO)
    for e in correr(contexto)["estrategias"]:
        assert set(e) == {
            "nombre",
            "descripcion",
            "transcripcion",
            "concesion_obtenida_pct",
            "riesgo",
        }
        EstrategiaNegociacion.model_validate({**e, "ganancia_esperada_uyu": 0})


def test_integracion_con_c_pone_la_ganancia_y_coincide_la_elegida(
    llm, contexto, monkeypatch, caplog
):
    llm(CIERRES_DEMO)
    monkeypatch.setattr(
        config,
        "settings",
        dataclasses.replace(config.settings, anthropic_api_key="test"),
    )
    neg = asyncio.run(integracion_a.negociar(contexto))

    ganancias = {e.nombre: e.ganancia_esperada_uyu for e in neg.estrategias}
    assert ganancias == {
        "competencia": Decimal("0.00"),
        "volumen": Decimal("8175.00"),  # 545 × 15 sillas
        "plazo": Decimal("4905.00"),
    }
    assert neg.elegida == "volumen" and neg.estado == "simulada"
    assert "corresponde" not in caplog.text  # C no tuvo que corregir la elegida


def test_gemelo_conoce_su_perfil_y_abasto_las_alternativas(llm, contexto):
    falso = llm(CIERRES_DEMO)
    correr(contexto)
    gemelo = next(
        p for p in falso.prompts if p.startswith("Estás actuando como Ofisillas")
    )
    assert "hasta 8% por debajo" in gemelo
    assert (
        "Silla ergonómica de oficina [silla]: $ 10.900 por unidad sin IVA × 15"
        in gemelo
    )
    assert "envío $ 1.200, pago a 30 días, entrega en 7 días" in gemelo
    assert "pago contado, compra futura de más puestos" in gemelo
    abasto = next(p for p in falso.prompts if "Estrategia asignada" in p)
    assert "Mueblería Rivera cotiza $ 9.800 por unidad sin IVA" in abasto
    assert "exige mínimo 20 unidades y el pedido es de 15" in abasto
    assert "8%" not in abasto  # Abasto no conoce el piso del gemelo


def test_mensaje_final_solo_usa_datos_de_la_estrategia(llm, contexto):
    falso = llm(CIERRES_DEMO)
    correr(contexto)
    assert "próximos puestos" in falso.system_redactar
    assert "5 % de descuento" in falso.system_redactar
    assert "$ 10.355 por unidad" in falso.system_redactar
    assert "Mueblería Rivera" not in falso.system_redactar
    assert "8%" not in falso.system_redactar  # nunca el piso del gemelo

    falso = llm({**CIERRES_DEMO, "competencia": cierre(10137)})
    resultado = correr(contexto)
    assert resultado["elegida"] == "competencia"
    assert "Mueblería Rivera cotiza $ 9.800" in falso.system_redactar


def test_el_piso_y_lo_cotizado_acotan_la_oferta(llm, contexto):
    llm(
        {
            "competencia": cierre(9000),  # debajo del piso de 8 % → 10.028
            "volumen": cierre(11500),  # más caro que lo cotizado → 10.900
            "plazo": cierre(10500, acepta=False),  # no acepta: no cuenta
        }
    )
    e = por_nombre(correr(contexto))
    assert e["competencia"]["concesion_obtenida_pct"] == 8.0  # 872 × 15 = 13.080
    assert e["volumen"]["concesion_obtenida_pct"] == 0
    assert e["plazo"]["concesion_obtenida_pct"] == 0


def test_producto_ajeno_o_precio_invalido_se_ignoran(llm, contexto):
    raro = CierreGemelo(
        acepta_negociar=True,
        precios_finales=[
            PrecioFinal(producto_id="notebook", precio=1),
            PrecioFinal(producto_id="silla", precio=0),
        ],
        condicion=None,
        animo="cordial",
    )
    llm({"competencia": raro, "volumen": raro, "plazo": raro})
    assert all(
        e["concesion_obtenida_pct"] == 0 for e in correr(contexto)["estrategias"]
    )


def test_molesto_es_riesgo_alto_y_no_se_elige(llm, contexto):
    llm({**CIERRES_DEMO, "competencia": cierre(10137, animo="molesto")})
    resultado = correr(contexto)
    assert por_nombre(resultado)["competencia"]["riesgo"] == "alto"
    assert resultado["elegida"] == "volumen"


def test_si_todas_son_riesgo_alto_gana_la_de_mayor_ganancia(llm, contexto):
    llm(
        {
            n: cierre(p, animo="molesto")
            for n, p in [("competencia", 10700), ("volumen", 10400), ("plazo", 10800)]
        }
    )
    assert correr(contexto)["elegida"] == "volumen"


def no_se_pudo_ensayar(estrategia: dict) -> bool:
    return (
        estrategia["descripcion"].startswith(negociacion.NO_ENSAYADA)
        and estrategia["transcripcion"] == []
        and estrategia["concesion_obtenida_pct"] == 0
        and estrategia["riesgo"] == "alto"
    )


def test_una_estrategia_fallida_no_tira_la_negociacion(llm, contexto):
    llm({**CIERRES_DEMO, "plazo": LLMError("timeout")})
    resultado = correr(contexto)
    estrategias = resultado["estrategias"]
    assert [e["nombre"] for e in estrategias] == ["competencia", "volumen", "plazo"]
    assert no_se_pudo_ensayar(estrategias[-1])
    assert not no_se_pudo_ensayar(estrategias[0])
    assert resultado["elegida"] == "volumen"


def test_si_fallan_todas_las_corridas_c_recibe_un_error_legible(llm, contexto):
    llm({n: LLMError("No hay conexión con la API del LLM.") for n in CIERRES_DEMO})
    # C atrapa CapaNoDisponible: 501 con el mensaje, y el pedido vuelve a "optimizado".
    with pytest.raises(CapaNoDisponible, match="No hay conexión"):
        correr(contexto)


def test_sin_items_no_hay_que_negociar(llm, contexto):
    falso = llm(CIERRES_DEMO)
    with pytest.raises(ValueError, match="no le compra nada a Ofisillas"):
        correr(contexto.model_copy(update={"items": []}))
    assert falso.textos == []


def test_empate_se_resuelve_igual_que_c(llm, contexto, monkeypatch, caplog):
    """competencia y volumen sacan 8 %: C elige la primera de la lista y el mensaje es de esa."""
    falso = llm(
        {
            "competencia": cierre(9000, animo="neutral"),
            "volumen": cierre(9000),
            "plazo": cierre(10573),
        }
    )
    monkeypatch.setattr(
        config,
        "settings",
        dataclasses.replace(config.settings, anthropic_api_key="test"),
    )
    neg = asyncio.run(integracion_a.negociar(contexto))
    assert neg.elegida == "competencia"
    assert "Mueblería Rivera cotiza $ 9.800" in falso.system_redactar
    assert "corresponde" not in caplog.text


def sin_alternativa_mas_barata(contexto, precio):
    items = [
        i.model_copy(update={"mejor_alternativa_precio": Decimal(precio)})
        for i in contexto.items
    ]
    return contexto.model_copy(update={"items": items})


def test_una_alternativa_mas_cara_no_sirve_para_competencia(contexto):
    assert items_negociados(contexto)[0].alternativa.startswith("Mueblería Rivera")
    for precio in ("10900", "11000"):  # igual o más cara que lo cotizado
        items = items_negociados(sin_alternativa_mas_barata(contexto, precio))
        assert items[0].alternativa is None
        assert texto_alternativas(items).startswith("ninguna")


def test_sin_alternativa_mas_barata_no_se_ensaya_competencia(llm, monkeypatch, caplog):
    compuservice = contexto_demo("compuservice")  # TecnoImport cotiza más caro todo
    falso = llm(
        {
            "volumen": cierre(26000, producto="notebook"),
            "plazo": cierre(27000, producto="notebook"),
        }
    )
    monkeypatch.setattr(
        config,
        "settings",
        dataclasses.replace(config.settings, anthropic_api_key="test"),
    )
    neg = asyncio.run(integracion_a.negociar(compuservice))

    assert [e.nombre for e in neg.estrategias] == ["volumen", "plazo", "competencia"]
    competencia = neg.estrategias[-1]
    assert competencia.concesion_obtenida_pct == 0 and competencia.riesgo == "alto"
    assert competencia.transcripcion == []
    assert neg.elegida == "volumen" and "corresponde" not in caplog.text
    # 2 estrategias × 2 corridas × 6 turnos + el mensaje final; ningún turno de competencia.
    assert len(falso.textos) == 25 and len(falso.jsons) == 4
    assert not [p for p in falso.prompts if "simulación: competencia" in p]
    assert not [p for p in falso.prompts if "TecnoImport S.A. cotiza" in p]


def test_si_todas_empatan_en_cero_no_gana_competencia_sin_ensayar(llm):
    llm({n: cierre(animo="molesto") for n in ("volumen", "plazo")})
    resultado = correr(contexto_demo("papelera_del_sur"))
    assert resultado["elegida"] == "volumen"


def test_una_corrida_que_no_termina_a_tiempo_se_descarta(llm, contexto, monkeypatch):
    falso = llm(CIERRES_DEMO)
    rapido = falso.pedir_texto

    async def plazo_colgado(*, system, mensajes, **kw):
        if "simulación: plazo" in system:
            await asyncio.sleep(10)
        return await rapido(system=system, mensajes=mensajes, **kw)

    monkeypatch.setattr(negociacion, "pedir_texto", plazo_colgado)
    monkeypatch.setattr(negociacion, "PLAZO_CORRIDAS_SEGUNDOS", 0.3)
    resultado = correr(contexto)
    estrategias = resultado["estrategias"]
    assert [e["nombre"] for e in estrategias] == ["competencia", "volumen", "plazo"]
    assert no_se_pudo_ensayar(estrategias[-1])
    assert resultado["elegida"] == "volumen"


def test_si_ninguna_corrida_termina_a_tiempo_es_timeout(llm, contexto, monkeypatch):
    llm(CIERRES_DEMO)

    async def colgado(**_):
        await asyncio.sleep(10)

    monkeypatch.setattr(negociacion, "pedir_texto", colgado)
    monkeypatch.setattr(negociacion, "PLAZO_CORRIDAS_SEGUNDOS", 0.3)
    with pytest.raises(TimeoutError, match="no terminó"):  # C responde 504
        correr(contexto)


def test_si_el_mensaje_final_no_llega_a_tiempo_es_timeout(llm, contexto, monkeypatch):
    falso = llm(CIERRES_DEMO)
    rapido = falso.pedir_texto

    async def redactar_colgado(*, system, mensajes, **kw):
        if system.startswith("Redactá"):
            await asyncio.sleep(10)
        return await rapido(system=system, mensajes=mensajes, **kw)

    monkeypatch.setattr(negociacion, "pedir_texto", redactar_colgado)
    monkeypatch.setattr(negociacion, "PLAZO_TOTAL_SEGUNDOS", 0.5)
    with pytest.raises(TimeoutError):  # C responde 504
        correr(contexto)


def test_alternativas_y_compromiso_por_proveedor():
    # Papelera y Compuservice son las más baratas en lo que les compra el plan.
    papelera = items_negociados(contexto_demo("papelera_del_sur"))
    assert [i.producto_id for i in papelera] == ["resma_a4", "desinfectante"]
    assert texto_alternativas(papelera).startswith("ninguna")
    # Solo lo que sale del plan: ni plazos ni cantidades que nadie decidió.
    assert compromiso_volumen(papelera) == (
        "repetir el pedido mensual (Resma papel A4 75 g (500 hojas), Desinfectante de pisos)"
    )

    compuservice = items_negociados(contexto_demo("compuservice"))
    assert texto_alternativas(compuservice).startswith("ninguna")
    assert "próximos puestos" in compromiso_volumen(compuservice)
    assert "pedido mensual (Tóner HP 85A original)" in compromiso_volumen(compuservice)


def test_sin_alternativa_lo_dice_en_vez_de_inventar(contexto):
    solo = contexto.model_copy(
        update={
            "items": [
                i.model_copy(
                    update={
                        "mejor_alternativa_proveedor_id": None,
                        "mejor_alternativa_nombre": None,
                        "mejor_alternativa_precio": None,
                        "mejor_alternativa_condicion": None,
                    }
                )
                for i in contexto.items
            ]
        }
    )
    assert texto_alternativas(items_negociados(solo)).startswith("ninguna")
