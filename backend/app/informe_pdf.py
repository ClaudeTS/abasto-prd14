"""Informe del pedido en PDF (RF-18): los datos del pedido, el diálogo del agente o ambos.

Con reportlab, como los presupuestos simulados de app/archivos.py (mismos colores y tipografía). Las
fuentes base de reportlab (Helvetica) solo tienen los caracteres de cp1252: lo que no entra (emojis,
flechas) se reemplaza o se saca para que no salgan cuadraditos.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.historial_pedidos import DetallePedido, Mensaje, etiqueta_estado
from app.normalizacion import fmt

_MARCA = colors.HexColor("#1f3b5c")
_TEXTO = colors.HexColor("#222222")
_SOMBRA = colors.HexColor("#e3e9f0")
_BORDE = colors.HexColor("#8a99ab")
_SUAVE = colors.HexColor("#6b7785")
_FONDO_TRANSCRIPCION = colors.HexColor("#f4f6f8")

_E = {
    "titulo": ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=_MARCA),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=10, leading=14, textColor=_SUAVE, spaceAfter=4),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=_MARCA, spaceBefore=10, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=_MARCA, spaceBefore=8, spaceAfter=3),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, leading=13, textColor=_TEXTO, spaceAfter=4),
    "meta": ParagraphStyle("meta", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=_SUAVE),
    "nota": ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=8.5, leading=11, textColor=_SUAVE, spaceAfter=2),
    "turno": ParagraphStyle("turno", fontName="Helvetica", fontSize=9, leading=12, textColor=_TEXTO, leftIndent=8),
    "celda": ParagraphStyle("celda", fontName="Helvetica", fontSize=8.5, leading=11),
    "celda_num": ParagraphStyle("celda_num", fontName="Helvetica", fontSize=8.5, leading=11, alignment=TA_RIGHT),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=_MARCA),
    "aviso": ParagraphStyle(
        "aviso", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fffbeb"), borderPadding=4, spaceAfter=8,
    ),
}

CANALES = {
    "whatsapp": "WhatsApp",
    "email": "Email",
    "pdf": "PDF",
    "foto": "Foto",
    "audio": "Audio de WhatsApp",
    "llamada": "Llamada",
    "nota_voz": "Nota de voz",
}
ORIGENES = {
    "solicitud_voz": "Solicitud por nota de voz",
    "solicitud_email": "Solicitud por email",
    "stock_minimo": "Stock mínimo",
    "zafra": "Zafra",
    "demo": "Demo guiada",
}
PROPOSITOS = {"solicitud": "Solicitud interna", "cotizacion": "Cotización", "negociacion": "Negociación", "orden": "Orden de compra"}
RESULTADOS = {"atendida": "Atendida", "no_atendida": "No atendió", "buzon": "Buzón de voz", "fallida": "Falló", "en_curso": "En curso"}
_REEMPLAZOS = {"→": "->", "↔": "<->", "−": "-", "≈": "~", "✓": "", "…": "..."}


def _limpio(texto: str) -> str:
    salida = []
    for c in texto:
        c = _REEMPLAZOS.get(c, c)
        try:
            c.encode("cp1252")
        except UnicodeEncodeError:
            continue
        salida.append(c)
    return "".join(salida)


def _p(texto: str | None, estilo: str = "p") -> Paragraph:
    return Paragraph(escape(_limpio(texto or "")).replace("\n", "<br/>"), _E[estilo])


def _fecha(valor: datetime | date | None, con_hora: bool = True) -> str:
    if valor is None:
        return "sin fecha"
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M") if con_hora else valor.strftime("%d/%m/%Y")
    return valor.strftime("%d/%m/%Y")


def _pesos(valor: Decimal | float | None, decimales: int = 0) -> str:
    return "—" if valor is None else f"$ {fmt(valor, decimales)}"


def _duracion(segundos: int | None) -> str:
    if not segundos:
        return "0:00"
    return f"{segundos // 60}:{segundos % 60:02d}"


def _tabla(filas: list[list[str]], anchos: list[float], numericas: frozenset[int] | set[int] = frozenset()) -> Table:
    datos = [[Paragraph(escape(_limpio(c)), _E["th"]) for c in filas[0]]]
    for fila in filas[1:]:
        datos.append(
            [Paragraph(escape(_limpio(c)).replace("\n", "<br/>"), _E["celda_num" if i in numericas else "celda"]) for i, c in enumerate(fila)]
        )
    tabla = Table(datos, colWidths=anchos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, _BORDE),
                ("BACKGROUND", (0, 0), (-1, 0), _SOMBRA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return tabla


def _pie(canvas, doc) -> None:  # noqa: ANN001 (firma de reportlab)
    canvas.saveState()
    ancho, _ = A4
    canvas.setStrokeColor(_BORDE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 15 * mm, ancho - doc.rightMargin, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_SUAVE)
    canvas.drawString(doc.leftMargin, 10 * mm, _limpio(doc.title))
    canvas.drawRightString(ancho - doc.rightMargin, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------- secciones
def _seccion_pedido(d: DetallePedido, ancho: float) -> list:
    h: list = [Paragraph("Datos del pedido", _E["h"])]
    datos = [
        ["Campo", "Valor"],
        ["Estado", etiqueta_estado(d.estado)],
        ["Cliente interno", "Ventas" if d.cliente_interno == "ventas" else "Personal"],
        ["Origen", ORIGENES.get(d.origen, d.origen)],
        ["Solicitante", d.solicitante or "—"],
        ["Creado", _fecha(d.creado_en)],
        ["Última actualización", _fecha(d.actualizado_en)],
    ]
    if d.necesario_desde:
        rango = _fecha(d.necesario_desde)
        if d.necesario_hasta and d.necesario_hasta != d.necesario_desde:
            rango += f" al {_fecha(d.necesario_hasta)}"
        datos.append(["Se necesita", rango])
    if d.motivo_cancelacion:
        datos.append(["Motivo de cancelación", d.motivo_cancelacion])
    h.append(_tabla(datos, [ancho * 0.3, ancho * 0.7]))

    h.append(Paragraph("Productos", _E["h3"]))
    filas = [["Producto", "Cantidad", "Para el", "Proveedor del plan"]]
    for l in d.lineas:
        cantidad = f"{fmt(l.cantidad)} {'L' if l.unidad == 'l' else 'u.'}"
        filas.append([l.nombre, cantidad, _fecha(l.necesario_para), l.proveedor_nombre or "—"])
    h.append(_tabla(filas, [ancho * 0.45, ancho * 0.15, ancho * 0.15, ancho * 0.25], {1}))

    h.append(Paragraph("Historial de estados", _E["h3"]))
    filas = [["Estado", "Fecha y hora", "Detalle"]]
    for e in d.historial_estados:
        filas.append([etiqueta_estado(e.estado), _fecha(e.en) if e.en else "—", e.detalle or ""])
    h.append(_tabla(filas, [ancho * 0.22, ancho * 0.18, ancho * 0.6]))

    if d.cotizaciones:
        h.append(Paragraph("Cotizaciones", _E["h3"]))
        h.append(_p("Costo comparable: sin IVA, en pesos uruguayos y por unidad del producto.", "nota"))
        filas = [["Proveedor", "Producto", "Precio original", "Costo comparable", "Entrega", "Pago", "Vigencia"]]
        for c in d.cotizaciones:
            for i in c.items:
                original = f"{'USD' if i.moneda_original == 'USD' else '$'} {fmt(i.precio_original, 2 if i.precio_original % 1 else 0)}"
                original += f" {'c/IVA' if i.incluye_iva_original else '+ IVA'} por {i.unidad_original}"
                if i.cantidad_minima:
                    original += f" (mínimo {fmt(i.cantidad_minima)})"
                filas.append(
                    [
                        c.proveedor_nombre,
                        i.nombre,
                        original,
                        _pesos(i.precio_unitario_sin_iva, 2),
                        f"{c.lead_time_dias} días" if c.lead_time_dias is not None else "—",
                        "Contado" if c.plazo_pago_dias == 0 else f"{c.plazo_pago_dias} días",
                        f"{c.vigencia_dias} días",
                    ]
                )
        h.append(_tabla(filas, [ancho * w for w in (0.17, 0.2, 0.2, 0.13, 0.09, 0.1, 0.11)], {3}))

    if d.plan:
        h.append(Paragraph("Plan de compra", _E["h3"]))
        texto = f"Costo total: {_pesos(d.plan.costo_total)} + IVA, comprando a {', '.join(d.plan.proveedores_usados)}."
        if d.plan.ahorro is not None and d.plan.ahorro > 0:
            texto += f" Ahorro: {_pesos(d.plan.ahorro)} ({fmt(d.plan.ahorro_pct or 0, 1)} %) contra comprarle todo al proveedor habitual."
        h.append(_p(texto))
        if d.plan.explicacion:
            h.append(_p(d.plan.explicacion))

    if d.ordenes:
        h.append(Paragraph("Órdenes de compra", _E["h3"]))
        filas = [["Número", "Proveedor", "Estado", "Total sin IVA", "Total con IVA", "Aprobada por", "Emitida"]]
        estados = {
            "pendiente_aprobacion": "Pendiente de aprobación",
            "emitida": "Emitida",
            "pendiente_entrega": "Pendiente de entrega",
            "recibida": "Recibida",
            "cancelada": "Cancelada",
        }
        for o in d.ordenes:
            aprobada = {"agente": "Agente (automática)", "lucia": "Lucía"}.get(o.aprobada_por or "", o.aprobada_por or "—")
            filas.append(
                [o.numero, o.proveedor_nombre, estados[o.estado], _pesos(o.total_sin_iva), _pesos(o.total_con_iva), aprobada, _fecha(o.emitida_en) if o.emitida_en else "—"]
            )
        h.append(_tabla(filas, [ancho * w for w in (0.11, 0.19, 0.17, 0.13, 0.13, 0.13, 0.14)], {3, 4}))
        for o in d.ordenes:
            if o.motivos:
                h.append(_p(f"{o.numero}: " + " ".join(o.motivos), "nota"))

    if d.negociaciones:
        h.append(Paragraph("Negociación", _E["h3"]))
        for n in d.negociaciones:
            estrategias = "; ".join(
                f"{e.nombre} {fmt(e.concesion_obtenida_pct, 1)} % (riesgo {e.riesgo})" for e in n.estrategias
            )
            h.append(_p(f"{n.proveedor_nombre}: estrategia elegida «{n.elegida}». Ensayo contra el gemelo: {estrategias}."))
            h.append(_p(f"Mensaje propuesto: {n.mensaje_propuesto}", "nota"))
            if n.resultado:
                h.append(_p(f"Resultado: {n.resultado}"))
    return h


def _mensaje(m: Mensaje, ancho: float) -> list:
    sentido = "Enviado" if m.sentido == "enviado" else "Recibido"
    meta = f"{_fecha(m.fecha) if m.fecha else 'Sin hora registrada'} · {CANALES.get(m.canal, m.canal)} · {sentido} · De: {m.de} · Para: {m.para}"
    if m.etiqueta:
        meta += f" · {m.etiqueta}"
    bloque: list = [_p(meta, "meta")]
    if m.llamada:
        ll = m.llamada
        partes = [f"Llamada{' (intento ' + str(ll.intento) + ')' if ll.intento else ''}", RESULTADOS.get(ll.resultado, ll.resultado)]
        if ll.resultado == "atendida":
            partes.append(f"duración {_duracion(ll.duracion_segundos)}")
        if ll.modo == "simulada":
            partes.append("llamada simulada, sin audio")
        elif ll.audio_disponible_hasta:
            partes.append(f"audio disponible hasta el {_fecha(ll.audio_disponible_hasta, con_hora=False)}")
        bloque.append(_p(" · ".join(partes)))
        if ll.resumen:
            bloque.append(_p(f"Resultado: {ll.resumen}"))
    if m.texto:
        bloque.append(_p(m.texto))
    if m.transcripcion:
        filas = [[Paragraph(f"<b>{escape(_limpio(t.quien))}:</b> {escape(_limpio(t.texto))}", _E["turno"])] for t in m.transcripcion]
        tabla = Table(filas, colWidths=[ancho])
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _FONDO_TRANSCRIPCION),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        bloque += [_p("Transcripción completa:", "meta"), tabla]
    if m.nota:
        bloque.append(_p(m.nota, "nota"))
    bloque.append(Spacer(1, 5))
    return bloque


def _seccion_dialogo(d: DetallePedido, ancho: float) -> list:
    h: list = [Paragraph("Diálogo del agente", _E["h"])]
    h.append(_p("Cada mensaje con su canal, sentido, participante y fecha y hora. Las llamadas, con la transcripción completa.", "nota"))
    if not d.conversaciones:
        h.append(_p("Todavía no hay conversaciones registradas para este pedido."))
    for conv in d.conversaciones:
        h.append(Paragraph(escape(_limpio(f"{conv.contraparte} · {PROPOSITOS.get(conv.proposito, conv.proposito)}")), _E["h3"]))
        for m in conv.mensajes:
            # con transcripción, el mensaje puede cortar página: no se fuerza a una sola
            h.append(_mensaje(m, ancho) if m.transcripcion else KeepTogether(_mensaje(m, ancho)))
    return h


def _aplanar(bloques: list) -> list:
    salida = []
    for b in bloques:
        if isinstance(b, list):
            salida.extend(b)
        else:
            salida.append(b)
    return salida


# ---------------------------------------------------------------- entrada
def generar(d: DetallePedido, *, incluir_pedido: bool = True, incluir_dialogo: bool = True) -> bytes:
    buffer = io.BytesIO()
    titulo = f"Abasto · Informe del pedido {d.numero}"
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title=titulo,
        author="Abasto",
    )
    contenido = "datos del pedido y diálogo del agente" if incluir_pedido and incluir_dialogo else (
        "datos del pedido" if incluir_pedido else "diálogo del agente"
    )
    historia: list = [
        _p(titulo, "titulo"),
        _p(f"{d.titulo} · {d.negocio} · {contenido} · generado el {datetime.now():%d/%m/%Y %H:%M}", "sub"),
        HRFlowable(width="100%", thickness=2, color=_MARCA, spaceAfter=8),
    ]
    if d.ejemplo:
        historia.append(_p("Datos de ejemplo: este pedido no es una compra real.", "aviso"))
    if incluir_pedido:
        historia += _seccion_pedido(d, doc.width)
    if incluir_dialogo:
        historia += _aplanar(_seccion_dialogo(d, doc.width))
    doc.build(historia, onFirstPage=_pie, onLaterPages=_pie)
    return buffer.getvalue()
