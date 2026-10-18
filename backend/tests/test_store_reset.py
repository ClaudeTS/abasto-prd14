"""Reinicio selectivo (store.reset): las colecciones registradas como persistentes sobreviven a
"Reiniciar demo"; reset(total=True) borra todo. En archivos JSON siempre; en Postgres si hay base de prueba
(ABASTO_TEST_DATABASE_URL, ver conftest.py: borra todo lo que tenga)."""

import dataclasses

import pytest

from app import config, store


@pytest.fixture(params=["json", "postgres"])
def modo(request, monkeypatch):
    if request.param == "json":
        monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, database_url=""))
    elif not config.settings.database_url:
        pytest.skip("sin base de prueba (ABASTO_TEST_DATABASE_URL)")
    monkeypatch.setattr(store, "_persistentes", set())
    store.reset(total=True)
    yield request.param
    store.reset(total=True)


def _guardar_x_e_y() -> None:
    store.guardar_dict("x", "uno", {"valor": 1})
    store.guardar_dict("y", "uno", {"valor": 2})


def test_reset_conserva_las_persistentes(modo):
    store.registrar_persistente("x")
    assert store.colecciones_persistentes() == frozenset({"x"})
    _guardar_x_e_y()

    store.reset()

    assert store.obtener_dict("x", "uno") == {"valor": 1}
    assert store.obtener_dict("y", "uno") is None
    store.guardar_dict("y", "dos", {"valor": 3})  # después del reinicio se sigue escribiendo
    assert store.valores("y") == [{"valor": 3}]


def test_reset_total_borra_todo(modo):
    store.registrar_persistente("x")
    _guardar_x_e_y()

    store.reset(total=True)

    assert store.valores("x") == []
    assert store.valores("y") == []
    assert store.colecciones_persistentes() == frozenset({"x"})  # el registro no se pierde


def test_reset_sin_persistentes_borra_todo_como_antes(modo):
    _guardar_x_e_y()
    store.reset(borrar_cache=False)  # la firma de siempre
    assert store.valores("x") == [] and store.valores("y") == []


def test_reset_borra_los_archivos(modo):
    store.registrar_persistente("x")
    ruta = config.settings.archivos_dir / "presupuesto.pdf"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"%PDF-1.4")
    store.subir_archivo(ruta.name)

    store.reset()

    assert not store.asegurar_archivo(ruta.name)


def test_reset_conserva_el_cache(modo):
    store.registrar_persistente("x")
    store.cache_guardar("prueba_reset", {"ok": True})
    store.reset()
    store.reset(total=True)
    assert store.cache_leer("prueba_reset") == {"ok": True}
    store.reset(borrar_cache=True)
    assert store.cache_leer("prueba_reset") is None
