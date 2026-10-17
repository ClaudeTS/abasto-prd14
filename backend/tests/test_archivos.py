"""Tests de generación de PDF / foto de presupuestos simulados."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from app.archivos import (
    extraer_texto_pdf,
    generar_foto_presupuesto,
    generar_pdf_presupuesto,
    html_a_texto,
)

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "respuestas_fijas.json"


@pytest.fixture(scope="module")
def respuestas() -> dict[str, str]:
    datos = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return {r["proveedor_id"]: r["contenido"] for r in datos["respuestas"]}


def _colapsar(texto: str) -> str:
    return " ".join(texto.split())


def test_pdf_tecnoimport_tiene_texto_real(
    respuestas: dict[str, str], tmp_path: Path
) -> None:
    destino = tmp_path / "sub" / "tecnoimport.pdf"
    ruta = generar_pdf_presupuesto(respuestas["tecnoimport"], destino)

    assert ruta == destino
    assert ruta.read_bytes()[:5] == b"%PDF-"
    texto = extraer_texto_pdf(ruta)
    assert len(texto) >= 50
    for esperado in ("TecnoImport", "780,00", "95,00", "más IVA", "5 días"):
        assert esperado in _colapsar(texto), esperado


def test_foto_rivera_jpeg_valido_y_deterministico(
    respuestas: dict[str, str], tmp_path: Path
) -> None:
    texto = respuestas["muebleria_rivera"]
    a = generar_foto_presupuesto(texto, tmp_path / "a" / "rivera.jpg", seed=7)
    b = generar_foto_presupuesto(texto, tmp_path / "b" / "rivera.jpg", seed=7)

    assert a == tmp_path / "a" / "rivera.jpg"
    with Image.open(a) as img_a, Image.open(b) as img_b:
        assert img_a.format == "JPEG"
        assert 900 <= img_a.width <= 1300
        assert img_a.tobytes() == img_b.tobytes()


def test_foto_cambia_con_otra_seed(respuestas: dict[str, str], tmp_path: Path) -> None:
    texto = respuestas["muebleria_rivera"]
    a = generar_foto_presupuesto(texto, tmp_path / "a.jpg", seed=7)
    b = generar_foto_presupuesto(texto, tmp_path / "b.jpg", seed=8)
    with Image.open(a) as img_a, Image.open(b) as img_b:
        assert img_a.tobytes() != img_b.tobytes()


def test_html_a_texto_tecnoimport(respuestas: dict[str, str]) -> None:
    texto = html_a_texto(respuestas["tecnoimport"])

    esperado = 'Notebook 15.6" Core i5 / 16 GB RAM / 512 GB SSD / Win 11 Pro 10 780,00'
    assert esperado in _colapsar(texto)
    # Una fila por línea, celdas separadas por un espacio.
    assert (
        '1 Notebook 15.6" Core i5 / 16 GB RAM / 512 GB SSD / Win 11 Pro 10 780,00 7.800,00'
        in texto.splitlines()
    )
    assert "<" not in texto


def test_html_a_texto_entidades_y_saltos() -> None:
    texto = html_a_texto("<h2>A &amp; B</h2><p>uno   dos<br>tres</p>")
    assert texto.splitlines() == ["A & B", "uno dos", "tres"]
