"""Ingreso con usuario y contraseña (RF-21) y permisos solo sobre reglas y configuración (PRD 1.4 §3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app

CONTRASENA = "abasto2026"  # la de data/usuarios_demo.json (AGENTS.md)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        c.post("/reset")
        yield c
        c.post("/reset")


def _token(client: TestClient, usuario: str = "lucia@tecnova.com.uy") -> str:
    r = client.post("/auth/login", json={"usuario": usuario, "contrasena": CONTRASENA})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_hash_pbkdf2():
    guardado = auth.hash_contrasena("secreta")
    assert guardado.startswith("pbkdf2_sha256$") and "secreta" not in guardado
    assert auth.verificar_contrasena("secreta", guardado)
    assert not auth.verificar_contrasena("otra", guardado)
    assert not auth.verificar_contrasena("secreta", "cualquier cosa")


def test_ingresar_con_email_o_usuario(client):
    r = client.post("/auth/login", json={"usuario": "lucia@tecnova.com.uy", "contrasena": CONTRASENA})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["usuario"] == {
        "id": "u_lucia",
        "nombre": "Lucía",
        "email": "lucia@tecnova.com.uy",
        "rol": "administrador",
        "cliente_interno": "personal",
    }
    assert "contrasena_hash" not in r.text
    yo = client.get("/auth/yo", headers=_h(cuerpo["token"]))
    assert yo.status_code == 200 and yo.json()["id"] == "u_lucia"
    # el nombre de usuario corto también sirve, sin importar mayúsculas
    assert client.post("/auth/login", json={"usuario": "Martin", "contrasena": CONTRASENA}).json()["usuario"]["rol"] == "consulta"


def test_credenciales_incorrectas(client):
    r = client.post("/auth/login", json={"usuario": "lucia", "contrasena": "mal"})
    assert r.status_code == 401 and r.json()["error"] == "Usuario o contraseña incorrectos"
    assert client.post("/auth/login", json={"usuario": "nadie", "contrasena": CONTRASENA}).status_code == 401


def test_yo_sin_token_o_con_token_trucho(client):
    assert client.get("/auth/yo").status_code == 401
    assert client.get("/auth/yo", headers=_h("abc.def")).status_code == 401
    token = _token(client)
    carga, firma = token.split(".")
    assert client.get("/auth/yo", headers=_h(carga + "x." + firma)).status_code == 401


def test_el_token_vence(client):
    viejo = auth.emitir_token("u_lucia", ahora=0)
    r = client.get("/auth/yo", headers=_h(viejo))
    assert r.status_code == 401 and "venció" in r.json()["error"]


def test_salir_invalida_el_token(client):
    token = _token(client)
    assert client.post("/auth/logout", headers=_h(token)).status_code == 204
    assert client.get("/auth/yo", headers=_h(token)).status_code == 401


def test_el_token_sobrevive_al_reset_de_la_demo(client):
    token = _token(client)
    client.post("/reset")
    assert client.get("/auth/yo", headers=_h(token)).status_code == 200


def test_registro_no_disponible(client):
    r = client.post("/auth/registro", json={"email": "x@y.com"})
    assert r.status_code == 501 and r.json()["error"] == "El registro todavía no está disponible"


def test_permisos_solo_en_reglas_y_configuracion(client):
    cambio = {"stock_minimo": 45, "motivo": "prueba"}
    assert client.patch("/reglas/resma_a4", json=cambio).status_code == 401
    consulta = _token(client, "sofia")
    r = client.patch("/reglas/resma_a4", json=cambio, headers=_h(consulta))
    assert r.status_code == 403 and "administrador" in r.json()["error"]
    assert client.patch("/configuracion", json={"iva": 0.2}, headers=_h(consulta)).status_code == 403
    assert client.post("/reglas/resma_a4/historial/x/revertir", headers=_h(consulta)).status_code == 403
    # leer sí pueden todos, y el resto de la API sigue abierta (demo guiada y tests)
    assert client.get("/reglas/resma_a4").status_code == 200
    assert client.get("/configuracion").status_code == 200
    assert client.get("/inventario").status_code == 200
    admin = _token(client)
    assert client.patch("/reglas/resma_a4", json=cambio, headers=_h(admin)).status_code == 200


def test_lista_de_usuarios(client):
    assert client.get("/auth/usuarios").status_code == 401
    token = _token(client)
    usuarios = client.get("/auth/usuarios", headers=_h(token)).json()
    assert [(u["nombre"], u["rol"], u["cliente_interno"]) for u in usuarios] == [
        ("Lucía", "administrador", "personal"),
        ("Martín", "consulta", "ventas"),
        ("Sofía", "consulta", "personal"),
    ]
    assert usuarios[0]["ultimo_ingreso"] and usuarios[1]["ultimo_ingreso"] is None
    assert all("contrasena_hash" not in u for u in usuarios)
