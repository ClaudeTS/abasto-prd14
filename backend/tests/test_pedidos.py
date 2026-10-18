"""Listado y detalle de pedidos, estados §6.2, conversaciones por canal y PDF (PRD 1.4: RF-05, 10, 12, 18)."""

from __future__ import annotations

import dataclasses
import io
import sys
import time
import types
from datetime import datetime, timedelta

import pdfplumber
import pytest
from fastapi.testclient import TestClient

from app import agente, config, store
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
    """Negociación falsa (Capa 5) y extracción con fixtures aunque haya "key" (como en test_agente.py)."""

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
    monkeypatch.setitem(sys.modules, "app.explicacion", types.SimpleNamespace())
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
    raise AssertionError(f"La corrida no llegó a {estados}: {corrida['estado']}")


def _por_numero(listado: dict) -> dict[str, dict]:
    return {p["numero"]: p for p in listado["pedidos"]}


def _mensajes(detalle: dict) -> list[dict]:
    return [m for c in detalle["conversaciones"] for m in c["mensajes"]]


# ---------------------------------------------------------------- listado (RF-12, RF-05)
def test_listado_con_el_pedido_vivo_y_los_de_ejemplo(client):
    r = client.get("/pedidos")
    assert r.status_code == 200, r.text
    listado = r.json()
    pedidos = _por_numero(listado)
    assert len(pedidos) == 9 and listado["total"] == 9
    demo = pedidos["PED-0142"]
    assert demo["id"] == PEDIDO and demo["demo"] and not demo["ejemplo"]
    assert demo["estado"] == "nuevo" and demo["origen"] == "demo" and demo["cliente_interno"] == "personal"
    assert [p["producto_id"] for p in demo["productos"]] == ["notebook", "silla", "resma_a4", "toner", "desinfectante"]
    assert all(p["ejemplo"] for n, p in pedidos.items() if n != "PED-0142")
    estados = {n: p["estado"] for n, p in pedidos.items()}
    assert estados["PED-0135"] == "cancelado" and estados["PED-0137"] == "pendiente_entrega"
    assert {"recibido", "cerrado"} <= set(estados.values())
    assert listado["conteos"] == {"en_tramite": 2, "recibidos": 6, "todos": 9}


def test_filtros_del_listado(client):
    def numeros(params: str) -> set[str]:
        r = client.get(f"/pedidos?{params}")
        assert r.status_code == 200, r.text
        return {p["numero"] for p in r.json()["pedidos"]}

    assert numeros("q=OC-0883") == {"PED-0133"}  # orden de compra
    assert numeros("q=toner") == numeros("q=Tóner")  # sin tildes ni mayúsculas
    assert "PED-0136" in numeros("q=tóner") and "PED-0142" in numeros("q=tóner")
    assert numeros("q=mueblería rivera") == {"PED-0134"}  # proveedor que cotizó
    assert numeros("cliente_interno=ventas") == {"PED-0136", "PED-0137"}
    assert numeros("estado=cancelado") == {"PED-0135"}
    assert numeros("estado=recibido,cerrado") == numeros("situacion=recibidos")
    assert numeros("situacion=en_tramite") == {"PED-0142", "PED-0137"}
    assert numeros("origen=solicitud_voz") == {"PED-0137"}
    assert numeros("desde=2026-10-05&hasta=2026-10-09") == {"PED-0133", "PED-0134", "PED-0135", "PED-0136"}
    assert client.get("/pedidos?estado=inventado").status_code == 422
    assert client.get("/pedidos?cliente_interno=gerencia").status_code == 422
    assert client.get("/pedidos?desde=2026-10-10&hasta=2026-10-01").status_code == 422
    con_conteos = client.get("/pedidos?cliente_interno=ventas&situacion=recibidos").json()
    assert con_conteos["conteos"] == {"en_tramite": 1, "recibidos": 1, "todos": 2} and con_conteos["total"] == 1


# ---------------------------------------------------------------- detalle y conversaciones (RF-10)
def test_detalle_de_ejemplo_con_conversaciones_por_canal(client):
    r = client.get("/pedidos/hist_ped_0131/detalle")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ejemplo"] and d["numero"] == "PED-0131" and d["estado"] == "cerrado" and d["acciones"] == []
    assert [e["estado"] for e in d["historial_estados"]][:2] == ["nuevo", "cotizando"]
    papelera = next(c for c in d["cotizaciones"] if c["proveedor_id"] == "papelera_del_sur")
    assert papelera["items"][0]["precio_unitario_sin_iva"] == 178.69  # 1.090 con IVA / 1,22 / 5
    assert papelera["vigencia_dias"] == 30  # no indicó vigencia
    assert d["plan"]["costo_total"] == 17869 and d["plan"]["costo_baseline"] == 23500
    (orden,) = d["ordenes"]
    assert orden["numero"] == "OC-0881" and orden["estado"] == "recibida" and orden["total_sin_iva"] == 17869
    mensajes = _mensajes(d)
    for m in mensajes:
        assert m["canal"] in ("whatsapp", "email", "pdf", "foto", "audio", "llamada", "nota_voz")
        assert m["sentido"] in ("enviado", "recibido") and m["fecha"] and m["participante"]
    llamadas = [m for m in mensajes if m["canal"] == "llamada"]
    assert [l["llamada"]["resultado"] for l in llamadas] == ["no_atendida", "atendida"]
    atendida = llamadas[1]
    fin = datetime.fromisoformat(atendida["fecha"]) + timedelta(seconds=atendida["llamada"]["duracion_segundos"])
    assert datetime.fromisoformat(atendida["llamada"]["audio_disponible_hasta"]) == fin + timedelta(days=60)
    assert llamadas[0]["llamada"]["audio_disponible_hasta"] is None
    assert len(atendida["transcripcion"]) >= 4 and atendida["transcripcion"][0]["quien"] == "Abasto"
    solicitud = next(m for m in mensajes if m["motivo"] == "solicitud_cotizacion")
    assert solicitud["sentido"] == "enviado" and "100 × Resma papel A4" in solicitud["texto"]
    oc = next(m for m in mensajes if m["motivo"] == "orden")
    assert "OC-0881" in oc["texto"] and "$ 17.869 + IVA" in oc["texto"]


def test_detalle_inexistente(client):
    assert client.get("/pedidos/no_existe/detalle").status_code == 404
    assert client.post("/pedidos/no_existe/recibir").status_code == 404


def test_pedido_demo_cotizado_desde_la_demo_guiada(client):
    """Sin agente: el feed de siempre. Estados del pedido interno; solicitud reconstruida y respuestas."""
    assert client.post(f"/pedidos/{PEDIDO}/cotizar").status_code == 200
    limite = time.time() + 10
    while time.time() < limite and client.get(f"/pedidos/{PEDIDO}").json()["estado"] != "cotizado":
        time.sleep(0.05)
    d = client.get(f"/pedidos/{PEDIDO}/detalle").json()
    assert d["estado"] == "cotizado" and d["origen"] == "demo" and d["corrida_id"] is None
    mensajes = _mensajes(d)
    enviados = [m for m in mensajes if m["motivo"] == "solicitud_cotizacion"]
    assert len(enviados) == 6 and all(m["nota"] for m in enviados)
    assert {m["canal"] for m in enviados} == {"whatsapp", "email"}  # email a TecnoImport (cotiza en PDF)
    recibidos = {m["participante"]: m for m in mensajes if m["sentido"] == "recibido"}
    assert recibidos["Papelera del Sur"]["canal"] == "audio" and recibidos["TecnoImport S.A."]["canal"] == "pdf"
    assert recibidos["Mueblería Rivera"]["archivo_url"].endswith(".jpg")
    assert recibidos["Compuservice"]["etiqueta"] == "Para revisar"  # el IVA dudoso
    assert len(d["cotizaciones"]) == 6


# ---------------------------------------------------------------- ciclo completo con el agente (§6.2)
def test_ciclo_completo_del_pedido_con_el_agente(client, gemelo):
    texto = client.get("/agente/ejemplo").json()["texto"]
    corrida = client.post("/agente", json={"texto": texto, "llamar_si_no_responde": False}).json()
    corrida = _esperar(client, corrida["id"], ("esperando_confirmacion",))
    d = client.get(f"/pedidos/{PEDIDO}/detalle").json()
    assert d["estado"] == "nuevo" and d["origen"] == "solicitud_voz" and d["corrida_id"] == corrida["id"]
    (pedido_de_lucia,) = [m for m in _mensajes(d) if m["canal"] == "nota_voz"]
    assert pedido_de_lucia["texto"] == texto and pedido_de_lucia["sentido"] == "recibido"

    client.post(f"/agente/{corrida['id']}/confirmar")
    corrida = _esperar(client, corrida["id"], ("esperando_revision",))
    assert client.get(f"/pedidos/{PEDIDO}/detalle").json()["estado"] == "cotizando"
    client.post(f"/cotizaciones/{corrida['revision'][0]['cotizacion_id']}/confirmar", json={"incluye_iva": True})
    corrida = _esperar(client, corrida["id"], ("esperando_aprobacion",))

    d = client.get(f"/pedidos/{PEDIDO}/detalle").json()
    estados = [e["estado"] for e in d["historial_estados"]]
    assert estados == ["nuevo", "cotizando", "cotizado", "negociando", "pendiente_aprobacion"]
    assert d["estado"] == "pendiente_aprobacion" and d["acciones"] == []
    ordenes = {o["proveedor_id"]: o for o in d["ordenes"]}
    assert ordenes["papelera_del_sur"]["estado"] == "pendiente_entrega"  # salió sola
    assert ordenes["compuservice"]["estado"] == "pendiente_aprobacion" and ordenes["compuservice"]["corrida_id"] == corrida["id"]
    assert d["negociaciones"][0]["proveedor_id"] == "ofisillas"
    oc = [m for m in _mensajes(d) if m["motivo"] == "orden"]
    assert [m["etiqueta"] for m in oc] == [ordenes["papelera_del_sur"]["numero"]]
    resumen = _por_numero(client.get("/pedidos?q=OC-1003").json())
    assert set(resumen) == {"PED-0142"}  # la OC de Papelera se busca en el listado

    assert client.post(f"/pedidos/{PEDIDO}/recibir").status_code == 409  # todavía no se aprobó todo
    for orden in ("oc_compuservice", "oc_ofisillas"):
        assert client.post(f"/agente/{corrida['id']}/ordenes/{orden}/aprobar").status_code == 200
    d = client.get(f"/pedidos/{PEDIDO}/detalle").json()
    assert d["estado"] == "pendiente_entrega" and d["acciones"] == ["recibir"]
    assert [e["estado"] for e in d["historial_estados"]][-2:] == ["aprobado", "pendiente_entrega"]

    r = client.post(f"/pedidos/{PEDIDO}/recibir")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "recibido" and r.json()["acciones"] == ["cerrar"]
    assert all(o["estado"] == "recibida" for o in r.json()["ordenes"])
    assert client.post(f"/pedidos/{PEDIDO}/recibir").status_code == 409
    assert client.post(f"/pedidos/{PEDIDO}/cerrar").json()["estado"] == "cerrado"
    listado = client.get("/pedidos?situacion=recibidos").json()
    assert "PED-0142" in _por_numero(listado)


def test_cancelar_desde_el_agente(client, gemelo):
    texto = client.get("/agente/ejemplo").json()["texto"]
    corrida = client.post("/agente", json={"texto": texto}).json()
    corrida = _esperar(client, corrida["id"], ("esperando_confirmacion",))
    client.post(f"/agente/{corrida['id']}/cancelar")
    d = client.get(f"/pedidos/{PEDIDO}/detalle").json()
    assert d["estado"] == "cancelado" and d["motivo_cancelacion"]


def test_cliente_interno_y_contactos_de_otros_bloques(client):
    """RF-05: el Bloque 2 agrega `cliente_interno` a la corrida. El Bloque 5 escribe `contactos`."""
    ahora = datetime(2026, 10, 20, 9, 0)
    store.guardar_dict(
        "agentes",
        "ag_prueba",
        {
            "id": "ag_prueba",
            "pedido_id": PEDIDO,
            "texto": None,
            "horizonte_meses": 1,
            "opciones": {},
            "estado": "cancelada",
            "pasos": [{"id": i, "titulo": i} for i in ("entender", "inventario", "confirmar", "cotizar")],
            "creada_en": ahora.isoformat(),
            "actualizada_en": ahora.isoformat(),
            "cliente_interno": "ventas",
            "canal": "email",
        },
    )
    store.guardar_dict(
        "contactos",
        "ct_1",
        {
            "id": "ct_1",
            "pedido_id": PEDIDO,
            "proveedor_id": "papelera_del_sur",
            "canal": "whatsapp",
            "sentido": "enviado",
            "texto": "Te llamé dos veces: ¿me pasás el precio por acá?",
            "enviado_en": "2026-10-20T10:31:00",
            "motivo": "aviso_no_atendio",
        },
    )
    store.guardar_dict("contactos", "ct_otro", {"id": "ct_otro", "pedido_id": "otro", "canal": "fax"})
    d = client.get(f"/pedidos/{PEDIDO}/detalle").json()
    assert d["cliente_interno"] == "ventas" and d["origen"] == "solicitud_email"
    (aviso,) = [m for m in _mensajes(d) if m["motivo"] == "aviso_no_atendio"]
    assert aviso["canal"] == "whatsapp" and aviso["sentido"] == "enviado" and aviso["participante"] == "Papelera del Sur"
    assert {p["numero"] for p in client.get("/pedidos?cliente_interno=ventas").json()["pedidos"]} >= {"PED-0142"}


def test_recibir_y_cerrar_un_pedido_de_ejemplo(client):
    assert client.post("/pedidos/hist_ped_0136/cerrar").json()["estado"] == "cerrado"  # recibido → cerrado
    assert client.post("/pedidos/hist_ped_0131/recibir").status_code == 409  # ya está cerrado
    r = client.post("/pedidos/hist_ped_0137/recibir")
    assert r.status_code == 200 and r.json()["estado"] == "recibido"
    assert r.json()["ordenes"][0]["estado"] == "recibida"
    client.post("/reset")  # las marcas viven en el runtime: el reset las borra
    assert client.get("/pedidos/hist_ped_0137/detalle").json()["estado"] == "pendiente_entrega"


# ---------------------------------------------------------------- PDF (RF-18)
def _texto_pdf(contenido: bytes) -> str:
    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def test_informe_pdf(client):
    r = client.get("/pedidos/hist_ped_0134/informe.pdf?incluir=pedido,dialogo")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert 'filename="PED-0134-completo.pdf"' in r.headers["content-disposition"]
    texto = _texto_pdf(r.content)
    assert "PED-0134" in texto and "Datos de ejemplo" in texto
    assert "Datos del pedido" in texto and "OC-0884" in texto
    assert "Diálogo del agente" in texto and "Llamada" in texto and "Transcripción completa" in texto
    assert "audio disponible hasta el 06/12/2026" in texto

    solo_pedido = _texto_pdf(client.get("/pedidos/hist_ped_0134/informe.pdf?incluir=pedido").content)
    assert "Datos del pedido" in solo_pedido and "Diálogo del agente" not in solo_pedido
    solo_dialogo = _texto_pdf(client.get("/pedidos/hist_ped_0134/informe.pdf?incluir=dialogo").content)
    assert "Diálogo del agente" in solo_dialogo and "Historial de estados" not in solo_dialogo

    assert client.get("/pedidos/hist_ped_0134/informe.pdf?incluir=todo").status_code == 422
    assert client.get("/pedidos/hist_ped_0134/informe.pdf?incluir=").status_code == 422
    assert client.get("/pedidos/no_existe/informe.pdf").status_code == 404
    vivo = client.get(f"/pedidos/{PEDIDO}/informe.pdf")
    assert vivo.status_code == 200 and "PED-0142" in _texto_pdf(vivo.content)
