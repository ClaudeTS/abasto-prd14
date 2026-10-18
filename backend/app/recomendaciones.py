"""Recomendaciones de la IA para el dashboard (RF-09, tabla `recomendacion` del PRD 1.4 §11.3).

Las detectan reglas en código, con los datos del store y del histórico de ejemplo:
- `alza_precio`: el último precio de un producto en un proveedor supera su promedio de los 6 meses
  anteriores en más del umbral (`RECOMENDACION_UMBRAL_ALZA_PCT`, 8 % por defecto).
- `oferta_otro_proveedor`: un producto que se compra regularmente a A está más barato en B.
- `canal_mas_rapido`: un proveedor responde bastante más rápido por otro canal que por el preferido.
- `pendiente_aprobacion`: hay órdenes o negociaciones esperando al administrador.

Cada una trae los datos que la respaldan y un enlace. El texto sale de una plantilla; si hay LLM
(`ANTHROPIC_API_KEY`), lo redacta el prompt `recomendaciones` en segundo plano y queda en cache. El
LLM solo redacta: si su texto trae un número que no está en los datos, se descarta y queda la plantilla.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from app import config, kpi, store
from app.normalizacion import fmt

log = logging.getLogger("abasto.recomendaciones")

UMBRAL_ALZA_PCT = 8.0
MESES_PROMEDIO = 6
MINIMO_PRECIOS_PROMEDIO = 3
DIFERENCIA_OFERTA_PCT = 3.0  # menos que esto no vale la pena recomendar cambiar de proveedor
VIGENCIA_PRECIO_DIAS = 60  # un precio más viejo no se compara como oferta
MINIMO_ORDENES_REGULAR = 2
FACTOR_CANAL = 0.5  # el otro canal tiene que responder en la mitad del tiempo o menos
MINIMO_MUESTRAS_CANAL = 2
TIMEOUT_LLM_S = 45.0
COLECCION_DESCARTADAS = "recomendaciones_descartadas"

Tipo = Literal["alza_precio", "oferta_otro_proveedor", "canal_mas_rapido", "pendiente_aprobacion"]
_tareas: set[asyncio.Task] = set()


# ---------------------------------------------------------------- modelos
class DatoRespaldo(BaseModel):
    etiqueta: str
    valor: str
    ejemplo: bool = False  # sale del histórico de ejemplo


class Enlace(BaseModel):
    ruta: str  # /pedidos/{id} | /proveedores/{id} | /negociacion
    etiqueta: str


class Recomendacion(BaseModel):
    id: str
    tipo: Tipo
    titulo: str
    texto: str
    texto_origen: Literal["llm", "plantilla"] = "plantilla"
    datos: list[DatoRespaldo]
    enlace: Enlace
    producto_id: str | None = None
    proveedor_id: str | None = None
    ejemplo: bool
    estado: Literal["nueva", "descartada"] = "nueva"
    fecha: datetime
    prioridad: int  # menor = más arriba


class Recomendaciones(BaseModel):
    recomendaciones: list[Recomendacion]
    descartadas: int
    umbral_alza_pct: float
    redaccion: Literal["llm", "plantilla"]  # quién redacta cuando hay texto nuevo
    ejemplo: bool


class RedaccionLLM(BaseModel):
    id: str
    titulo: str
    texto: str


class SalidaLLM(BaseModel):
    recomendaciones: list[RedaccionLLM] = Field(default_factory=list)


class RecomendacionNoEncontrada(KeyError):
    pass


# ---------------------------------------------------------------- datos
@dataclass(frozen=True)
class _Precio:
    fecha: datetime
    producto_id: str
    proveedor_id: str
    precio: float
    pedido_id: str
    ejemplo: bool


def umbral_por_defecto() -> float:
    try:
        return float(os.environ.get("RECOMENDACION_UMBRAL_ALZA_PCT", "") or UMBRAL_ALZA_PCT)
    except ValueError:
        return UMBRAL_ALZA_PCT


def _precios(hasta: date) -> list[_Precio]:
    salida = [
        _Precio(kpi._dt(p["fecha"]), p["producto_id"], p["proveedor_id"], float(p["precio_sin_iva"]), p["pedido_id"], True)
        for p in kpi.historial()["precios"]
    ]
    mensajes = {m["id"]: m for m in store.valores("mensajes")}
    for c in store.valores("cotizaciones"):
        if c.get("pedido_id") == "pruebas":
            continue
        fecha = kpi._dt((mensajes.get(c.get("mensaje_id")) or {}).get("recibido_en")) or datetime.now()
        for i in c.get("items", []):
            salida.append(_Precio(fecha, i["producto_id"], c["proveedor_id"], float(i["precio_unitario_sin_iva"]), c["pedido_id"], False))
    return sorted((p for p in salida if p.fecha.date() <= hasta), key=lambda p: p.fecha)


def _ordenes(hasta: date) -> list[tuple[datetime, str, str, bool]]:
    """(fecha, producto, proveedor, ejemplo) de cada línea comprada."""
    salida = [
        (kpi._dt(o["emitida_en"]), o["producto_id"], o["proveedor_id"], True) for o in kpi.historial()["ordenes"]
    ]
    for c in store.valores("agentes"):
        for o in c.get("ordenes", []):
            if o.get("estado") == "enviada_simulada" and o.get("enviada_en"):
                salida += [(kpi._dt(o["enviada_en"]), l["producto_id"], o["proveedor_id"], False) for l in o.get("lineas", [])]
    return [o for o in salida if o[0].date() <= hasta]


def _minimos() -> dict[tuple[str, str], float]:
    """Mínimo de compra por (producto, proveedor), de las condiciones de los proveedores."""
    salida = {}
    for p in store.semilla("proveedores_sim")["proveedores"]:
        for producto_id, v in p["privado"].get("tabla_precios", {}).items():
            if v.get("cantidad_minima"):
                salida[(producto_id, p["publico"]["id"])] = float(v["cantidad_minima"])
    return salida


def _pesos(valor: float) -> str:
    return f"$ {fmt(valor, 2)}" if valor < 1000 and round(valor * 100) % 100 else f"$ {fmt(valor)}"


def _fecha(d: datetime) -> str:
    return d.strftime("%d/%m/%Y")


def _enlace_precio(p: _Precio) -> Enlace:
    if p.ejemplo:  # los pedidos del histórico de ejemplo no existen en el listado de pedidos
        return Enlace(ruta=f"/proveedores/{p.proveedor_id}", etiqueta="Ver proveedor")
    return Enlace(ruta=f"/pedidos/{p.pedido_id}", etiqueta="Ver pedido")


# ---------------------------------------------------------------- detectores
def detectar_alzas(precios: list[_Precio], umbral_pct: float) -> list[Recomendacion]:
    nombres = kpi.nombres_productos()
    por_par: dict[tuple[str, str], list[_Precio]] = defaultdict(list)
    for p in precios:
        por_par[(p.producto_id, p.proveedor_id)].append(p)
    ultimos = {par: lista[-1] for par, lista in por_par.items()}
    salida = []
    for (producto_id, proveedor_id), lista in por_par.items():
        ultimo = lista[-1]
        desde = ultimo.fecha - timedelta(days=30 * MESES_PROMEDIO)
        previos = [p for p in lista[:-1] if p.fecha >= desde and p.pedido_id != ultimo.pedido_id]
        if len(previos) < MINIMO_PRECIOS_PROMEDIO:
            continue
        promedio = sum(p.precio for p in previos) / len(previos)
        alza = (ultimo.precio - promedio) / promedio * 100
        if alza <= umbral_pct:
            continue
        producto, proveedor = nombres.get(producto_id, producto_id), kpi.nombre_proveedor(proveedor_id)
        ejemplo_prev = any(p.ejemplo for p in previos)
        datos = [
            DatoRespaldo(etiqueta="Último precio", valor=f"{_pesos(ultimo.precio)} sin IVA ({_fecha(ultimo.fecha)})", ejemplo=ultimo.ejemplo),
            DatoRespaldo(etiqueta=f"Promedio de {MESES_PROMEDIO} meses", valor=f"{_pesos(promedio)} ({len(previos)} cotizaciones)", ejemplo=ejemplo_prev),
            DatoRespaldo(etiqueta="Alza sobre el promedio", valor=f"{fmt(alza, 1)} %", ejemplo=ultimo.ejemplo or ejemplo_prev),
            DatoRespaldo(etiqueta="Umbral", valor=f"{fmt(umbral_pct, 1)} %"),
        ]
        texto = (
            f"{proveedor} lo cotiza a {_pesos(ultimo.precio)} sin IVA, {fmt(alza, 1)} % sobre su promedio de "
            f"{MESES_PROMEDIO} meses ({_pesos(promedio)})."
        )
        alternativa = min(
            (u for (prod, prov), u in ultimos.items()
             if prod == producto_id and prov != proveedor_id and u.precio < ultimo.precio
             and (ultimo.fecha - u.fecha).days <= VIGENCIA_PRECIO_DIAS),
            key=lambda u: u.precio, default=None,
        )
        if alternativa:
            nombre_alt = kpi.nombre_proveedor(alternativa.proveedor_id)
            datos.append(DatoRespaldo(etiqueta=f"Precio en {nombre_alt}", valor=f"{_pesos(alternativa.precio)} sin IVA ({_fecha(alternativa.fecha)})", ejemplo=alternativa.ejemplo))
            texto += f" {nombre_alt} lo ofrece a {_pesos(alternativa.precio)}."
        salida.append(Recomendacion(
            id=f"alza.{producto_id}.{proveedor_id}.{ultimo.fecha.date().isoformat()}", tipo="alza_precio",
            titulo=f"{producto} subió por encima de su promedio en {proveedor}", texto=texto, datos=datos,
            enlace=_enlace_precio(ultimo), producto_id=producto_id, proveedor_id=proveedor_id,
            ejemplo=any(d.ejemplo for d in datos), fecha=ultimo.fecha, prioridad=2,
        ))
    return salida


def detectar_ofertas(precios: list[_Precio], ordenes: list[tuple[datetime, str, str, bool]], hasta: date) -> list[Recomendacion]:
    nombres = kpi.nombres_productos()
    minimos = _minimos()
    desde = datetime.combine(hasta, datetime.min.time()) - timedelta(days=30 * MESES_PROMEDIO)
    recientes = [o for o in ordenes if o[0] >= desde]
    ultimos: dict[tuple[str, str], _Precio] = {}
    for p in precios:
        ultimos[(p.producto_id, p.proveedor_id)] = p
    salida = []
    for producto_id in sorted({o[1] for o in recientes}):
        del_producto = [o for o in recientes if o[1] == producto_id]
        conteo = Counter(o[2] for o in del_producto)
        habitual, veces = conteo.most_common(1)[0]
        if veces < MINIMO_ORDENES_REGULAR or (producto_id, habitual) not in ultimos:
            continue
        actual = ultimos[(producto_id, habitual)]
        candidatos = [
            u for (prod, prov), u in ultimos.items()
            if prod == producto_id and prov != habitual and abs((actual.fecha - u.fecha).days) <= VIGENCIA_PRECIO_DIAS
        ]
        mejor = min(candidatos, key=lambda u: u.precio, default=None)
        if mejor is None:
            continue
        diferencia = (actual.precio - mejor.precio) / actual.precio * 100
        if diferencia < DIFERENCIA_OFERTA_PCT:
            continue
        producto = nombres.get(producto_id, producto_id)
        nombre_hab, nombre_mejor = kpi.nombre_proveedor(habitual), kpi.nombre_proveedor(mejor.proveedor_id)
        ejemplo_ordenes = any(o[3] for o in del_producto if o[2] == habitual)
        datos = [
            DatoRespaldo(etiqueta=f"Compras a {nombre_hab}", valor=f"{veces} de {len(del_producto)} órdenes en {MESES_PROMEDIO} meses", ejemplo=ejemplo_ordenes),
            DatoRespaldo(etiqueta=f"Precio en {nombre_hab}", valor=f"{_pesos(actual.precio)} sin IVA ({_fecha(actual.fecha)})", ejemplo=actual.ejemplo),
            DatoRespaldo(etiqueta=f"Precio en {nombre_mejor}", valor=f"{_pesos(mejor.precio)} sin IVA ({_fecha(mejor.fecha)})", ejemplo=mejor.ejemplo),
            DatoRespaldo(etiqueta="Diferencia", valor=f"{fmt(diferencia, 1)} % menos", ejemplo=actual.ejemplo or mejor.ejemplo),
        ]
        texto = (
            f"{nombre_mejor}: {_pesos(mejor.precio)} sin IVA, {fmt(diferencia, 1)} % menos que los "
            f"{_pesos(actual.precio)} de {nombre_hab}."
        )
        if (minimo := minimos.get((producto_id, mejor.proveedor_id))):
            datos.append(DatoRespaldo(etiqueta=f"Mínimo de compra en {nombre_mejor}", valor=f"{fmt(minimo)} unidades"))
            texto += f" Ojo: exige un mínimo de {fmt(minimo)} unidades."
        salida.append(Recomendacion(
            id=f"oferta.{producto_id}.{habitual}.{mejor.proveedor_id}", tipo="oferta_otro_proveedor",
            titulo=f"{producto}: la comprás a {nombre_hab} y {nombre_mejor} está más barato",
            texto=texto, datos=datos,
            enlace=Enlace(ruta=f"/proveedores/{mejor.proveedor_id}", etiqueta="Ver proveedor"),
            producto_id=producto_id, proveedor_id=mejor.proveedor_id,
            ejemplo=any(d.ejemplo for d in datos), fecha=max(actual.fecha, mejor.fecha), prioridad=3,
        ))
    return salida


_NOMBRE_CANAL = {"llamada": "llamada", "whatsapp": "WhatsApp", "email": "email"}


def _duracion(minutos: float) -> str:
    if minutos < 60:
        return f"{fmt(minutos)} min"
    horas, resto = divmod(round(minutos), 60)
    return f"{horas} h" + (f" {resto} min" if resto else "")


def detectar_canales(hasta: date) -> list[Recomendacion]:
    desde = datetime.combine(hasta, datetime.min.time()) - timedelta(days=30 * MESES_PROMEDIO)
    obs = [o for o in kpi.obs_tiempos_canal() if desde <= o.fecha and o.fecha.date() <= hasta]
    proveedores = kpi._proveedores()
    salida = []
    for proveedor_id, pub in proveedores.items():
        preferido = kpi.canal_de(pub["canal_preferido"])
        tiempos: dict[str, list[kpi._Obs]] = defaultdict(list)
        for o in obs:
            if o.datos["proveedor_id"] == proveedor_id:
                tiempos[o.datos["canal"]].append(o)
        promedios = {
            canal: sum(o.datos["minutos"] for o in lista) / len(lista)
            for canal, lista in tiempos.items() if len(lista) >= MINIMO_MUESTRAS_CANAL
        }
        if preferido not in promedios or len(promedios) < 2:
            continue
        rapido = min(promedios, key=promedios.get)
        if rapido == preferido or promedios[rapido] > promedios[preferido] * FACTOR_CANAL:
            continue
        nombre = pub["nombre"]
        datos = [
            DatoRespaldo(
                etiqueta=f"Por {_NOMBRE_CANAL[canal]}" + (" (canal preferido)" if canal == preferido else ""),
                valor=f"{_duracion(promedios[canal])} promedio ({len(tiempos[canal])} respuestas)",
                ejemplo=any(o.ejemplo for o in tiempos[canal]),
            )
            for canal in sorted(promedios, key=promedios.get)
        ]
        salida.append(Recomendacion(
            id=f"canal.{proveedor_id}.{rapido}", tipo="canal_mas_rapido",
            titulo=f"{nombre} responde más rápido por {_NOMBRE_CANAL[rapido]}",
            texto=(
                f"Promedio de respuesta: {_duracion(promedios[rapido])} por {_NOMBRE_CANAL[rapido]} y "
                f"{_duracion(promedios[preferido])} por {_NOMBRE_CANAL[preferido]}, su canal preferido. "
                f"Conviene contactarlo primero por {_NOMBRE_CANAL[rapido]}."
            ),
            datos=datos, enlace=Enlace(ruta=f"/proveedores/{proveedor_id}", etiqueta="Ver proveedor"),
            proveedor_id=proveedor_id, ejemplo=any(d.ejemplo for d in datos),
            fecha=max(o.fecha for lista in tiempos.values() for o in lista), prioridad=4,
        ))
    return salida


def detectar_pendientes() -> list[Recomendacion]:
    pendientes = kpi.pendientes()
    if not pendientes:
        return []
    clave = hashlib.sha1("|".join(sorted(p.id for p in pendientes)).encode()).hexdigest()[:10]
    n = len(pendientes)
    return [Recomendacion(
        id=f"pendientes.{clave}", tipo="pendiente_aprobacion",
        titulo=f"{n} {'decisión espera' if n == 1 else 'decisiones esperan'} tu aprobación",
        texto="Sin compra automática, por encima del tope o con una estrategia de negociación para aprobar: "
        + "; ".join(p.titulo for p in pendientes) + ".",
        datos=[DatoRespaldo(etiqueta=p.titulo, valor=p.detalle) for p in pendientes],
        enlace=Enlace(ruta=pendientes[0].enlace, etiqueta="Revisar"),
        proveedor_id=pendientes[0].proveedor_id, ejemplo=False, fecha=datetime.now(), prioridad=1,
    )]


# ---------------------------------------------------------------- redacción con LLM
def _clave_llm(recos: list[Recomendacion]) -> str:
    base = json.dumps([[r.id, r.tipo, [d.model_dump() for d in r.datos]] for r in recos], ensure_ascii=False, sort_keys=True)
    return "reco_" + hashlib.sha1(base.encode()).hexdigest()[:16]


def _hay_llm() -> bool:
    return bool(config.settings.anthropic_api_key)


async def _redactar(clave: str, recos: list[Recomendacion]) -> None:
    from app.explicacion import numeros_inventados
    from app.llm import cargar_prompt, pedir_json

    entrada = [
        {"id": r.id, "tipo": r.tipo, "titulo_base": r.titulo, "texto_base": r.texto,
         "datos": {d.etiqueta: d.valor for d in r.datos}}
        for r in recos
    ]
    try:
        salida = await asyncio.wait_for(
            pedir_json(
                system=cargar_prompt("recomendaciones_system"),
                contenido=[{"type": "text", "text": cargar_prompt(
                    "recomendaciones_user", recomendaciones=json.dumps(entrada, ensure_ascii=False, indent=1))}],
                esquema=SalidaLLM,
            ),
            TIMEOUT_LLM_S,
        )
    except Exception as exc:  # noqa: BLE001 — sin redacción queda la plantilla
        log.warning("No se pudieron redactar las recomendaciones con el LLM: %s", exc)
        store.cache_guardar(clave, {"textos": {}, "error": str(exc)})
        return
    por_id = {r.id: r for r in recos}
    textos = {}
    for r in salida.recomendaciones:
        base = por_id.get(r.id)
        if base is None:
            continue
        datos = {d.etiqueta: f"{d.etiqueta}: {d.valor}" for d in base.datos}
        datos["titulo_base"], datos["texto_base"] = base.titulo, base.texto
        if inventados := numeros_inventados(f"{r.titulo}\n{r.texto}", datos):
            log.warning("Recomendación %s con números que no están en los datos: %s", r.id, inventados)
            continue
        textos[r.id] = {"titulo": r.titulo.strip(), "texto": r.texto.strip()}
    store.cache_guardar(clave, {"textos": textos})


def _aplicar_llm(recos: list[Recomendacion]) -> None:
    """Usa la redacción en cache si está; si no, la pide en segundo plano (la próxima consulta la trae)."""
    if not recos or not _hay_llm():
        return
    clave = _clave_llm(recos)
    guardado = store.cache_leer(clave)
    if guardado is None:
        if not any(not t.done() and t.get_name() == clave for t in _tareas):
            try:
                tarea = asyncio.get_running_loop().create_task(_redactar(clave, recos), name=clave)
            except RuntimeError:  # sin loop (uso sincrónico): queda la plantilla
                return
            _tareas.add(tarea)
            tarea.add_done_callback(_tareas.discard)
        return
    for r in recos:
        if (t := guardado.get("textos", {}).get(r.id)):
            r.titulo, r.texto, r.texto_origen = t["titulo"], t["texto"], "llm"


# ---------------------------------------------------------------- entrada pública
def _descartadas() -> dict[str, Any]:
    return {d["id"]: d for d in store.valores(COLECCION_DESCARTADAS)}


def generar(hasta: date | None = None, umbral_pct: float | None = None) -> list[Recomendacion]:
    hasta = hasta or date.today()
    umbral = umbral_pct if umbral_pct is not None else umbral_por_defecto()
    precios = _precios(hasta)
    recos = (
        detectar_pendientes()
        + detectar_alzas(precios, umbral)
        + detectar_ofertas(precios, _ordenes(hasta), hasta)
        + detectar_canales(hasta)
    )
    descartadas = _descartadas()
    for r in recos:
        if r.id in descartadas:
            r.estado = "descartada"
    return sorted(recos, key=lambda r: (r.prioridad, -r.fecha.timestamp()))


def listar(hasta: date | None = None, umbral_pct: float | None = None, incluir_descartadas: bool = False) -> Recomendaciones:
    todas = generar(hasta, umbral_pct)
    visibles = [r for r in todas if incluir_descartadas or r.estado == "nueva"]
    _aplicar_llm([r for r in visibles if r.estado == "nueva"])
    return Recomendaciones(
        recomendaciones=visibles,
        descartadas=sum(r.estado == "descartada" for r in todas),
        umbral_alza_pct=umbral_pct if umbral_pct is not None else umbral_por_defecto(),
        redaccion="llm" if _hay_llm() else "plantilla",
        ejemplo=any(r.ejemplo for r in visibles),
    )


def descartar(reco_id: str) -> Recomendacion:
    reco = next((r for r in generar() if r.id == reco_id), None)
    if reco is None:
        raise RecomendacionNoEncontrada(reco_id)
    store.guardar_dict(COLECCION_DESCARTADAS, reco_id, {"id": reco_id, "descartada_en": datetime.now().isoformat(timespec="seconds")})
    reco.estado = "descartada"
    return reco
