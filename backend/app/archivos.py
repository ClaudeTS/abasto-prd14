"""Generación de archivos "realistas" para el simulador de proveedores.

- PDF de presupuesto formal a partir de un subconjunto simple de HTML (reportlab).
- Foto de presupuesto escrito a mano a partir de texto plano (Pillow).
- Utilidades de lectura: texto de un PDF (pdfplumber) y HTML → texto plano.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import pdfplumber
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --------------------------------------------------------------------------- #
# Parseo del subconjunto de HTML
# --------------------------------------------------------------------------- #

_BLOQUES = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table"}
_ENCABEZADOS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_CELDAS = {"td", "th"}
_NEGRITA = {"b", "strong"}
_ITALICA = {"i", "em"}
_NUMERO = re.compile(r"^[\s$€USDU\$]*[-+]?[\d.,]+\s*%?$")


@dataclass
class _Bloque:
    """Bloque de contenido: encabezado, párrafo o tabla."""

    tipo: str  # "h1".."h6" | "p" | "table"
    runs: list[tuple[str, bool, bool]] = field(default_factory=list)
    filas: list[list[tuple[str, bool]]] = field(default_factory=list)


class _ParserPresupuesto(HTMLParser):
    """Convierte HTML simple en una lista de bloques."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bloques: list[_Bloque] = []
        self._actual: _Bloque | None = None
        self._tabla: _Bloque | None = None
        self._fila: list[tuple[str, bool]] | None = None
        self._celda: list[str] | None = None
        self._celda_th = False
        self._negrita = 0
        self._italica = 0

    def _cerrar_actual(self) -> None:
        if (
            self._actual is not None
            and "".join(t for t, *_ in self._actual.runs).strip()
        ):
            self.bloques.append(self._actual)
        self._actual = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _NEGRITA:
            self._negrita += 1
        elif tag in _ITALICA:
            self._italica += 1
        elif tag == "br":
            self.handle_data("\n")
        elif tag == "table":
            self._cerrar_actual()
            self._tabla = _Bloque("table")
        elif tag == "tr" and self._tabla is not None:
            self._fila = []
        elif tag in _CELDAS and self._fila is not None:
            self._celda = []
            self._celda_th = tag == "th"
        elif tag in _BLOQUES and self._tabla is None:
            self._cerrar_actual()
            self._actual = _Bloque(tag if tag in _ENCABEZADOS else "p")
            if tag == "li":
                self._actual.runs.append(("• ", False, False))

    def handle_endtag(self, tag: str) -> None:
        if tag in _NEGRITA:
            self._negrita = max(0, self._negrita - 1)
        elif tag in _ITALICA:
            self._italica = max(0, self._italica - 1)
        elif tag in _CELDAS and self._celda is not None and self._fila is not None:
            texto = " ".join("".join(self._celda).split())
            self._fila.append((texto, self._celda_th))
            self._celda = None
        elif tag == "tr" and self._fila is not None and self._tabla is not None:
            if self._fila:
                self._tabla.filas.append(self._fila)
            self._fila = None
        elif tag == "table" and self._tabla is not None:
            if self._tabla.filas:
                self.bloques.append(self._tabla)
            self._tabla = None
        elif tag in _BLOQUES and self._tabla is None:
            self._cerrar_actual()

    def handle_data(self, data: str) -> None:
        if self._celda is not None:
            self._celda.append(data)
            return
        if self._tabla is not None:
            return  # texto suelto entre celdas: se ignora
        if self._actual is None:
            if not data.strip():
                return
            self._actual = _Bloque("p")
        self._actual.runs.append((data, self._negrita > 0, self._italica > 0))

    def close(self) -> None:
        super().close()
        self._cerrar_actual()


def _parsear(html: str) -> list[_Bloque]:
    parser = _ParserPresupuesto()
    parser.feed(html)
    parser.close()
    return parser.bloques


# --------------------------------------------------------------------------- #
# HTML → texto
# --------------------------------------------------------------------------- #


class _ParserTexto(HTMLParser):
    """Extrae texto: bloques y filas → salto de línea; celdas → espacio."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" or tag in _BLOQUES:
            self.partes.append("\n")
        elif tag in _CELDAS:
            self.partes.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOQUES:
            self.partes.append("\n")
        elif tag in _CELDAS:
            self.partes.append(" ")

    def handle_data(self, data: str) -> None:
        self.partes.append(data)


def html_a_texto(html: str) -> str:
    """Convierte HTML a texto plano con whitespace colapsado por línea."""
    parser = _ParserTexto()
    parser.feed(html)
    parser.close()
    lineas = (" ".join(linea.split()) for linea in "".join(parser.partes).splitlines())
    return "\n".join(linea for linea in lineas if linea)


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

_COLOR_MARCA = colors.HexColor("#1f3b5c")
_COLOR_TEXTO = colors.HexColor("#222222")
_COLOR_SOMBRA = colors.HexColor("#e3e9f0")
_COLOR_BORDE = colors.HexColor("#8a99ab")
_COLOR_SUAVE = colors.HexColor("#6b7785")

_ESTILOS = {
    "membrete": ParagraphStyle(
        "membrete",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=_COLOR_MARCA,
        spaceAfter=2,
    ),
    "h": ParagraphStyle(
        "h",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=_COLOR_MARCA,
        spaceBefore=8,
        spaceAfter=4,
    ),
    "p": ParagraphStyle(
        "p",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=_COLOR_TEXTO,
        spaceAfter=6,
    ),
    "celda": ParagraphStyle(
        "celda", fontName="Helvetica", fontSize=9.5, leading=12, alignment=TA_LEFT
    ),
    "celda_num": ParagraphStyle(
        "celda_num", fontName="Helvetica", fontSize=9.5, leading=12, alignment=TA_RIGHT
    ),
    "th": ParagraphStyle(
        "th",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=_COLOR_MARCA,
        alignment=TA_LEFT,
    ),
    "th_num": ParagraphStyle(
        "th_num",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=_COLOR_MARCA,
        alignment=TA_RIGHT,
    ),
}


def _runs_a_markup(runs: list[tuple[str, bool, bool]]) -> str:
    """Pasa runs (texto, negrita, itálica) al mini-markup de reportlab."""
    partes: list[str] = []
    for texto, negrita, italica in runs:
        t = escape(re.sub(r"[ \t\r\f\v]+", " ", texto), quote=False)
        t = t.replace("\n", "<br/>")
        if italica:
            t = f"<i>{t}</i>"
        if negrita:
            t = f"<b>{t}</b>"
        partes.append(t)
    return "".join(partes).strip()


def _es_numero(texto: str) -> bool:
    return bool(texto) and bool(_NUMERO.match(texto))


def _anchos_columnas(filas: list[list[tuple[str, bool]]], ancho: float) -> list[float]:
    """Anchos que no parten palabras: mínimo = palabra más larga, resto proporcional."""
    relleno = 14.0
    minimos: list[float] = []
    preferidos: list[float] = []
    for c in range(len(filas[0])):
        min_c = pref_c = 20.0
        for fila in filas:
            texto, th = fila[c]
            fuente, tam = ("Helvetica-Bold", 9) if th else ("Helvetica", 9.5)
            palabras = texto.split() or [""]
            min_c = max(min_c, max(stringWidth(p, fuente, tam) for p in palabras))
            pref_c = max(pref_c, stringWidth(texto, fuente, tam))
        minimos.append(min_c + relleno)
        preferidos.append(pref_c + relleno)

    if sum(preferidos) <= ancho:
        extra = ancho - sum(preferidos)
        return [p + extra * p / sum(preferidos) for p in preferidos]
    if sum(minimos) >= ancho:
        return [ancho * m / sum(minimos) for m in minimos]
    sobrante = ancho - sum(minimos)
    holgura = [p - m for p, m in zip(preferidos, minimos)]
    return [m + sobrante * h / sum(holgura) for m, h in zip(minimos, holgura)]


def _tabla_pdf(filas: list[list[tuple[str, bool]]], ancho: float) -> Table:
    """Arma una tabla con bordes, encabezado sombreado y números a la derecha."""
    n_cols = max(len(f) for f in filas)
    filas = [f + [("", False)] * (n_cols - len(f)) for f in filas]
    cuerpo = [f for f in filas if not all(th for _, th in f)]

    # Columna numérica = todas sus celdas de cuerpo no vacías son números.
    numericas = [
        bool(cuerpo)
        and all(_es_numero(f[c][0]) for f in cuerpo if f[c][0])
        and any(f[c][0] for f in cuerpo)
        for c in range(n_cols)
    ]

    anchos = _anchos_columnas(filas, ancho)

    datos = []
    for fila in filas:
        datos.append(
            [
                Paragraph(
                    escape(texto, quote=False),
                    _ESTILOS[
                        ("th" if th else "celda") + ("_num" if numericas[c] else "")
                    ],
                )
                for c, (texto, th) in enumerate(fila)
            ]
        )

    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.6, _COLOR_BORDE),
        ("BOX", (0, 0), (-1, -1), 1.0, _COLOR_MARCA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i, fila in enumerate(filas):
        if all(th for _, th in fila):
            estilo.append(("BACKGROUND", (0, i), (-1, i), _COLOR_SOMBRA))
    tabla = Table(datos, colWidths=anchos, repeatRows=1 if filas[0][0][1] else 0)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _pie_de_pagina(canvas, doc) -> None:  # noqa: ANN001 (firma de reportlab)
    canvas.saveState()
    ancho, _ = A4
    canvas.setStrokeColor(_COLOR_BORDE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 15 * mm, ancho - doc.rightMargin, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_COLOR_SUAVE)
    canvas.drawRightString(ancho - doc.rightMargin, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


def generar_pdf_presupuesto(html: str, destino: Path) -> Path:
    """Renderiza el HTML de un presupuesto a un PDF A4 con texto seleccionable."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    bloques = _parsear(html)

    doc = SimpleDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        title=next(
            (_runs_a_markup(b.runs) for b in bloques if b.tipo in _ENCABEZADOS),
            "Presupuesto",
        ),
    )
    historia: list = []
    hubo_membrete = False
    for i, bloque in enumerate(bloques):
        if bloque.tipo == "table":
            historia += [
                Spacer(1, 4),
                _tabla_pdf(bloque.filas, doc.width),
                Spacer(1, 10),
            ]
        elif bloque.tipo in _ENCABEZADOS and not hubo_membrete and i == 0:
            hubo_membrete = True
            historia += [
                Paragraph(_runs_a_markup(bloque.runs), _ESTILOS["membrete"]),
                HRFlowable(width="100%", thickness=2, color=_COLOR_MARCA, spaceAfter=8),
            ]
        elif bloque.tipo in _ENCABEZADOS:
            historia.append(Paragraph(_runs_a_markup(bloque.runs), _ESTILOS["h"]))
        else:
            historia.append(Paragraph(_runs_a_markup(bloque.runs), _ESTILOS["p"]))

    if not historia:
        historia.append(Paragraph(" ", _ESTILOS["p"]))
    doc.build(historia, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    return destino


def extraer_texto_pdf(ruta: Path) -> str:
    """Extrae el texto de todas las páginas de un PDF con pdfplumber."""
    with pdfplumber.open(str(ruta)) as pdf:
        return "\n".join(pagina.extract_text() or "" for pagina in pdf.pages)


# --------------------------------------------------------------------------- #
# Foto de presupuesto manuscrito
# --------------------------------------------------------------------------- #

_DIR_FUENTES = [
    Path(__file__).resolve().parent / "assets" / "fonts",
    Path(__file__).resolve().parents[2] / "data" / "fonts",
]
_FUENTES_MANUSCRITAS = ["Caveat*.ttf", "caveat*.woff", "PatrickHand*.ttf"]
_FUENTES_SISTEMA = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "DejaVuSans-Oblique.ttf",
]

_ANCHO_PAPEL = 1000
_MARGEN_X = 90
_MARGEN_SUP = 110
_MARGEN_INF = 90
_COLOR_PAPEL = (0xF4, 0xEC, 0xD8)
_COLOR_TINTA = (0x1C, 0x2A, 0x5E)
_COLOR_RENGLON = (0xA9, 0xBC, 0xD0)
_COLOR_MARGEN = (0xD9, 0x9A, 0x96)
_COLOR_MESA = (0x6E, 0x5B, 0x48)


@lru_cache(maxsize=8)
def _cargar_fuente(
    tam_manuscrita: int, tam_fallback: int
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, bool]:
    """Devuelve (fuente, es_manuscrita). Cae a DejaVu Oblique o a la default."""
    for directorio in _DIR_FUENTES:
        for patron in _FUENTES_MANUSCRITAS:
            for ruta in sorted(directorio.glob(patron)):
                try:
                    return ImageFont.truetype(str(ruta), tam_manuscrita), True
                except OSError:
                    continue
    for ruta in _FUENTES_SISTEMA:
        try:
            return ImageFont.truetype(ruta, tam_fallback), False
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam_fallback), False
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default(), False


def _ancho_texto(fuente: ImageFont.ImageFont, texto: str) -> float:
    return float(fuente.getlength(texto))


def _envolver(texto: str, fuente: ImageFont.ImageFont, ancho_max: float) -> list[str]:
    """Parte cada línea en renglones que entren en el ancho disponible."""
    renglones: list[str] = []
    for linea in texto.splitlines():
        palabras = linea.split()
        if not palabras:
            renglones.append("")
            continue
        actual = palabras[0]
        for palabra in palabras[1:]:
            candidato = f"{actual} {palabra}"
            if _ancho_texto(fuente, candidato) <= ancho_max:
                actual = candidato
            else:
                renglones.append(actual)
                actual = palabra
        renglones.append(actual)
    return renglones


def _papel(ancho: int, alto: int, rng: random.Random) -> Image.Image:
    """Fondo de papel con variación de tono a gran escala y grano fino."""
    base = Image.new("RGB", (ancho, alto), _COLOR_PAPEL)
    # Manchas suaves: ruido de baja resolución escalado.
    chico = Image.frombytes("L", (12, 16), rng.randbytes(12 * 16)).resize(
        (ancho, alto), Image.BICUBIC
    )
    sombra = Image.new("RGB", (ancho, alto), (0xD8, 0xCB, 0xAE))
    base = Image.composite(sombra, base, chico.point(lambda v: v * 50 // 255))
    # Grano fino.
    grano = (
        Image.frombytes("L", (ancho, alto), rng.randbytes(ancho * alto))
        .filter(ImageFilter.GaussianBlur(0.6))
        .point(lambda v: 128 + (v - 128) * 3 // 4)
    )
    gris = Image.merge("RGB", (grano, grano, grano))
    return Image.blend(base, gris, 0.06)


def _renglones(img: Image.Image, interlineado: int, y0: int) -> None:
    """Dibuja renglones tenues y la línea de margen."""
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    ancho, alto = img.size
    y = y0
    while y < alto - 30:
        d.line([(0, y), (ancho, y)], fill=(*_COLOR_RENGLON, 110), width=2)
        y += interlineado
    d.line(
        [(_MARGEN_X - 22, 0), (_MARGEN_X - 22, alto)],
        fill=(*_COLOR_MARGEN, 120),
        width=2,
    )
    img.paste(Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB"))


def _escribir(
    img: Image.Image,
    renglones: list[str],
    fuente: ImageFont.ImageFont,
    interlineado: int,
    y0: int,
    rng: random.Random,
) -> None:
    """Escribe a mano: jitter por letra, deriva de la línea base y tinta irregular."""
    capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
    tam = int(getattr(fuente, "size", 24))
    for n, renglon in enumerate(renglones):
        # La letra se apoya sobre el renglón n (línea base unos px arriba).
        base_y = y0 + n * interlineado - 6 + rng.uniform(-2, 1)
        x = _MARGEN_X + rng.uniform(-6, 10)
        pendiente = rng.uniform(-0.012, 0.012)
        x_inicio = x
        for ch in renglon:
            if ch == " ":
                x += _ancho_texto(fuente, " ") * rng.uniform(0.9, 1.4)
                continue
            dy = (x - x_inicio) * pendiente + rng.uniform(-1.6, 1.6)
            alfa = int(rng.uniform(190, 250))
            ancho_ch = _ancho_texto(fuente, ch)
            # Cada letra en su propio "tile", girada unos grados.
            lado = int(2 * tam + ancho_ch) + 8
            pad = lado // 4
            tile = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
            if isinstance(fuente, ImageFont.FreeTypeFont):
                pos, anchor = (pad, lado // 2), "ls"
            else:  # fuente bitmap: no soporta anchor
                pos, anchor = (pad, lado // 2 - tam), None
            ImageDraw.Draw(tile).text(
                pos, ch, font=fuente, fill=(*_COLOR_TINTA, alfa), anchor=anchor
            )
            tile = tile.rotate(rng.uniform(-5, 5), resample=Image.BICUBIC)
            capa.alpha_composite(
                tile,
                (max(0, int(x - pad)), max(0, int(base_y + dy - lado // 2))),
            )
            x += ancho_ch + rng.uniform(-0.8, 1.2)
    # Leve corrimiento de tinta.
    capa = capa.filter(ImageFilter.GaussianBlur(0.5))
    img.paste(Image.alpha_composite(img.convert("RGBA"), capa).convert("RGB"))


def _vineta(img: Image.Image) -> Image.Image:
    """Oscurece levemente los bordes, como una foto de celular."""
    ancho, alto = img.size
    mascara = Image.radial_gradient("L").resize((ancho, alto), Image.BICUBIC)
    mascara = mascara.point(lambda v: max(0, v - 120) * 70 // 135)
    oscuro = Image.new("RGB", img.size, (0, 0, 0))
    return Image.composite(oscuro, img, mascara)


def generar_foto_presupuesto(texto: str, destino: Path, *, seed: int = 7) -> Path:
    """Genera un JPEG de un presupuesto escrito a mano en papel (determinístico)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    fuente, manuscrita = _cargar_fuente(54, 36)
    interlineado = 64 if manuscrita else 58
    renglones = _envolver(texto, fuente, _ANCHO_PAPEL - _MARGEN_X - 70)
    alto = max(
        int(_ANCHO_PAPEL * 0.62),
        _MARGEN_SUP + interlineado * max(len(renglones), 1) + _MARGEN_INF,
    )

    papel = _papel(_ANCHO_PAPEL, alto, rng)
    _renglones(papel, interlineado, _MARGEN_SUP)
    _escribir(papel, renglones, fuente, interlineado, _MARGEN_SUP, rng)

    # Foto: papel apoyado sobre una mesa, levemente girado.
    borde = 40
    mesa = Image.new("RGB", (_ANCHO_PAPEL + 2 * borde, alto + 2 * borde), _COLOR_MESA)
    sombra = Image.new("L", mesa.size, 0)
    ImageDraw.Draw(sombra).rectangle(
        [borde + 6, borde + 8, borde + _ANCHO_PAPEL + 6, borde + alto + 8], fill=150
    )
    mesa.paste((0x3A, 0x2E, 0x24), mask=sombra.filter(ImageFilter.GaussianBlur(8)))
    mesa.paste(papel, (borde, borde))
    angulo = 2.0 * (1 if rng.random() < 0.5 else -1)
    foto = mesa.rotate(
        angulo, resample=Image.BICUBIC, expand=False, fillcolor=_COLOR_MESA
    )
    recorte = int(math.ceil(alto * math.sin(math.radians(abs(angulo))) / 2)) + 4
    foto = foto.crop((recorte, recorte, foto.width - recorte, foto.height - recorte))
    foto = _vineta(foto).filter(ImageFilter.GaussianBlur(0.4))

    foto.save(destino, format="JPEG", quality=88, optimize=True)
    return destino
