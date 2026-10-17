"""Cliente LLM único de Abasto (rol A). Ningún otro archivo instancia el SDK (AGENTS.md §6).

El modelo y la API key salen de `app.config` (backend/.env). Sin temperature: Sonnet 5.5 la
rechaza; la variabilidad se controla con el prompt y `effort`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app import config

log = logging.getLogger("abasto.llm")

MODEL = config.settings.llm_model
# Tope de cada llamada, reintentos incluidos (AGENTS.md §6.8).
TIMEOUT_SEGUNDOS = 60.0
# Un reintento para 429/529/5xx; más no entra en los plazos de C (90 s para /negociar).
MAX_REINTENTOS = 1
# Con thinking adaptativo, el razonamiento cuenta dentro de max_tokens: menos que esto corta respuestas.
MAX_TOKENS = 16000
# Si el clasificador de seguridad rechaza un pedido, la API lo reintenta sola en otro modelo.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

T = TypeVar("T", bound=BaseModel)

_cliente: anthropic.AsyncAnthropic | None = None


class LLMError(Exception):
    """Error legible para mostrar en la UI tal cual."""


def cliente() -> anthropic.AsyncAnthropic:
    global _cliente
    if _cliente is None:
        _cliente = anthropic.AsyncAnthropic(
            api_key=config.settings.anthropic_api_key or None,
            timeout=anthropic.Timeout(TIMEOUT_SEGUNDOS, connect=5.0),
            max_retries=MAX_REINTENTOS,
        )
    return _cliente


def cargar_prompt(nombre: str, /, **variables: object) -> str:
    """Lee app/prompts/<nombre>.md y reemplaza cada {{variable}} (puede haber una {{nombre}})."""
    texto = (PROMPTS_DIR / f"{nombre}.md").read_text(encoding="utf-8")
    for clave, valor in variables.items():
        texto = texto.replace("{{" + clave + "}}", str(valor))
    return texto


async def completar(
    system: str, user: str, *, temperature: float, max_tokens: int
) -> str:
    """Contrato con C (simulador en SIM_MODE=llm): un system y un user, devuelve texto.

    `temperature` se ignora (Sonnet 5.5 la rechaza) y `max_tokens` se sube al mínimo que deja
    lugar al thinking adaptativo.
    """
    del temperature
    return await pedir_texto(
        system=system,
        mensajes=[{"role": "user", "content": user}],
        max_tokens=max(max_tokens, MAX_TOKENS),
    )


async def pedir_json(
    *,
    system: str,
    contenido: list[dict],
    esquema: type[T],
    historial: list[dict] | None = None,
    max_tokens: int = MAX_TOKENS,
    effort: str = "low",
) -> T:
    """Pide una respuesta JSON validada contra `esquema`.

    `contenido` es el último mensaje del usuario; `historial`, los turnos anteriores (opcional).
    Usa salida estructurada (el JSON viene garantizado por la API) y además valida con Pydantic.
    Se valida después de `_llamar`, para que un refusal o un corte por max_tokens se informe como
    tal. Si la validación falla, reintenta una vez pidiendo solo JSON válido; si vuelve a fallar,
    levanta LLMError en vez de inventar datos.
    """
    formato = {
        "type": "json_schema",
        "schema": anthropic.transform_schema(esquema.model_json_schema()),
    }
    mensaje = list(contenido)
    for intento in (1, 2):
        respuesta = await _llamar(
            "create",
            max_tokens=max_tokens,
            system=system,
            messages=[*(historial or []), {"role": "user", "content": mensaje}],
            output_config={"effort": effort, "format": formato},
        )
        try:
            return esquema.model_validate_json(_texto(respuesta))
        except ValidationError as e:
            log.warning("JSON inválido (intento %s): %s", intento, e)
        mensaje = list(contenido) + [
            {
                "type": "text",
                "text": "Respondé solo con JSON válido que cumpla el esquema.",
            }
        ]
    raise LLMError("El LLM no devolvió un JSON válido después de reintentar.")


async def pedir_texto(
    *,
    system: str,
    mensajes: list[dict],
    max_tokens: int = MAX_TOKENS,
    effort: str = "low",
) -> str:
    """Pide una respuesta en texto libre (turnos de negociación, mensaje final, explicación).

    `mensajes` es la conversación completa en formato de la API: arranca y termina con "user".
    """
    respuesta = await _llamar(
        "create",
        max_tokens=max_tokens,
        system=system,
        messages=mensajes,
        output_config={"effort": effort},
    )
    texto = _texto(respuesta).strip()
    if not texto:
        raise LLMError("El LLM devolvió una respuesta vacía.")
    return texto


def _texto(respuesta) -> str:
    return "".join(b.text for b in respuesta.content if b.type == "text")


async def _llamar(metodo: str, **parametros):
    """Una llamada a `client.beta.messages.<metodo>` con el modelo, el fallback, el tope de
    TIMEOUT_SEGUNDOS y los errores comunes a todo Abasto."""
    inicio = time.perf_counter()
    try:
        llamada = getattr(cliente().beta.messages, metodo)
        respuesta = await asyncio.wait_for(
            llamada(
                model=MODEL, betas=[FALLBACK_BETA], fallbacks="default", **parametros
            ),
            TIMEOUT_SEGUNDOS,
        )
    except anthropic.CredentialsError as e:
        raise LLMError(
            f"No se pudieron leer las credenciales de Anthropic: {e}. Revisá ANTHROPIC_API_KEY"
            " en backend/.env."
        ) from e
    except anthropic.AuthenticationError as e:
        raise LLMError("API key de Anthropic inválida (ANTHROPIC_API_KEY).") from e
    except TypeError as e:
        # Sin credenciales, el SDK levanta TypeError al armar el pedido.
        if "authentication" not in str(e):
            raise
        raise LLMError(
            "Falta ANTHROPIC_API_KEY: copiá backend/.env.example a backend/.env y completala."
        ) from e
    except anthropic.BadRequestError as e:
        raise LLMError(f"Pedido inválido al LLM: {e.message}") from e
    except anthropic.RateLimitError as e:
        raise LLMError(
            "Límite de uso de la API alcanzado; probá de nuevo en un minuto."
        ) from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"La API del LLM respondió {e.status_code}: {e.message}") from e
    except (anthropic.APITimeoutError, TimeoutError) as e:
        raise LLMError(f"El LLM no respondió en {TIMEOUT_SEGUNDOS:.0f} s.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("No hay conexión con la API del LLM.") from e

    log.info(
        "%s · %.1f s · in=%s out=%s · %s",
        respuesta.model,
        time.perf_counter() - inicio,
        respuesta.usage.input_tokens,
        respuesta.usage.output_tokens,
        respuesta._request_id,
    )
    if respuesta.stop_reason == "refusal":
        raise LLMError("El modelo rechazó el pedido (refusal).")
    if respuesta.stop_reason == "max_tokens":
        raise LLMError("La respuesta del LLM se cortó por max_tokens.")
    return respuesta
