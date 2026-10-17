"""Prueba las llamadas reales (ElevenLabs + Twilio) sin levantar el server. Ver docs/LLAMADAS.md.

Desde backend/, con las variables en backend/.env:

    python -m scripts.probar_llamada --numeros            # números importados en ElevenLabs (y su phone_number_id)
    python -m scripts.probar_llamada papelera_del_sur     # llama al teléfono de ese proveedor (TELEFONOS_PROVEEDORES)

La llamada de prueba usa las mismas instrucciones que la de "pedir cotización" del pedido demo y
muestra la transcripción a medida que llega. No toca el runtime de la demo.
"""

from __future__ import annotations

import asyncio
import sys
import time

import httpx

from app import config, llamadas
from app.models import Llamada
from app.pedidos import PEDIDO_DEMO_ID, obtener


def listar_numeros() -> None:
    s = config.settings
    if not s.elevenlabs_api_key:
        sys.exit("Falta ELEVENLABS_API_KEY en backend/.env")
    r = httpx.get(f"{s.elevenlabs_base_url}/v1/convai/phone-numbers", headers={"xi-api-key": s.elevenlabs_api_key}, timeout=30)
    if r.status_code == 401:
        sys.exit("ElevenLabs respondió 401: la ELEVENLABS_API_KEY no es válida (o no tiene permiso para Agents).")
    r.raise_for_status()
    numeros = r.json()
    if not numeros:
        print("No hay números importados. En ElevenLabs: Agents → Phone Numbers → Import (Twilio).")
    for n in numeros:
        agente = (n.get("assigned_agent") or {}).get("agent_name", "—")
        print(f"{n['phone_number']:<16} {n.get('provider', ''):<8} phone_number_id={n['phone_number_id']}  agente={agente}  ({n.get('label', '')})")
    print("\nCopiá el phone_number_id del número de Twilio en ELEVENLABS_PHONE_NUMBER_ID.")


async def llamar(proveedor_id: str) -> None:
    cfg = llamadas.configuracion()
    if cfg.faltan:
        sys.exit("Faltan variables en backend/.env: " + ", ".join(cfg.faltan))
    numero = (config.settings.telefonos_proveedores or {}).get(proveedor_id)
    if not numero:
        sys.exit(f"No hay teléfono para '{proveedor_id}' en TELEFONOS_PROVEEDORES (hay: {', '.join(cfg.proveedores_con_telefono)})")
    variables = llamadas.instrucciones_cotizacion(obtener(PEDIDO_DEMO_ID), proveedor_id)
    print(f"Llamando a {variables['proveedor_nombre']} ({llamadas.enmascarar(numero)})…")
    print(f"Primer mensaje: {variables['primer_mensaje']}\n")
    datos = await llamadas._disparar(numero, variables)
    print(f"conversation_id={datos.get('conversation_id')}  callSid={datos.get('callSid')}\n")
    llamada = Llamada(
        id="prueba", pedido_id=PEDIDO_DEMO_ID, proveedor_id=proveedor_id, tipo="cotizacion", modo="real",
        estado="sonando", conversation_id=datos.get("conversation_id"), iniciada_en=__import__("datetime").datetime.now(),
    )
    mostrados, inicio = 0, time.time()
    while llamada.estado in llamadas.ACTIVAS and time.time() - inicio < llamadas.DURACION_MAXIMA_S:
        await asyncio.sleep(2)
        llamadas._aplicar(llamada, await llamadas._consultar(llamada.conversation_id))
        for turno in llamada.transcripcion[mostrados:]:
            quien = "Abasto   " if turno.rol == "abasto" else "Proveedor"
            print(f"  [{turno.segundo or 0:>3}s] {quien}: {turno.texto}")
        mostrados = len(llamada.transcripcion)
        print(f"    · {llamada.estado}", end="\r")
    print(f"\nEstado final: {llamada.estado}  duración: {llamada.duracion_segundos} s")
    if llamada.error:
        print(f"Error: {llamada.error}")
    if llamada.resultado:
        print(f"Resumen: {llamada.resultado.resumen}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--numeros":
        listar_numeros()
    else:
        asyncio.run(llamar(sys.argv[1]))
