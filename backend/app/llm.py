"""Cliente LLM único de Abasto. Ningún otro archivo instancia el SDK (AGENTS.md §6)."""

import logging
import os
import time
from pathlib import Path
from typing import TypeVar

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

log = logging.getLogger("abasto.llm")

MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
TIMEOUT_SEGUNDOS = 60.0
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
        _cliente = anthropic.AsyncAnthropic(timeout=TIMEOUT_SEGUNDOS)
    return _cliente


def cargar_prompt(nombre: str, **variables: object) -> str:
    """Lee app/prompts/<nombre>.md y reemplaza cada {{variable}}."""
    texto = (PROMPTS_DIR / f"{nombre}.md").read_text(encoding="utf-8")
    for clave, valor in variables.items():
        texto = texto.replace("{{" + clave + "}}", str(valor))
    return texto


async def pedir_json(
    *,
    system: str,
    contenido: list[dict],
    esquema: type[T],
    max_tokens: int = 16000,
    effort: str = "low",
) -> T:
    """Pide una respuesta JSON validada contra `esquema`.

    Usa salida estructurada (el JSON viene garantizado por la API) y además valida con Pydantic.
    Si la validación falla, reintenta una vez pidiendo solo JSON válido; si vuelve a fallar,
    levanta LLMError en vez de inventar datos.
    """
    mensaje = list(contenido)
    for intento in (1, 2):
        inicio = time.perf_counter()
        try:
            respuesta = await cliente().beta.messages.parse(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": mensaje}],
                output_format=esquema,
                output_config={"effort": effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except ValidationError as e:
            log.warning("JSON inválido (intento %s): %s", intento, e)
            mensaje = list(contenido) + [
                {
                    "type": "text",
                    "text": "Respondé solo con JSON válido que cumpla el esquema.",
                }
            ]
            continue
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
            raise LLMError(
                f"La API del LLM respondió {e.status_code}: {e.message}"
            ) from e
        except anthropic.APITimeoutError as e:
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
        if respuesta.parsed_output is not None:
            return respuesta.parsed_output
        mensaje = list(contenido) + [
            {
                "type": "text",
                "text": "Respondé solo con JSON válido que cumpla el esquema.",
            }
        ]
    raise LLMError("El LLM no devolvió un JSON válido después de reintentar.")
