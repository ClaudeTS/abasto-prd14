Catálogo (producto_id → nombre, unidad):
{{catalogo}}

Empresa: {{negocio}}
Hoy es {{fecha}}.

Lo que pidió:
"""
{{texto}}
"""

Esquema de respuesta:
{
  "items": [
    {
      "producto_id": "string | null",
      "descripcion": "string",                // cómo lo nombró
      "cantidad": number | null,              // en la unidad del catálogo
      "necesario_para": "AAAA-MM-DD" | null,
      "evidencia": "string"
    }
  ],
  "excluir": ["producto_id"],
  "horizonte_meses": number | null,
  "evidencia_horizonte": "string | null",
  "dudas": ["string"]
}

Respondé solo con el JSON, sin texto antes ni después, sin bloques de código.
