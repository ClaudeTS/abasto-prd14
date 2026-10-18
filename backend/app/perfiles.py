"""Proveedores (bloque 4, PRD 1.4): ficha, perfil de negociación, confianza del gemelo y altas.

- **Ficha**: lo público de `proveedores_sim.json` + antigüedad, cumplimiento histórico y garantía de
  `data/proveedores_extra.json` (datos de ejemplo, marcados `ejemplo: true`).
- **Perfil de negociación** (RF-17, §11.6): parte del perfil privado del gemelo y guarda lo que edita
  el administrador en la colección `perfiles_proveedor`. `para_gemelo()` aplica esas ediciones al
  perfil privado, así lo editado alimenta al gemelo (lo llama `pipeline.perfil_privado`).
- **Confianza** (§11.6): desvío promedio entre la concesión simulada (estrategia elegida) y la real
  (precio acordado en la llamada de negociación). Se calcula al leer, nunca se guarda.
- **Altas** (RF-19): manual (queda activa) o por el agente (conversación simulada, queda "en revisión"
  hasta que un administrador la aprueba). Colección `proveedores_alta`.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, Field

from app import pipeline, store
from app.models import Llamada, MensajeCrudo, Negociacion, Plan

COL_PERFILES = "perfiles_proveedor"
COL_ALTAS = "proveedores_alta"
CONFIANZA_ALTA_PP = 2.0
CONFIANZA_MEDIA_PP = 5.0
MIN_NEGOCIACIONES = 3

NivelConfianza = Literal["alta", "media", "baja", "sin_datos"]

# Campos editables del perfil → clave en el perfil privado que usa el gemelo (negociacion.py).
CAMPOS_GEMELO = {
    "estilo": "personalidad",
    "condiciones_habituales": "habitos",
    "precio_piso_pct": "precio_piso_pct",
    "sensible_a": "sensible_a",
    "no_sensible_a": "insensible_a",
    "concesion_tipica": "perfil_concesion",
}


# ---------------------------------------------------------------- modelos del bloque
class PerfilEdicion(BaseModel):
    """PATCH /proveedores/{id}/perfil: solo los campos que cambian."""

    estilo: str | None = None
    condiciones_habituales: str | None = None
    precio_piso_pct: float | None = Field(default=None, ge=0, le=50)
    sensible_a: list[str] | None = None
    no_sensible_a: list[str] | None = None
    concesion_tipica: str | None = None
    motivo: str | None = None
    usuario: str | None = None  # quién edita (hasta que el bloque 3 tenga la sesión real)


class Contacto(BaseModel):
    nombre: str | None = None
    email: str | None = None
    telefono: str | None = None


class Condiciones(BaseModel):
    plazo_pago_dias: int | None = Field(default=None, ge=0)
    plazo_entrega_dias: int | None = Field(default=None, ge=0)
    pedido_minimo: str | None = None
    envio: str | None = None
    garantia_meses: int | None = Field(default=None, ge=0)


class AltaManual(BaseModel):
    nombre: str = Field(min_length=2)
    razon_social: str | None = None
    rubro: str = ""
    contacto: Contacto = Field(default_factory=Contacto)
    whatsapp: bool = False
    canal_preferido: str = "whatsapp_texto"
    condiciones: Condiciones = Field(default_factory=Condiciones)
    productos: list[str] = Field(default_factory=list)
    usuario: str | None = None


class AltaAgente(BaseModel):
    """Lo mínimo que el agente necesita para contactar a un proveedor nuevo."""

    nombre: str = Field(min_length=2)
    telefono: str | None = None
    email: str | None = None
    canal: Literal["whatsapp", "email", "llamada"] = "whatsapp"
    rubro: str | None = None
    productos: list[str] = Field(default_factory=list)  # ids del catálogo o texto libre
    pedido_id: str | None = None  # la negociación/pedido que motivó el alta
    motivo: str | None = None


class AprobacionAlta(BaseModel):
    usuario: str | None = None
    aprobar: bool = True
    motivo: str | None = None


# ---------------------------------------------------------------- datos semilla
def _extra() -> dict[str, Any]:
    try:
        return store.semilla("proveedores_extra")
    except FileNotFoundError:
        return {"proveedores": {}, "negociaciones_historicas": []}


def extra(proveedor_id: str) -> dict[str, Any]:
    return _extra().get("proveedores", {}).get(proveedor_id, {})


def _privado_original(proveedor_id: str) -> dict[str, Any] | None:
    for p in store.semilla("proveedores_sim")["proveedores"]:
        if p["publico"]["id"] == proveedor_id:
            return p["privado"]
    return None


def altas() -> list[dict[str, Any]]:
    return store.valores(COL_ALTAS)


def alta(proveedor_id: str) -> dict[str, Any] | None:
    return store.obtener_dict(COL_ALTAS, proveedor_id)


def existe(proveedor_id: str) -> bool:
    return proveedor_id in pipeline.proveedores() or alta(proveedor_id) is not None


# ---------------------------------------------------------------- ficha
def antiguedad(fecha_alta: str | None, hoy: date | None = None) -> dict[str, Any]:
    if not fecha_alta:
        return {"fecha_alta": None, "dias": None, "texto": "nuevo"}
    desde = date.fromisoformat(fecha_alta[:10])
    dias = max(((hoy or date.today()) - desde).days, 0)
    if dias < 30:
        texto = "nuevo"
    elif dias < 365:
        meses = dias // 30
        texto = "1 mes" if meses == 1 else f"{meses} meses"
    else:
        anios = dias // 365
        texto = "1 año" if anios == 1 else f"{anios} años"
    return {"fecha_alta": desde.isoformat(), "dias": dias, "texto": texto}


def ficha(proveedor_id: str) -> dict[str, Any]:
    """Datos del proveedor para el listado, el ranking y la evaluación."""
    publicos = pipeline.proveedores()
    if proveedor_id in publicos:
        p = publicos[proveedor_id]
        e = extra(proveedor_id)
        return {
            "id": p.id,
            "nombre": p.nombre,
            "rubro": p.rubro,
            "canal_preferido": p.canal_preferido,
            "confiabilidad": p.confiabilidad,
            "antiguedad": antiguedad(e.get("fecha_alta")),
            "cumplimiento_historico_pct": e.get("cumplimiento_historico_pct"),
            "garantia_meses": e.get("garantia_meses"),
            "email": e.get("email"),
            "whatsapp": e.get("whatsapp"),
            "alta_por": e.get("alta_por", "usuario"),
            "estado": "activo",
            "datos_ejemplo": bool(e.get("ejemplo")),
        }
    a = alta(proveedor_id)
    if a is None:
        raise KeyError(proveedor_id)
    return {
        "id": a["id"],
        "nombre": a["nombre"],
        "rubro": a.get("rubro") or "",
        "canal_preferido": a.get("canal_preferido", "whatsapp_texto"),
        "confiabilidad": None,
        "antiguedad": antiguedad(None),
        "cumplimiento_historico_pct": None,
        "garantia_meses": (a.get("condiciones") or {}).get("garantia_meses"),
        "email": (a.get("contacto") or {}).get("email"),
        "whatsapp": a.get("whatsapp"),
        "alta_por": a.get("alta_por", "usuario"),
        "estado": a.get("estado", "activo"),
        "datos_ejemplo": False,
    }


# ---------------------------------------------------------------- perfil de negociación
def rango_concesion(texto: str | None) -> str | None:
    """"Cede 2–4 % por pago contado y hasta 6 % si…" → "2–6 %". None si el texto no tiene porcentajes."""
    if not texto:
        return None
    numeros = []
    for a, b in re.findall(r"(\d+(?:[.,]\d+)?)(?:\s*[–-]\s*(\d+(?:[.,]\d+)?))?\s*%", texto):
        numeros += [float(x.replace(",", ".")) for x in (a, b) if x]
    if not numeros:
        return None
    bajo, alto = min(numeros), max(numeros)
    f = lambda x: f"{x:g}".replace(".", ",")  # noqa: E731
    return f"{f(bajo)} %" if bajo == alto else f"{f(bajo)}–{f(alto)} %"


def _base(proveedor_id: str) -> dict[str, Any]:
    privado = _privado_original(proveedor_id)
    if privado is not None:
        return {
            "estilo": privado.get("personalidad", ""),
            "condiciones_habituales": privado.get("habitos", ""),
            "precio_piso_pct": privado.get("precio_piso_pct"),
            "sensible_a": list(privado.get("sensible_a", [])),
            "no_sensible_a": list(privado.get("insensible_a", [])),
            "concesion_tipica": privado.get("perfil_concesion", ""),
        }
    a = alta(proveedor_id)
    if a is None:
        raise KeyError(proveedor_id)
    return {
        "estilo": a.get("estilo") or "Proveedor nuevo: todavía no hay historial para estimar su estilo.",
        "condiciones_habituales": texto_condiciones(a.get("condiciones") or {}),
        "precio_piso_pct": None,
        "sensible_a": [],
        "no_sensible_a": [],
        "concesion_tipica": "",
    }


def _edicion(proveedor_id: str) -> dict[str, Any]:
    return store.obtener_dict(COL_PERFILES, proveedor_id) or {}


def para_gemelo(proveedor_id: str, privado: dict[str, Any]) -> dict[str, Any]:
    """El perfil privado con lo que editó el administrador (lo que lee el gemelo)."""
    campos = _edicion(proveedor_id).get("campos") or {}
    if not campos:
        return privado
    combinado = dict(privado)
    for campo, valor in campos.items():
        if campo in CAMPOS_GEMELO:
            combinado[CAMPOS_GEMELO[campo]] = valor
    return combinado


def perfil(proveedor_id: str) -> dict[str, Any]:
    """Perfil completo: campos (base + edición), confianza, historial y tiempos de respuesta."""
    base = _base(proveedor_id)
    edicion = _edicion(proveedor_id)
    campos = {**base, **(edicion.get("campos") or {})}
    historial = historial_negociaciones(proveedor_id)
    conf = confianza(historial, es_nuevo=proveedor_id not in pipeline.proveedores())
    return {
        "proveedor": ficha(proveedor_id),
        **campos,
        "concesion_tipica_rango": rango_concesion(campos.get("concesion_tipica")),
        "negociaciones_observadas": conf["negociaciones"],
        "confianza": conf,
        "editado": bool(edicion.get("campos")),
        "actualizado_el": edicion.get("actualizado_el"),
        "actualizado_por": edicion.get("actualizado_por"),
        "version": edicion.get("version", 0),
        "historial_ediciones": edicion.get("historial", []),
        "historial_negociaciones": historial,
        "tiempo_respuesta": tiempos_respuesta(proveedor_id),
    }


def editar(proveedor_id: str, cambios: PerfilEdicion) -> dict[str, Any]:
    base = _base(proveedor_id)
    edicion = _edicion(proveedor_id)
    campos = dict(edicion.get("campos") or {})
    actual = {**base, **campos}
    nuevos = cambios.model_dump(exclude_none=True, exclude={"motivo", "usuario"})
    diferencias = {}
    for campo, valor in nuevos.items():
        if isinstance(valor, str):
            valor = valor.strip()
        if isinstance(valor, list):
            valor = [v.strip() for v in valor if v and v.strip()]
        if valor != actual.get(campo):
            diferencias[campo] = {"antes": actual.get(campo), "despues": valor}
            campos[campo] = valor
    if not diferencias:
        return perfil(proveedor_id)
    ahora = datetime.now().isoformat(timespec="seconds")
    usuario = (cambios.usuario or "").strip() or "administrador"
    historial = list(edicion.get("historial", []))
    historial.append(
        {"fecha": ahora, "usuario": usuario, "motivo": (cambios.motivo or "").strip() or None, "cambios": diferencias}
    )
    store.guardar_dict(
        COL_PERFILES,
        proveedor_id,
        {
            "proveedor_id": proveedor_id,
            "campos": campos,
            "actualizado_el": ahora,
            "actualizado_por": usuario,
            "version": int(edicion.get("version", 0)) + 1,
            "historial": historial,
        },
    )
    return perfil(proveedor_id)


# ---------------------------------------------------------------- confianza del gemelo
def _concesion_real(neg: Negociacion) -> tuple[float | None, Llamada | None]:
    """Concesión real (%) según la llamada de negociación asociada, si terminó con resultado."""
    llamadas = [
        Llamada.model_validate(l)
        for l in store.valores("llamadas")
        if l.get("negociacion_id") == neg.id or (neg.llamada_id and l.get("id") == neg.llamada_id)
    ]
    terminadas = [l for l in llamadas if l.estado == "terminada" and l.resultado is not None]
    llamada = max(terminadas, key=lambda l: l.iniciada_en, default=None) or max(
        llamadas, key=lambda l: l.iniciada_en, default=None
    )
    if llamada is None or llamada.estado != "terminada" or llamada.resultado is None:
        return None, llamada
    res = llamada.resultado
    if res.precio_acordado is not None:
        cotizado = _precio_cotizado(neg)
        if cotizado:
            pct = (cotizado - Decimal(res.precio_acordado)) / cotizado * 100
            return round(float(max(pct, Decimal(0))), 2), llamada
    if res.acuerdo is False:
        return 0.0, llamada
    return None, llamada


def _precio_cotizado(neg: Negociacion) -> Decimal | None:
    """Precio del primer ítem del plan para ese proveedor: el que se negocia por teléfono."""
    plan = store.obtener_dict("planes", neg.pedido_id)
    if plan:
        asignado = [a for a in Plan.model_validate(plan).asignaciones if a.proveedor_id == neg.proveedor_id]
        if asignado:
            return Decimal(asignado[0].precio_unitario_sin_iva)
    return None


def historial_negociaciones(proveedor_id: str) -> list[dict[str, Any]]:
    """Simulado contra real: las negociaciones del store (reales) y las de ejemplo."""
    filas: list[dict[str, Any]] = []
    for neg in store.listar("negociaciones", Negociacion, proveedor_id=proveedor_id):
        elegida = next((e for e in neg.estrategias if e.nombre == neg.elegida), None)
        simulada = elegida.concesion_obtenida_pct if elegida else None
        real, llamada = _concesion_real(neg)
        observada = real is not None and llamada is not None and llamada.modo == "real"
        filas.append(
            {
                "origen": "real",
                "negociacion_id": neg.id,
                "pedido_id": neg.pedido_id,
                "fecha": llamada.iniciada_en.isoformat(timespec="seconds") if llamada else None,
                "estrategia": neg.elegida,
                "estado": neg.estado,
                "concesion_simulada_pct": simulada,
                "concesion_real_pct": real,
                "desvio_pp": round(simulada - real, 2) if simulada is not None and real is not None else None,
                "llamada_id": llamada.id if llamada else None,
                "llamada_modo": llamada.modo if llamada else None,
                # Una llamada simulada repite la concesión del gemelo: no mide su precisión.
                "cuenta_para_confianza": observada,
                "nota": (
                    None
                    if observada
                    else "Llamada simulada: repite lo del gemelo, no cuenta para la confianza"
                    if llamada is not None and llamada.modo == "simulada" and real is not None
                    else "Sin resultado real todavía"
                ),
                "ejemplo": False,
            }
        )
    for h in _extra().get("negociaciones_historicas", []):
        if h.get("proveedor_id") != proveedor_id:
            continue
        sim, real = h.get("concesion_simulada_pct"), h.get("concesion_real_pct")
        filas.append(
            {
                "origen": "ejemplo",
                "negociacion_id": None,
                "pedido_id": h.get("pedido"),
                "fecha": h.get("fecha"),
                "estrategia": h.get("estrategia"),
                "estado": "cerrada",
                "concesion_simulada_pct": sim,
                "concesion_real_pct": real,
                "desvio_pp": round(sim - real, 2) if sim is not None and real is not None else None,
                "llamada_id": None,
                "llamada_modo": None,
                "cuenta_para_confianza": sim is not None and real is not None,
                "nota": None,
                "ejemplo": True,
            }
        )
    filas.sort(key=lambda f: f.get("fecha") or "9999", reverse=True)  # sin fecha (en curso) primero
    return filas


def confianza(historial: list[dict[str, Any]] | None, *, es_nuevo: bool = False) -> dict[str, Any]:
    """§11.6: alta hasta ±2 pp; media hasta ±5; baja más de ±5 o menos de 3 negociaciones."""
    observadas = [h for h in (historial or []) if h.get("cuenta_para_confianza")]
    n = len(observadas)
    desvio = round(sum(abs(h["desvio_pp"]) for h in observadas) / n, 2) if n else None
    con_ejemplo = any(h.get("ejemplo") for h in observadas)
    if n == 0 and es_nuevo:
        nivel: NivelConfianza = "sin_datos"
        motivo = "Proveedor nuevo: sin negociaciones."
    elif n < MIN_NEGOCIACIONES:
        nivel = "baja"
        motivo = (
            "Sin negociaciones reales."
            if n == 0
            else f"Solo {n} negociación{'es' if n > 1 else ''} real{'es' if n > 1 else ''}: hacen falta {MIN_NEGOCIACIONES}."
        )
    elif desvio <= CONFIANZA_ALTA_PP:  # type: ignore[operator]
        nivel, motivo = "alta", f"Desvío promedio ±{_pp(desvio)} pp en {n} negociaciones."
    elif desvio <= CONFIANZA_MEDIA_PP:  # type: ignore[operator]
        nivel, motivo = "media", f"Desvío promedio ±{_pp(desvio)} pp en {n} negociaciones."
    else:
        nivel, motivo = "baja", f"Desvío promedio ±{_pp(desvio)} pp en {n} negociaciones (más de ±5)."
    return {
        "nivel": nivel,
        "desvio_promedio_pp": desvio,
        "negociaciones": n,
        "motivo": motivo,
        "incluye_ejemplos": con_ejemplo,
    }


def _pp(valor: float | None) -> str:
    return f"{valor:.1f}".replace(".", ",") if valor is not None else "—"


# ---------------------------------------------------------------- tiempo de respuesta por canal
def tiempos_respuesta(proveedor_id: str) -> dict[str, Any]:
    """Del store: cuánto tardó en responder la solicitud de cotización por cada canal, y cuántas
    llamadas atendió. Sin datos, cada valor es null."""
    inicios: dict[str, datetime | None] = {}
    por_canal: dict[str, list[float]] = {}
    for m in store.listar("mensajes", MensajeCrudo, proveedor_id=proveedor_id):
        if m.pedido_id not in inicios:
            sim = store.obtener_dict("simulaciones", m.pedido_id) or {}
            inicios[m.pedido_id] = datetime.fromtimestamp(float(sim["inicio"])) if sim.get("inicio") else None
        inicio = inicios[m.pedido_id]
        if m.canal == "llamada" or inicio is None:
            continue
        segundos = (m.recibido_en.replace(tzinfo=None) - inicio).total_seconds()
        if segundos >= 0:
            por_canal.setdefault(m.canal, []).append(segundos)
    canales = [
        {
            "canal": canal,
            "respuestas": len(valores),
            "promedio_segundos": round(sum(valores) / len(valores), 1),
            "mediana_segundos": round(median(valores), 1),
        }
        for canal, valores in sorted(por_canal.items())
    ]
    llamadas = [l for l in store.listar("llamadas", Llamada, proveedor_id=proveedor_id) if l.estado in ("terminada", "fallida")]
    atendidas = [l for l in llamadas if l.estado == "terminada"]
    duraciones = [l.duracion_segundos for l in atendidas if l.duracion_segundos]
    return {
        "canales": canales,
        "llamadas": {
            "realizadas": len(llamadas),
            "atendidas": len(atendidas),
            "duracion_promedio_segundos": round(sum(duraciones) / len(duraciones), 1) if duraciones else None,
        }
        if llamadas
        else None,
        "mas_rapido": min(canales, key=lambda c: c["promedio_segundos"])["canal"] if canales else None,
        "fuente": "Mensajes y llamadas registrados en Abasto (en la demo, con las demoras del simulador)",
    }


# ---------------------------------------------------------------- listado
def resumen(proveedor_id: str) -> dict[str, Any]:
    f = ficha(proveedor_id)
    es_nuevo = proveedor_id not in pipeline.proveedores()
    campos = {**_base(proveedor_id), **(_edicion(proveedor_id).get("campos") or {})}
    historial = historial_negociaciones(proveedor_id)
    productos = sorted(_productos(proveedor_id))
    return {
        **f,
        "productos": productos,
        "perfil": {
            "sensible_a": campos.get("sensible_a") or [],
            "no_sensible_a": campos.get("no_sensible_a") or [],
            "concesion_tipica": campos.get("concesion_tipica") or "",
            "concesion_tipica_rango": rango_concesion(campos.get("concesion_tipica")),
            "precio_piso_pct": campos.get("precio_piso_pct"),
        }
        if not es_nuevo or campos.get("sensible_a") or campos.get("concesion_tipica")
        else None,
        "confianza": confianza(historial, es_nuevo=es_nuevo),
        "habitual": proveedor_id == pipeline.datos_pedido()["pedido"].get("proveedor_habitual_id"),
    }


def _productos(proveedor_id: str) -> set[str]:
    privado = _privado_original(proveedor_id)
    if privado is not None:
        return set(privado.get("tabla_precios", {}))
    a = alta(proveedor_id) or {}
    return set(a.get("productos") or [])


def listado() -> list[dict[str, Any]]:
    ids = list(pipeline.proveedores()) + [a["id"] for a in altas()]
    return [resumen(pid) for pid in ids]


# ---------------------------------------------------------------- altas (RF-19)
CANAL_ALTA = {"whatsapp": "whatsapp_texto", "email": "pdf", "llamada": "llamada"}


def texto_condiciones(c: dict[str, Any]) -> str:
    partes = []
    if c.get("pedido_minimo"):
        partes.append(f"mínimo {c['pedido_minimo']}")
    if c.get("envio"):
        partes.append(f"envío {c['envio']}")
    if c.get("plazo_pago_dias") is not None:
        partes.append("pago contado" if c["plazo_pago_dias"] == 0 else f"pago {c['plazo_pago_dias']} días")
    if c.get("plazo_entrega_dias") is not None:
        partes.append(f"entrega {c['plazo_entrega_dias']} días")
    if c.get("garantia_meses"):
        partes.append(f"garantía {c['garantia_meses']} meses")
    return " · ".join(partes) or "Sin condiciones cargadas."


def _slug(nombre: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", nombre.lower().translate(str.maketrans("áéíóúñü", "aeiounu"))).strip("_")
    return f"nuevo_{base or 'proveedor'}_{uuid.uuid4().hex[:4]}"


def _nombre_producto(pid: str) -> str:
    return {p.id: p.nombre for p in pipeline.catalogo()}.get(pid, pid)


def alta_manual(datos: AltaManual) -> dict[str, Any]:
    ahora = datetime.now().isoformat(timespec="seconds")
    registro = {
        "id": _slug(datos.nombre),
        "nombre": datos.nombre.strip(),
        "razon_social": (datos.razon_social or datos.nombre).strip(),
        "rubro": datos.rubro.strip(),
        "contacto": datos.contacto.model_dump(),
        "whatsapp": datos.whatsapp,
        "canales": [datos.canal_preferido],
        "canal_preferido": datos.canal_preferido,
        "condiciones": datos.condiciones.model_dump(),
        "productos": datos.productos,
        "estado": "activo",
        "alta_por": "usuario",
        "creado_por": (datos.usuario or "").strip() or "administrador",
        "creado_en": ahora,
        "aprobado_por": (datos.usuario or "").strip() or "administrador",
        "aprobado_en": ahora,
        "conversacion": [],
        "simulada": False,
    }
    store.guardar_dict(COL_ALTAS, registro["id"], registro)
    return registro


def alta_por_agente(datos: AltaAgente) -> dict[str, Any]:
    """RF-19 simulado: el agente contacta al proveedor nuevo, le pide los datos y lo deja en revisión.

    La conversación es un guion en código (no se manda nada): el "proveedor" contesta con datos de
    ejemplo verosímiles, que quedan cargados y marcados como simulados hasta que el admin los revise.
    """
    nombre = datos.nombre.strip()
    razon_social = nombre if re.search(r"\b(S\.?A\.?|S\.?R\.?L\.?|Ltda\.?)$", nombre, re.I) else f"{nombre} S.R.L."
    productos = datos.productos or []
    nombres_prod = [_nombre_producto(p).lower() for p in productos]
    lista_prod = ", ".join(nombres_prod) if nombres_prod else (datos.rubro or "sus productos")
    canal_txt = {"whatsapp": "WhatsApp", "email": "email", "llamada": "teléfono"}[datos.canal]
    rubro = (datos.rubro or "").strip() or ("proveedor de " + lista_prod)
    contacto = {
        "nombre": "Martín (ventas)",
        "email": datos.email or f"ventas@{re.sub(r'[^a-z0-9]', '', nombre.lower()) or 'proveedor'}.com.uy",
        "telefono": datos.telefono,
    }
    condiciones = {
        "plazo_pago_dias": 30,
        "plazo_entrega_dias": 5,
        "pedido_minimo": "sin mínimo",
        "envio": "sin cargo en Montevideo",
        "garantia_meses": 12 if any(p in {"notebook", "silla"} for p in productos) else None,
    }
    motivo = (datos.motivo or "").strip()
    comprador = (pipeline.datos_pedido()["pedido"].get("comprador") or "Compras").split(" (")[0]
    negocio = pipeline.datos_pedido()["pedido"].get("negocio", "la empresa")
    turnos = [
        ("abasto", f"Hola, ¿hablo con {nombre}? Te escribe el asistente de compras de {negocio}, de parte de {comprador}. "
                   + (f"{motivo} " if motivo else "")
                   + f"Estamos buscando proveedores de {lista_prod} y nos gustaría darte de alta. ¿Me pasás unos datos?"),
        ("proveedor", "¡Hola! Sí, claro. ¿Qué necesitás?"),
        ("abasto", "Primero, la razón social y un contacto de ventas."),
        ("proveedor", f"Somos {razon_social}. Te atiende {contacto['nombre'].split(' ')[0]}, de ventas; el mail es {contacto['email']}."),
        ("abasto", f"Perfecto. ¿Por qué canales te podemos pedir cotización? ¿Tenés WhatsApp?"),
        ("proveedor", f"Por WhatsApp a este mismo número o por mail. Cotizamos en el día."),
        ("abasto", "¿Cuáles son tus condiciones habituales? Plazo de pago, entrega, mínimo de compra y envío."),
        ("proveedor", "Pago a 30 días con factura, entrega en 5 días hábiles, sin mínimo y envío sin cargo en Montevideo."
                      + (" Los equipos tienen 12 meses de garantía." if condiciones["garantia_meses"] else "")),
        ("abasto", f"Bárbaro. ¿Qué productos nos podrías ofrecer?"),
        ("proveedor", f"Trabajamos {lista_prod}. Si me pasás cantidades te cotizo."),
        ("abasto", f"Gracias. Te dejo cargado como proveedor; {comprador} revisa los datos y te pedimos cotización por {canal_txt}."),
    ]
    inicio = datetime.now()
    conversacion = [
        {"rol": rol, "texto": texto, "canal": datos.canal, "segundo": i * 20}
        for i, (rol, texto) in enumerate(turnos)
    ]
    registro = {
        "id": _slug(nombre),
        "nombre": nombre,
        "razon_social": razon_social,
        "rubro": rubro,
        "contacto": contacto,
        "whatsapp": True,
        "canales": ["whatsapp_texto", "pdf"] if datos.canal != "llamada" else ["llamada", "whatsapp_texto"],
        "canal_preferido": CANAL_ALTA[datos.canal],
        "condiciones": condiciones,
        "productos": productos,
        "estado": "en_revision",
        "alta_por": "agente",
        "creado_por": "agente",
        "creado_en": inicio.isoformat(timespec="seconds"),
        "aprobado_por": None,
        "aprobado_en": None,
        "pedido_id": datos.pedido_id,
        "motivo": motivo or None,
        "conversacion": conversacion,
        "simulada": True,
        "datos_pedidos": ["razón social", "contacto", "canales", "condiciones", "productos"],
    }
    store.guardar_dict(COL_ALTAS, registro["id"], registro)
    return registro


def aprobar_alta(proveedor_id: str, datos: AprobacionAlta) -> dict[str, Any]:
    registro = alta(proveedor_id)
    if registro is None:
        raise KeyError(proveedor_id)
    if registro.get("estado") != "en_revision":
        raise ValueError(f"El alta de {registro['nombre']} no está en revisión (estado: {registro.get('estado')})")
    registro["estado"] = "activo" if datos.aprobar else "rechazado"
    registro["aprobado_por"] = (datos.usuario or "").strip() or "administrador"
    registro["aprobado_en"] = datetime.now().isoformat(timespec="seconds")
    if datos.motivo:
        registro["motivo_revision"] = datos.motivo.strip()
    store.guardar_dict(COL_ALTAS, proveedor_id, registro)
    return registro
