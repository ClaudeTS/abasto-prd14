Catálogo del pedido (producto_id → nombre, unidad canónica):
{{catalogo}}

Presentaciones con nombre (si el precio es por una de estas, escribí ese nombre exacto en unidad_original; si es por unidad, litro o kilo, escribí "unidad", "l" o "kg"; si es otra presentación, copiala tal como viene):
{{unidades}}

Proveedor: {{proveedor_nombre}} ({{rubro}})
Comprador: {{comprador}}
Canal: {{canal}}

Mensaje:
"""
{{mensaje}}
"""

Esquema de respuesta:
{
  "items": [
    {
      "producto_id": "string | null",
      "descripcion_original": "string",
      "precio": number | null,
      "moneda": "UYU" | "USD",
      "unidad_original": "string",
      "incluye_iva_original": boolean,
      "cantidad_minima": number | null,      // en la misma unidad que unidad_original
      "evidencia": "string"
    }
  ],
  "costo_envio": number | null,             // 0 si dice envío sin cargo
  "pedido_minimo_total": number | null,
  "plazo_pago_dias": number | null,         // contado = 0
  "lead_time_dias": number | null,
  "validez_dias": number | null,
  "observaciones": ["string"],
  "confianza": number,
  "campos_dudosos": ["string"]
}

Respondé solo con el JSON, sin texto antes ni después, sin bloques de código.
