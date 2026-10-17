"""Corre la extracción real (con el LLM) sobre los 6 mensajes de data/respuestas_fijas.json.

Uso, desde backend/ y con ANTHROPIC_API_KEY en .env:
    python -m scripts.probar_extraccion                 # los 6
    python -m scripts.probar_extraccion tecnoimport     # solo algunos

Arma cada mensaje como el simulador de C (PDF y foto con `app.archivos`), le pide el texto a
`pipeline.obtener_texto` y llama a `extraer_crudo`. Verifica AGENTS.md §8: < 20 s, evidencia en
cada ítem y, después de la normalización de C (Compuservice con el IVA confirmado), los precios de
resultado_esperado_demo. Guarda la salida cruda en backend/data/runtime/ensayos/extracciones.json.
"""

import asyncio
import json
import sys
import time
from datetime import datetime
from decimal import Decimal

from app import archivos, config, pipeline, store
from app.extraccion import extraer_crudo
from app.llm import MODEL, LLMError
from app.models import MensajeCrudo
from scripts.demo import normalizar

LIMITE_SEGUNDOS = 20


def armar_mensaje(respuesta: dict) -> MensajeCrudo:
    proveedor_id, canal, contenido = (
        respuesta["proveedor_id"],
        respuesta["canal"],
        respuesta["contenido"],
    )
    mensaje_id = f"msg_prueba_{proveedor_id}"
    archivo = None
    if canal == "pdf":
        archivo = f"{mensaje_id}.pdf"
        archivos.generar_pdf_presupuesto(
            contenido, config.settings.archivos_dir / archivo
        )
    elif canal == "foto":
        archivo = f"{mensaje_id}.jpg"
        archivos.generar_foto_presupuesto(
            contenido, config.settings.archivos_dir / archivo
        )
    return MensajeCrudo(
        id=mensaje_id,
        pedido_id=pipeline.datos_pedido()["pedido"]["id"],
        proveedor_id=proveedor_id,
        canal=canal,
        contenido_texto=None if archivo else contenido,
        archivo=archivo,
        recibido_en=datetime.now(),
        estado="pendiente",
    )


async def correr(mensaje: MensajeCrudo):
    texto, imagen = pipeline.obtener_texto(mensaje)
    inicio = time.perf_counter()
    try:
        crudo = await extraer_crudo(
            texto=texto,
            imagen=imagen,
            canal=mensaje.canal,
            proveedor=pipeline.proveedores()[mensaje.proveedor_id],
            catalogo=pipeline.catalogo(),
        )
    except LLMError as e:
        return mensaje, time.perf_counter() - inicio, e
    return mensaje, time.perf_counter() - inicio, crudo


def revisar(
    mensaje: MensajeCrudo, segundos: float, crudo: dict, esperado: dict
) -> list[str]:
    problemas = []
    if segundos > LIMITE_SEGUNDOS:
        problemas.append(f"tardó {segundos:.1f} s (> {LIMITE_SEGUNDOS} s)")
    cotizacion = normalizar(mensaje.proveedor_id, crudo)
    obtenido = {i.producto_id: i.precio_unitario_sin_iva for i in cotizacion.items}
    for producto, precio in esperado.items():
        if obtenido.get(producto) != precio:
            problemas.append(
                f"{producto}: esperado {precio}, obtenido {obtenido.get(producto)}"
            )
    for producto in obtenido.keys() - esperado.keys():
        problemas.append(f"{producto}: cotizado pero no esperado")
    problemas += [
        f"{i.producto_id}: sin evidencia" for i in cotizacion.items if not i.evidencia
    ]
    if cotizacion.estado == "revisar":
        problemas.append(f"queda para revisar ({', '.join(cotizacion.campos_dudosos)})")
    return problemas


async def main(filtro: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    esperados = store.semilla("pedido_demo")["resultado_esperado_demo"][
        "precios_normalizados_sin_iva"
    ]
    respuestas = [
        r
        for r in store.semilla("respuestas_fijas")["respuestas"]
        if not filtro or r["proveedor_id"] in filtro
    ]
    print(f"Modelo: {MODEL} · {len(respuestas)} mensajes\n")
    resultados = await asyncio.gather(*(correr(armar_mensaje(r)) for r in respuestas))

    fallas, guardadas = 0, {}
    for mensaje, segundos, resultado in resultados:
        print(f"── {mensaje.proveedor_id} ({mensaje.canal}) · {segundos:.1f} s")
        if isinstance(resultado, Exception):
            print(f"   ERROR: {resultado}")
            fallas += 1
            continue
        for item in resultado["items"]:
            print(
                f"   {str(item['producto_id']):<14} {item['moneda']} {item['precio']}"
                f" por {item['unidad_original']}"
                f" · IVA {'incluido' if item['incluye_iva_original'] else 'aparte'}"
                f" · mínimo {item['cantidad_minima']}"
            )
            print(f"   {'':<14} evidencia: «{item['evidencia']}»")
        print(
            f"   envío {resultado['costo_envio']} · mínimo {resultado['pedido_minimo_total']} · "
            f"pago {resultado['plazo_pago_dias']} d · entrega {resultado['lead_time_dias']} d · "
            f"confianza {resultado['confianza']:.2f} · dudosos {resultado['campos_dudosos'] or '-'}"
        )
        esperado = {
            producto: Decimal(str(por_proveedor[mensaje.proveedor_id]))
            for producto, por_proveedor in esperados.items()
            if mensaje.proveedor_id in por_proveedor
        }
        problemas = revisar(mensaje, segundos, resultado, esperado)
        print("   OK" if not problemas else "   PROBLEMAS: " + " | ".join(problemas))
        fallas += bool(problemas)
        guardadas[mensaje.proveedor_id] = resultado

    salida = config.settings.runtime_dir / "ensayos" / "extracciones.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(guardadas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"\n{len(resultados) - fallas}/{len(resultados)} OK · salida cruda en {salida}"
    )
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
