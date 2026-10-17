"""Prueba la Capa 5 contra el LLM real, sin levantar el server.

Uso (desde backend/, con ANTHROPIC_API_KEY en backend/.env):
    python -m scripts.probar_negociacion            # Ofisillas, como en la demo
    python -m scripts.probar_negociacion tecnoimport

Recorre cotizar → confirmar IVA → optimizar con datos fijos, ensaya la negociación con el
proveedor elegido e imprime las 3 estrategias, tiempos y el mensaje propuesto. Usa un directorio
de datos temporal: no toca el runtime de la demo.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

os.environ.setdefault("ABASTO_DATA_DIR", tempfile.mkdtemp(prefix="abasto_negociacion_"))
os.environ["SIM_DELAY_SECONDS"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import config, negociacion  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ContextoNegociacion  # noqa: E402

PEDIDO = "pedido_demo_oct_2026"


def preparar_contexto(proveedor_id: str) -> ContextoNegociacion:
    with TestClient(app) as c:
        c.post("/reset")
        c.post(f"/pedidos/{PEDIDO}/cotizar")
        for _ in range(200):
            m = c.get(f"/pedidos/{PEDIDO}/mensajes").json()
            if len(m) == 6 and all(x["estado"] in ("extraido", "error") for x in m):
                break
            time.sleep(0.1)
        for cot in c.get(f"/pedidos/{PEDIDO}/cotizaciones").json():
            if "iva" in cot["campos_dudosos"]:
                c.post(f"/cotizaciones/{cot['id']}/confirmar", json={"incluye_iva": True})
        c.post(f"/pedidos/{PEDIDO}/optimizar")
        # Sin pasar por /negociar: armamos el contexto igual que el endpoint.
        from app import integracion_a, pedidos, pipeline, store
        from app.models import Cotizacion, Plan

        pedido = pedidos.obtener(PEDIDO)
        plan = Plan.model_validate(store.obtener_dict("planes", PEDIDO))
        return integracion_a.construir_contexto(
            pedido,
            plan,
            store.listar("cotizaciones", Cotizacion, pedido_id=PEDIDO),
            pipeline.proveedores(),
            pipeline.perfil_privado(proveedor_id),
            proveedor_id,
            {p.id: p.nombre for p in pipeline.catalogo()},
        )


async def main(proveedor_id: str) -> None:
    if not config.settings.anthropic_api_key:
        sys.exit("Falta ANTHROPIC_API_KEY en backend/.env")
    contexto = preparar_contexto(proveedor_id)
    print(f"Negociando con {contexto.proveedor.nombre} · valor en juego $ {contexto.valor_en_juego_uyu:,.0f}")
    inicio = time.perf_counter()
    resultado = await negociacion.ensayar(contexto)
    print(f"\nTardó {time.perf_counter() - inicio:.1f} s (objetivo < 40 s)\n")
    for e in resultado["estrategias"]:
        marca = "★" if e["nombre"] == resultado["elegida"] else " "
        print(f"{marca} {e['nombre']:<12} {e['concesion_obtenida_pct']:5.2f} %  "
              f"$ {e['ganancia_esperada_uyu']:>9,.0f}  riesgo {e['riesgo']}")
        for t in e["transcripcion"]:
            print(f"      {t['rol']:>9}: {t['texto']}")
    print(f"\nMensaje propuesto ({len(resultado['mensaje_propuesto'].split())} palabras):\n")
    print(resultado["mensaje_propuesto"])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ofisillas"))
