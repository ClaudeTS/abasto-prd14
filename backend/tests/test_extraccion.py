"""Capa 1 con un LLM falso: armado del pedido por canal y salida cruda según el contrato con C."""

import asyncio
from decimal import Decimal

import pytest

from app import extraccion, pipeline, store
from app.archivos import (
    extraer_texto_pdf,
    generar_foto_presupuesto,
    generar_pdf_presupuesto,
)
from app.extraccion import (
    EntradaInvalida,
    ExtraccionLLM,
    armar_contenido,
    evidencia_en_texto,
    extraer_crudo,
    html_a_texto,
)
from scripts.demo import normalizar

FIJAS = store.semilla("extracciones_fijas")["extracciones"]
RESPUESTAS = {
    r["proveedor_id"]: r for r in store.semilla("respuestas_fijas")["respuestas"]
}
ESPERADOS = store.semilla("pedido_demo")["resultado_esperado_demo"][
    "precios_normalizados_sin_iva"
]


class LLMFalso:
    """Reemplaza a pedir_json: devuelve lo que se le diga y guarda lo que recibió."""

    def __init__(self, salida: dict):
        self.salida = salida
        self.llamadas = []

    async def pedir_json(self, *, system, contenido, esquema, **_):
        self.llamadas.append({"system": system, "contenido": contenido})
        assert esquema is ExtraccionLLM
        return ExtraccionLLM.model_validate(self.salida)


@pytest.fixture
def llm(monkeypatch):
    def instalar(salida):
        falso = LLMFalso(salida)
        monkeypatch.setattr(extraccion, "pedir_json", falso.pedir_json)
        return falso

    return instalar


def extraer(proveedor_id, *, texto=None, imagen=None):
    respuesta = RESPUESTAS[proveedor_id]
    return asyncio.run(
        extraer_crudo(
            texto=texto,
            imagen=imagen,
            canal=respuesta["canal"],
            proveedor=pipeline.proveedores()[proveedor_id],
            catalogo=pipeline.catalogo(),
        )
    )


def texto_de(proveedor_id):
    contenido = RESPUESTAS[proveedor_id]["contenido"]
    return (
        html_a_texto(contenido)
        if RESPUESTAS[proveedor_id]["canal"] == "pdf"
        else contenido
    )


@pytest.mark.parametrize("proveedor_id", sorted(FIJAS))
def test_el_esquema_acepta_las_6_extracciones_de_referencia(proveedor_id):
    ExtraccionLLM.model_validate(FIJAS[proveedor_id])


@pytest.mark.parametrize("proveedor_id", sorted(FIJAS))
def test_salida_cruda_sin_convertir_y_c_la_normaliza_a_lo_esperado(llm, proveedor_id):
    llm(FIJAS[proveedor_id])
    crudo = extraer(proveedor_id, texto=texto_de(proveedor_id))

    assert (
        crudo == FIJAS[proveedor_id]
    )  # misma forma y mismos valores que la referencia de C
    cotizacion = normalizar(proveedor_id, crudo)
    obtenido = {i.producto_id: i.precio_unitario_sin_iva for i in cotizacion.items}
    esperado = {
        producto: Decimal(str(por_proveedor[proveedor_id]))
        for producto, por_proveedor in ESPERADOS.items()
        if proveedor_id in por_proveedor
    }
    assert obtenido == esperado
    assert cotizacion.estado in ("valida", "confirmada")


def test_el_prompt_lleva_catalogo_presentaciones_y_mensaje(llm):
    falso = llm(FIJAS["papelera_del_sur"])
    extraer("papelera_del_sur", texto=texto_de("papelera_del_sur"))

    [bloque] = falso.llamadas[0]["contenido"]
    assert bloque["type"] == "text"
    user = bloque["text"]
    assert "- resma_a4 → Resma papel A4 75 g (500 hojas) (unidad)" in user
    assert "- caja de 5 resmas" in user and "- bidón de 5 L" in user
    assert "Proveedor: Papelera del Sur" in user
    assert "Canal: whatsapp_audio" in user
    assert RESPUESTAS["papelera_del_sur"]["contenido"].strip() in user
    assert "{{" not in user and "{{" not in falso.llamadas[0]["system"]
    assert "NO conviertas unidades" in falso.llamadas[0]["system"]


def test_evidencia_que_no_esta_en_el_mensaje_se_marca_sin_bloquear(llm):
    salida = {**FIJAS["ofisillas"], "confianza": 1.4}
    salida["items"] = [{**salida["items"][0], "evidencia": "silla a $ 9.900"}]
    llm(salida)
    crudo = extraer("ofisillas", texto=texto_de("ofisillas"))

    assert crudo["campos_dudosos"] == ["evidencia:silla"]
    assert crudo["confianza"] == 1.0
    assert normalizar("ofisillas", crudo).estado == "valida"  # C no la bloquea por esto


@pytest.mark.parametrize("evidencia", ["   ", "...", "…", '""', " - "])
def test_evidencia_sin_contenido_queda_vacia_y_c_bloquea_el_precio(llm, evidencia):
    salida = {**FIJAS["ofisillas"]}
    salida["items"] = [{**salida["items"][0], "evidencia": evidencia}]
    llm(salida)
    crudo = extraer("ofisillas", texto=texto_de("ofisillas"))

    assert crudo["items"][0]["evidencia"] == ""
    assert "evidencia:silla" not in crudo["campos_dudosos"]
    cotizacion = normalizar("ofisillas", crudo)
    assert "precio:silla" in cotizacion.campos_dudosos
    assert cotizacion.estado != "valida"


def test_sin_texto_ni_archivo_no_llama_al_llm(llm):
    falso = llm(FIJAS["ofisillas"])
    with pytest.raises(EntradaInvalida, match="no trae texto ni archivo"):
        extraer("ofisillas", texto="   ")
    assert falso.llamadas == []


def test_html_del_pdf_se_lee_como_texto(llm):
    falso = llm(FIJAS["tecnoimport"])
    crudo = extraer("tecnoimport", texto=RESPUESTAS["tecnoimport"]["contenido"])

    user = falso.llamadas[0]["contenido"][0]["text"]
    assert "<table" not in user and "<td" not in user
    assert "evidencia:notebook" not in crudo["campos_dudosos"]


def test_pdf_con_texto_llega_como_texto_y_la_evidencia_esta(tmp_path, llm):
    pdf = generar_pdf_presupuesto(
        RESPUESTAS["tecnoimport"]["contenido"], tmp_path / "t.pdf"
    )
    falso = llm(FIJAS["tecnoimport"])
    texto = extraer_texto_pdf(pdf)  # lo que hace pipeline.obtener_texto
    crudo = extraer("tecnoimport", texto=texto)

    assert [b["type"] for b in falso.llamadas[0]["contenido"]] == ["text"]
    assert not [d for d in crudo["campos_dudosos"] if d.startswith("evidencia:")], texto


def test_en_la_tabla_del_pdf_la_evidencia_no_mezcla_filas(tmp_path):
    pdf = generar_pdf_presupuesto(
        RESPUESTAS["tecnoimport"]["contenido"], tmp_path / "t.pdf"
    )
    texto = extraer_texto_pdf(
        pdf
    )  # pdfplumber parte la fila de la notebook en 3 líneas
    for item in FIJAS["tecnoimport"]["items"]:
        assert evidencia_en_texto(item["evidencia"], texto, tabla=True), item
    # El tóner con el precio de la notebook (780,00): cada palabra está, pero en filas distintas.
    mezcla = "Tóner HP 85A original (CE285A) 8 780,00"
    assert not evidencia_en_texto(mezcla, texto, tabla=True)
    html = html_a_texto(RESPUESTAS["tecnoimport"]["contenido"])  # una fila por línea
    assert not evidencia_en_texto(mezcla, html)
    for item in FIJAS["tecnoimport"]["items"]:
        assert evidencia_en_texto(item["evidencia"], html), item


def test_pdf_escaneado_va_como_documento(tmp_path):
    pdf = generar_pdf_presupuesto("<h2>Presupuesto</h2>", tmp_path / "escaneado.pdf")
    bloques, fuente = armar_contenido(
        texto=None,
        imagen=pdf,
        canal="pdf",
        proveedor=pipeline.proveedores()["tecnoimport"],
        catalogo=pipeline.catalogo(),
    )
    assert bloques[0]["type"] == "document"
    assert bloques[0]["source"]["media_type"] == "application/pdf"
    assert "el PDF adjunto es el presupuesto" in bloques[1]["text"]
    assert fuente is None


def test_foto_va_como_imagen(tmp_path, llm):
    foto = generar_foto_presupuesto(
        RESPUESTAS["muebleria_rivera"]["contenido"], tmp_path / "foto.jpg"
    )
    falso = llm(FIJAS["muebleria_rivera"])
    crudo = extraer("muebleria_rivera", imagen=foto)

    imagen, texto = falso.llamadas[0]["contenido"]
    assert imagen["type"] == "image"
    assert imagen["source"]["media_type"] == "image/jpeg"
    assert "la imagen adjunta es el presupuesto" in texto["text"]
    assert crudo["campos_dudosos"] == FIJAS["muebleria_rivera"]["campos_dudosos"]


@pytest.mark.parametrize(
    "nombre, contenido, mensaje",
    [("lista.gif", b"GIF89a", "no soportado"), ("falta.jpg", None, "No existe")],
)
def test_archivos_invalidos(tmp_path, nombre, contenido, mensaje):
    ruta = tmp_path / nombre
    if contenido is not None:
        ruta.write_bytes(contenido)
    with pytest.raises(EntradaInvalida, match=mensaje):
        armar_contenido(
            texto=None,
            imagen=ruta,
            canal="foto",
            proveedor=pipeline.proveedores()["muebleria_rivera"],
            catalogo=pipeline.catalogo(),
        )


def test_evidencia_en_texto():
    texto = 'Silla ergonómica  mod. "Prime"\n$10.900 + IVA c/u'
    assert evidencia_en_texto("silla ergonómica mod. Prime", texto)
    assert evidencia_en_texto("Silla ergonómica ... $10.900 + IVA c/u", texto)
    assert not evidencia_en_texto("$9.900", texto)
    assert not evidencia_en_texto("  ", texto)
    # Palabras sueltas del mensaje solo valen en una tabla con filas; acá hay un solo monto.
    mezcla = "Prime silla $10.900"
    assert not evidencia_en_texto(mezcla, texto)
    assert not evidencia_en_texto(mezcla, texto, tabla=True)
    assert not evidencia_en_texto("silla $9.900", texto, tabla=True)


def test_en_una_tabla_las_palabras_valen_dentro_de_una_sola_fila():
    # Sin columna Ítem: ninguna fila empieza con un número.
    sin_item = "Silla ergonómica mod. Prime 15 10.900,00\nMesa de reunión 2 25.000,00"
    assert evidencia_en_texto("Silla ergonómica 15 10.900,00", sin_item, tabla=True)
    assert not evidencia_en_texto("Silla ergonómica 2 25.000,00", sin_item, tabla=True)
    # Descripción de 5 líneas, algunas empiezan con un número, partida arriba y abajo de la fila.
    larga = "\n".join(
        [
            "Ítem Descripción Cant. Precio Subtotal",
            'Notebook 15.6"',
            "Core i5",
            "1 10 780,00 7.800,00",
            "16 GB RAM",
            "512 GB SSD",
            "Win 11 Pro",
            "2 Tóner HP 85A original 8 95,00 760,00",
            "Precios en dólares, más IVA.",
        ]
    )
    notebook = 'Notebook 15.6" Core i5 16 GB RAM 512 GB SSD Win 11 Pro 10 780,00'
    assert evidencia_en_texto(notebook, larga, tabla=True)
    assert evidencia_en_texto("Tóner HP 85A original 8 95,00", larga, tabla=True)
    assert not evidencia_en_texto("Tóner HP 85A original 8 780,00", larga, tabla=True)
    assert not evidencia_en_texto("Notebook 15.6 Core i5 8 95,00", larga, tabla=True)
