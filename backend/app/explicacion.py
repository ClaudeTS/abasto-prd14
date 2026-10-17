"""Explicación del plan de compra en lenguaje natural (rol A, prompt `explicar_plan`).

Contrato con C: `explicar_plan(datos)` recibe las variables del prompt ya formateadas
(`optimizacion.datos_para_explicar`). Si falla, C usa su plantilla, así que ante un número que no
está en los datos se levanta LLMError en vez de mostrar un dato inventado. Un porcentaje tiene que
ser uno de los porcentajes de los datos; un monto o cualquier otro número, alguno de los números de
los datos (también los de los nombres de producto); "44 mil pesos" se compara como 44.000. Se
toleran los enteros chicos que no son porcentajes ni montos ("3 proveedores").
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from app.llm import LLMError, cargar_prompt, pedir_texto

# 498.454 · 1.234.567,89 (formato uruguayo: punto de miles, coma decimal); si no, 8,05 · 8.05 · 15
_MILES = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d)"
_NUMERO = re.compile(rf"{_MILES}|\d+(?:[.,]\d+)?")
_PORCENTAJE = re.compile(r"\s*(%|por ?ciento)")
_MONEDA_ANTES = re.compile(r"(U\$[SD]|US\$|\$U|\$|\bUSD|\bUYU)\s*$", re.IGNORECASE)
_MONEDA_DESPUES = re.compile(r"\s*(USD|UYU|d[oó]lares|pesos)\b", re.IGNORECASE)
_MILES_ESCRITO = re.compile(r"\s*(mil(?:lones|l[oó]n)?)\b", re.IGNORECASE)


async def explicar_plan(datos: dict[str, str]) -> str:
    texto = await pedir_texto(
        system=cargar_prompt("explicar_plan_system"),
        mensajes=[
            {"role": "user", "content": cargar_prompt("explicar_plan_user", **datos)}
        ],
    )
    if inventados := numeros_inventados(texto, datos):
        raise LLMError(
            "La explicación trae números que no están en el plan: "
            + ", ".join(inventados)
        )
    return texto


def numeros_inventados(texto: str, datos: dict[str, str]) -> list[str]:
    """Números del texto que no salen de `datos` (ni redondeando).

    Un porcentaje se compara solo con los porcentajes de los datos: las variables `*_pct` y los
    números que llevan %. Los enteros chicos que no son porcentaje ni monto se aceptan: son
    conteos ("3 proveedores"). "1 USD = $ 40,00" vale si los datos traen el tipo de cambio.
    """
    conocidos, porcentajes = set(), set()
    if "tipo_cambio" in datos:
        conocidos.add(Decimal(1))
    for clave, valor in datos.items():
        for _, numero, es_porcentaje, _, _ in _numeros(valor):
            conocidos.add(numero)
            if es_porcentaje or "pct" in clave:
                porcentajes.add(numero)
    inventados = []
    for crudo, numero, es_porcentaje, es_monto, escala in _numeros(texto):
        if es_porcentaje:
            validos = porcentajes
        elif numero < 100 and numero == numero.to_integral_value() and not es_monto:
            continue
        else:
            validos = conocidos
        if not any(_coincide(numero, c / escala) for c in validos):
            inventados.append(crudo)
    return list(dict.fromkeys(inventados))


def _numeros(texto: str):
    """(como está escrito, valor, si es un porcentaje, si es un monto, escala) de cada número.

    La escala es 1000 en "30 mil" y 1.000.000 en "2 millones"; esos números son montos.
    """
    for m in _NUMERO.finditer(texto):
        porcentaje = bool(_PORCENTAJE.match(texto, m.end()))
        palabra = _MILES_ESCRITO.match(texto, m.end())
        escala = 1 if not palabra else 1000 if palabra[1].lower() == "mil" else 10**6
        monto = bool(
            escala > 1
            or _MONEDA_ANTES.search(texto, 0, m.start())
            or _MONEDA_DESPUES.match(texto, m.end())
        )
        yield m.group(), _a_decimal(m.group()), porcentaje, monto, escala


def _a_decimal(texto: str) -> Decimal:
    if re.fullmatch(_MILES, texto):
        texto = texto.replace(".", "")
    return Decimal(texto.replace(",", "."))


def _coincide(valor: Decimal, conocido: Decimal) -> bool:
    """`valor` es `conocido`, o `conocido` redondeado a los decimales de `valor`."""
    decimales = max(-valor.as_tuple().exponent, 0)
    return conocido.quantize(Decimal(1).scaleb(-decimales), ROUND_HALF_UP) == valor
