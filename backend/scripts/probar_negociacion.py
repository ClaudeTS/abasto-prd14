"""Corre la negociación ensayada real (con el LLM) contra el gemelo de un proveedor.

Uso, desde backend/ y con ANTHROPIC_API_KEY en .env:
    python -m scripts.probar_negociacion                # Ofisillas, el caso de la demo
    python -m scripts.probar_negociacion compuservice   # otro proveedor del plan

Arma el mismo contexto que POST /negociar (`scripts.demo.contexto_demo`: extracciones fijas,
normalización y solver de C) y pasa por `integracion_a.negociar`, que pone la ganancia y valida la
salida de `ensayar`. Verifica ARQUITECTURA §7 (< 40 s, mensaje de ≤ 80 palabras) y, para Ofisillas,
que gane "volumen" como en el guion. Guarda el resultado en backend/data/runtime/ensayos/.
"""

import asyncio
import json
import sys
import time

from app import config, integracion_a
from app.llm import MODEL, LLMError
from app.negociacion import LIMITE_SEGUNDOS, NO_ENSAYADA
from scripts.demo import contexto_demo

ESPERADA = {"ofisillas": "volumen"}  # PITCH_Y_DEMO.md, paso 5
MAX_PALABRAS = 80


async def main(proveedor_id: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        contexto = contexto_demo(proveedor_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR: no se puede negociar con {proveedor_id}: {e}")
        return 1
    print(
        f"Modelo: {MODEL} · negociación con {contexto.proveedor.nombre}"
        f" · en juego $ {contexto.valor_en_juego_uyu}\n"
    )
    inicio = time.perf_counter()
    try:
        negociacion = await integracion_a.negociar(contexto)
    except (LLMError, integracion_a.CapaNoDisponible) as e:
        print(f"ERROR: {e}")
        return 1
    except TimeoutError as e:
        print(f"ERROR: se venció el plazo de la negociación ({e})")
        return 1
    segundos = time.perf_counter() - inicio

    for e in negociacion.estrategias:
        marca = "  ← elegida" if e.nombre == negociacion.elegida else ""
        print(
            f"── {e.nombre}: {e.concesion_obtenida_pct:.2f} % · UYU {e.ganancia_esperada_uyu}"
            f" · riesgo {e.riesgo}{marca}"
        )
        print(f"   {e.descripcion}")
        for turno in e.transcripcion:
            quien = "Abasto   " if turno["rol"] == "abasto" else "Proveedor"
            print(f"   {quien} › {turno['texto']}")
        print()
    palabras = len(negociacion.mensaje_propuesto.split())
    print(
        f"Mensaje propuesto ({palabras} palabras):\n{negociacion.mensaje_propuesto}\n"
    )

    problemas = []
    if segundos > LIMITE_SEGUNDOS:
        problemas.append(f"tardó {segundos:.1f} s (> {LIMITE_SEGUNDOS} s)")
    if palabras > MAX_PALABRAS:
        problemas.append(f"el mensaje tiene {palabras} palabras (> {MAX_PALABRAS})")
    fallidas = [
        e.nombre
        for e in negociacion.estrategias
        if e.descripcion.startswith(NO_ENSAYADA)
    ]
    if fallidas:
        problemas.append(f"no se pudieron ensayar: {', '.join(fallidas)}")
    esperada = ESPERADA.get(proveedor_id)
    if esperada and negociacion.elegida != esperada:
        print(f"AVISO: el guion espera '{esperada}' y ganó '{negociacion.elegida}'.")

    salida = (
        config.settings.runtime_dir / "ensayos" / f"negociacion_{proveedor_id}.json"
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(negociacion.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"{segundos:.1f} s · "
        + ("OK" if not problemas else "PROBLEMAS: " + " | ".join(problemas))
    )
    print(f"Guardado en {salida}")
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ofisillas")))
