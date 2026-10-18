"""Reglas por producto, historial, vista previa y configuración (PRD 1.4: RF-02/03/04, RF-13/14/15, RF-20)."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import agente, inventario, pipeline
from app.main import app

PEDIDO = "pedido_demo_oct_2026"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(agente, "INTERVALO_S", 0.05)
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _admin(client: TestClient) -> dict[str, str]:
    token = client.post("/auth/login", json={"usuario": "lucia", "contrasena": "abasto2026"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _repo(client: TestClient, producto_id: str) -> dict:
    return next(p for p in client.get("/inventario").json()["productos"] if p["producto_id"] == producto_id)["reposicion"]


# ---------------------------------------------------------------- lectura
def test_reglas_de_cada_producto_con_su_contexto(client):
    todas = client.get("/reglas").json()
    assert [r["producto_id"] for r in todas] == ["notebook", "silla", "resma_a4", "toner", "desinfectante"]
    resma = client.get("/reglas/resma_a4").json()
    reglas = resma["reglas"]
    # compra automática, mínimo y tope del total salen del inventario del agente (sin duplicar)
    assert reglas["compra_automatica"] is True and reglas["stock_minimo"] == 40
    assert reglas["tope_automatico_uyu"] == 30000
    assert reglas["stock_base"] is None and reglas["zafra"] is None and reglas["tope_precio_unitario"] is None
    assert reglas["descuento_objetivo_pct"] is None and reglas["concesion_maxima_pct"] is None  # a definir
    assert [p["proveedor_id"] for p in reglas["proveedores"]] == ["papelera_del_sur", "distribuidora_oriental"]
    ctx = resma["contexto"]
    assert ctx["stock_actual"] == 10 and ctx["fecha_corte"].startswith("2026-10-19T18:00")
    assert ctx["reposicion"]["cantidad"] == 150 and ctx["reposicion"]["motivo"] == "pronostico"
    assert ctx["mejor_precio"] is None  # todavía no se cotizó: no se inventa un precio
    assert client.get("/reglas/zzz").status_code == 404


# ---------------------------------------------------------------- semántica en el inventario
def test_sin_reglas_nuevas_la_reposicion_es_la_de_siempre(client):
    repo = _repo(client, "resma_a4")
    assert repo["motivo"] == "pronostico" and repo["cantidad"] == 150
    assert "Pronóstico 120 + mínimo 40 − stock 10 = 150" in repo["evidencia"]


def test_stock_base_repone_hasta_el_base(client):
    h = _admin(client)
    r = client.patch("/reglas/resma_a4", json={"stock_base": 200, "motivo": "Reposición por máximo"}, headers=h)
    assert r.status_code == 200, r.text
    repo = _repo(client, "resma_a4")  # 10 ≤ 40: lleva el stock a 200 (de a 5)
    assert repo["motivo"] == "stock_base" and repo["cantidad"] == 190
    assert "llegó al mínimo 40: stock base 200 − stock 10 = 190" in repo["evidencia"]
    # tóner: 7 > mínimo 4, con stock base no se compra hasta tocar el mínimo
    client.patch("/reglas/toner", json={"stock_base": 12, "motivo": "x"}, headers=h)
    toner = _repo(client, "toner")
    assert toner["cantidad"] == 0 and "no llegó al mínimo 4" in toner["evidencia"]


def test_zafra_pide_la_cantidad_de_zafra(client):
    h = _admin(client)
    zafra = {"inicio": "10-01", "fin": "12-31", "cantidad": 102}  # hoy (20/10) está adentro
    r = client.patch("/reglas/desinfectante", json={"zafra": zafra, "motivo": "Temporada de limpieza"}, headers=h)
    assert r.status_code == 200, r.text
    repo = _repo(client, "desinfectante")
    assert repo["motivo"] == "zafra" and repo["cantidad"] == 105  # de a 5 L
    assert "Zafra (01/10 a 31/12): cantidad de zafra 102 = 102 L → 105 L" in repo["evidencia"]
    assert client.get("/reglas/desinfectante").json()["contexto"]["en_zafra"] is True
    # fuera de la zafra vuelve a la cuenta de siempre
    client.patch("/reglas/desinfectante", json={"zafra": {"inicio": "05-01", "fin": "08-31", "cantidad": 100}, "motivo": "x"}, headers=h)
    assert _repo(client, "desinfectante")["motivo"] == "pronostico"


def test_zafra_que_cruza_el_fin_de_anio():
    from datetime import date

    z = {"inicio": "11-15", "fin": "02-28", "cantidad": 10}
    assert inventario.en_zafra(z, date(2026, 12, 31)) and inventario.en_zafra(z, date(2027, 1, 10))
    assert not inventario.en_zafra(z, date(2026, 10, 20))


def test_compra_automatica_es_el_modo_del_inventario(client):
    h = _admin(client)
    r = client.patch("/reglas/toner", json={"compra_automatica": False, "stock_minimo": 5, "motivo": "Revisar precios"}, headers=h)
    assert r.status_code == 200
    item = next(p for p in client.get("/inventario").json()["productos"] if p["producto_id"] == "toner")
    assert item["modo"] == "manual" and item["stock_minimo"] == 5
    # y al revés: lo que cambia el inventario se ve en las reglas
    client.patch("/inventario/toner", json={"modo": "automatico"})
    assert client.get("/reglas/toner").json()["reglas"]["compra_automatica"] is True


# ---------------------------------------------------------------- validación y motivo
def test_validaciones(client):
    h = _admin(client)
    sin_motivo = client.patch("/reglas/resma_a4", json={"stock_minimo": 50}, headers=h)
    assert sin_motivo.status_code == 422
    vacio = client.patch("/reglas/resma_a4", json={"stock_minimo": 50, "motivo": "  "}, headers=h)
    assert vacio.status_code == 422 and vacio.json()["detalle"] == {"motivo": "Obligatorio para guardar."}
    r = client.patch("/reglas/resma_a4", json={"stock_base": 30, "motivo": "x"}, headers=h)
    assert r.status_code == 422 and "mayor que el stock mínimo" in r.json()["detalle"]["stock_base"]
    r = client.patch("/reglas/resma_a4", json={"stock_minimo": -1, "tope_precio_unitario": -5, "motivo": "x"}, headers=h)
    assert set(r.json()["detalle"]) == {"stock_minimo", "tope_precio_unitario"}
    r = client.patch("/reglas/resma_a4", json={"zafra": {"inicio": "13-01", "fin": "02-01", "cantidad": 5}, "motivo": "x"}, headers=h)
    assert "zafra" in r.json()["detalle"]
    r = client.patch("/reglas/resma_a4", json={"concesion_maxima_pct": 150, "motivo": "x"}, headers=h)
    assert "concesion_maxima_pct" in r.json()["detalle"]
    r = client.patch("/reglas/resma_a4", json={"proveedores": [{"proveedor_id": "trucho", "prioridad": 1}], "motivo": "x"}, headers=h)
    assert "proveedores" in r.json()["detalle"]
    assert client.get("/reglas/resma_a4/historial").json() == []  # nada se guardó


# ---------------------------------------------------------------- historial y reversión
def test_historial_con_valor_anterior_y_nuevo_y_revertir(client):
    h = _admin(client)
    cambio = {
        "stock_base": 200,
        "tope_precio_unitario": 160,
        "proveedores": [
            {"proveedor_id": "distribuidora_oriental", "prioridad": 1, "minimo_compra": 50, "unidad_venta": "caja de 5 resmas", "factor_conversion": 5},
            {"proveedor_id": "papelera_del_sur", "prioridad": 2},
        ],
        "sustitutos": [{"nombre": "Resma A4 80 g"}],
        "motivo": "Más demanda que el año pasado",
    }
    vista = client.patch("/reglas/resma_a4", json=cambio, headers=h).json()
    assert vista["actualizado_por"] == "Lucía"
    assert vista["reglas"]["proveedores"][0]["proveedor_id"] == "distribuidora_oriental"
    hist = client.get("/reglas/resma_a4/historial").json()
    por_campo = {c["campo"]: c for c in hist}
    assert set(por_campo) == {"stock_base", "tope_precio_unitario", "proveedores", "sustitutos"}
    base = por_campo["stock_base"]
    assert (base["texto_anterior"], base["texto_nuevo"]) == ("sin definir", "200 u.")
    assert base["usuario"] == "Lucía" and base["motivo"] == "Más demanda que el año pasado"
    assert por_campo["tope_precio_unitario"]["texto_nuevo"] == "$ 160"
    assert len({c["lote"] for c in hist}) == 1

    r = client.post(f"/reglas/resma_a4/historial/{base['id']}/revertir", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["reglas"]["stock_base"] is None
    assert _repo(client, "resma_a4")["cantidad"] == 150  # vuelve a la cuenta de siempre
    hist = client.get("/reglas/resma_a4/historial").json()
    reversion = hist[0]
    assert reversion["revierte"] == base["id"] and reversion["texto_nuevo"] == "sin definir"
    assert next(c for c in hist if c["id"] == base["id"])["revertido_por"] == reversion["id"]
    assert client.post(f"/reglas/resma_a4/historial/{base['id']}/revertir", headers=h).status_code == 409


def test_no_revierte_un_cambio_pisado_por_otro(client):
    h = _admin(client)
    client.patch("/reglas/resma_a4", json={"stock_minimo": 50, "motivo": "uno"}, headers=h)
    primero = client.get("/reglas/resma_a4/historial").json()[0]
    client.patch("/reglas/resma_a4", json={"stock_minimo": 60, "motivo": "dos"}, headers=h)
    r = client.post(f"/reglas/resma_a4/historial/{primero['id']}/revertir", headers=h)
    assert r.status_code == 409 and "más reciente" in r.json()["error"]
    assert client.post("/reglas/resma_a4/historial/cr_nada/revertir", headers=h).status_code == 404


# ---------------------------------------------------------------- vista previa
def test_vista_previa_no_guarda(client):
    r = client.post("/reglas/resma_a4/vista-previa", json={"stock_minimo": 60, "stock_base": 300, "tope_precio_unitario": 200})
    assert r.status_code == 200, r.text
    vp = r.json()
    assert vp["valido"] and vp["dispara_compra"] and vp["cantidad"] == 290 and vp["motivo"] == "stock_base"
    assert vp["aprobacion"] == "automatica" and vp["bajo_tope"] is None
    assert "se dispara una compra automática de 290 u." in vp["texto"]
    assert "Todavía no hay cotizaciones para comparar con el tope de $ 200" in vp["texto"]
    assert {c["campo"] for c in vp["cambios"]} == {"stock_minimo", "stock_base", "tope_precio_unitario"}
    assert client.get("/reglas/resma_a4").json()["reglas"]["stock_minimo"] == 40  # nada guardado
    apagada = client.post("/reglas/resma_a4/vista-previa", json={"compra_automatica": False}).json()
    assert apagada["aprobacion"] == "requiere_aprobacion" and "compra automática está apagada" in apagada["texto"]
    invalida = client.post("/reglas/resma_a4/vista-previa", json={"stock_base": 10}).json()
    assert not invalida["valido"] and "stock_base" in invalida["errores"]
    notebook = client.post("/reglas/notebook/vista-previa", json={}).json()
    assert notebook["aplica_cierre"] is False and "equipamiento" in notebook["texto"]


def test_vista_previa_compara_el_mejor_precio_con_el_tope(client):
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 30
    while time.time() < limite:
        mensajes = client.get(f"/pedidos/{PEDIDO}/mensajes").json()
        if len(mensajes) == 6 and all(m["estado"] in ("extraido", "error") for m in mensajes):
            break
        time.sleep(0.1)
    ctx = client.get("/reglas/resma_a4").json()["contexto"]
    mejor = ctx["mejor_precio"]
    assert mejor and mejor["evidencia"] and ctx["precios"][0] == mejor
    alto = client.post("/reglas/resma_a4/vista-previa", json={"tope_precio_unitario": mejor["precio_sin_iva_uyu"] + 1}).json()
    assert alto["bajo_tope"] is True and "está bajo el tope" in alto["texto"]
    bajo = client.post("/reglas/resma_a4/vista-previa", json={"tope_precio_unitario": 1}).json()
    assert bajo["bajo_tope"] is False and bajo["aprobacion"] == "requiere_aprobacion"
    usd = client.post("/reglas/resma_a4/vista-previa", json={"tope_precio_unitario": 10, "moneda_tope": "USD"}).json()
    assert usd["tope_unitario_uyu"] == 400  # 10 × 40,00


# ---------------------------------------------------------------- agente: tope de precio unitario
def test_el_agente_respeta_el_tope_de_precio_unitario(client):
    h = _admin(client)
    item = inventario.item("resma_a4", 1)
    assert agente._aprobacion(item, Decimal(1000), Decimal(150))[0] == "automatica"  # sin tope unitario: como hoy
    client.patch("/reglas/resma_a4", json={"tope_precio_unitario": 140, "motivo": "x"}, headers=h)
    aprobacion, motivo = agente._aprobacion(item, Decimal(1000), Decimal(150))
    assert aprobacion == "supera_tope" and "tope de precio unitario de $ 140,00" in motivo
    aprobacion, motivo = agente._aprobacion(item, Decimal(1000), Decimal(139.5))
    assert aprobacion == "automatica" and "no supera el tope unitario" in motivo


def test_la_orden_no_sale_sola_si_supera_el_tope_unitario(client):
    h = _admin(client)
    opciones = {"esperar_confirmacion": False, "llamar_si_no_responde": False, "negociar": False}
    corrida = client.post("/agente", json=opciones).json()
    limite = time.time() + 20
    while client.get(f"/agente/{corrida['id']}").json()["estado"] != "esperando_revision":
        assert time.time() < limite
        time.sleep(0.05)
    corrida = client.get(f"/agente/{corrida['id']}").json()
    client.patch("/reglas/desinfectante", json={"tope_precio_unitario": 1, "motivo": "Prueba"}, headers=h)
    client.post(f"/cotizaciones/{corrida['revision'][0]['cotizacion_id']}/confirmar", json={"incluye_iva": True})
    while client.get(f"/agente/{corrida['id']}").json()["estado"] != "esperando_aprobacion":
        assert time.time() < limite
        time.sleep(0.05)
    corrida = client.get(f"/agente/{corrida['id']}").json()
    papelera = next(o for o in corrida["ordenes"] if o["proveedor_id"] == "papelera_del_sur")
    assert papelera["estado"] == "esperando_aprobacion"
    linea = next(l for l in papelera["lineas"] if l["producto_id"] == "desinfectante")
    assert linea["aprobacion"] == "supera_tope" and "tope de precio unitario" in linea["motivo"]


# ---------------------------------------------------------------- configuración (RF-20)
def test_configuracion_por_defecto_y_cambios(client):
    cfg = client.get("/configuracion").json()
    assert (cfg["tipo_cambio_usd"], cfg["iva"], cfg["vigencia_dias_default"], cfg["moneda_base"]) == (40.0, 0.22, 30, "UYU")
    h = _admin(client)
    r = client.patch("/configuracion", json={"tipo_cambio_usd": 41.5, "vigencia_dias_default": 15, "motivo": "BCU del día"}, headers=h)
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["tipo_cambio_usd"] == 41.5 and cfg["fecha_tipo_cambio"] and cfg["actualizado_por"] == "Lucía"
    assert pipeline.config_vigente()["tipo_cambio_usd"] == 41.5
    assert client.get(f"/pedidos/{PEDIDO}").json()["tipo_cambio_usd"] == 41.5
    hist = client.get("/configuracion/historial").json()
    assert {c["campo"] for c in hist} == {"tipo_cambio_usd", "fecha_tipo_cambio", "vigencia_dias_default"}
    assert next(c for c in hist if c["campo"] == "tipo_cambio_usd")["texto_nuevo"] == "41,50"
    for malo in ({"iva": 22}, {"tipo_cambio_usd": 0}, {"vigencia_dias_default": 0}, {"moneda_base": "USD"}, {"iva": None}):
        assert client.patch("/configuracion", json=malo, headers=h).status_code == 422, malo


def test_el_pipeline_usa_la_configuracion_guardada(client):
    h = _admin(client)
    client.patch("/configuracion", json={"tipo_cambio_usd": 50, "vigencia_dias_default": 20}, headers=h)
    client.post(f"/pedidos/{PEDIDO}/cotizar")
    limite = time.time() + 30
    while time.time() < limite:
        cots = {c["proveedor_id"]: c for c in client.get(f"/pedidos/{PEDIDO}/cotizaciones").json()}
        if len(cots) == 6:
            break
        time.sleep(0.1)
    tecno = cots["tecnoimport"]  # cotiza en USD y dice validez 5 días
    assert tecno["tipo_cambio_usd"] == 50 and tecno["validez_dias"] == 5
    assert any("× 50" in (i["conversion_aplicada"] or "") for i in tecno["items"])
    ofisillas = cots["ofisillas"]  # no indica validez: toma la de configuración
    assert ofisillas["validez_dias"] == 20
    assert "Vigencia: 20 días por defecto (el proveedor no la indicó)." in ofisillas["observaciones"]
