"""Explicación del plan con el LLM (prompt `explicar_plan`, PROMPTS.md §6).

El solver decide, el LLM explica (AGENTS §6.5): recibe los datos ya formateados por
optimizacion.datos_para_explicar y no puede cambiar ningún número. Si falla, el backend usa la
explicación de plantilla (integracion_a.explicar).
"""

from __future__ import annotations

from pydantic import BaseModel

from app import llm


class Explicacion(BaseModel):
    texto: str


async def explicar_plan(datos: dict[str, str]) -> str:
    respuesta: Explicacion = await llm.pedir_json(
        system=llm.cargar_prompt("explicar_plan_system"),
        contenido=[
            {
                "type": "text",
                "text": llm.cargar_prompt("explicar_plan_user", **datos)
                + '\n\nDevolvé la explicación en el campo "texto".',
            }
        ],
        esquema=Explicacion,
        max_tokens=1024,
    )
    return respuesta.texto.strip()
