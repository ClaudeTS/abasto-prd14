# Diseño — paleta institucional

La interfaz sigue la plantilla institucional de Abasto (presentación "ABASTO_Plantilla_Institucional"). Los colores
están definidos una sola vez en `frontend/src/index.css` (`@theme` y `:root`) y se usan como clases de Tailwind
(`bg-celeste`, `text-azul-profundo`, `bg-negro`, …). Propuesta visual completa: lienzo "Abasto — Mockups PRD 1.4",
sección "Propuesta de color".

## Paleta

| Token | Hex | Uso |
|---|---|---|
| `grafito` | #1F1F1F | texto, encabezados de tabla, KPI oscuro |
| `celeste` | #01ADBD | acción principal (`--primary`), lo importante, etapa actual |
| `celeste-ink` | #01707B | celeste como texto sobre blanco (enlaces, "en marcha") |
| `azul` | #00A0DF | íconos y acentos de IA |
| `azul-profundo` | #0E4E6B | bandas y chips de IA |
| `negro` / `negro-2` / `negro-3` | #161616 / #26292B / #3A3F42 | menú, hero, encabezado del pedido |
| `fondo` | #F7F7F7 | lienzo (`--background`) |
| `gris-claro` | #DDE2E1 | bordes, series de contexto |
| `gris-texto` / `gris-oscuro` | #6E6E73 / #B4B4B4 | texto secundario sobre claro / sobre oscuro |

Tipografía: Poppins (títulos, `font-heading`) y Roboto (texto, `font-sans`), servidas con Fontsource.

## Reglas

1. **Nunca texto blanco sobre celeste** (2,96:1). Sobre celeste va grafito (5,57:1): por eso `--primary-foreground` es grafito.
2. **Una sola cosa en celeste por bloque**: el KPI destacado, el canal más rápido, la etapa actual. El resto, gris.
3. **Azul = lo hizo la IA**: recomendaciones, gemelo, mensajes propuestos, llamadas del agente.
4. **Estados del pedido en 5 familias** (`features/pedidos/presentacion.tsx`): gris inactivo (nuevo, cerrado), azul la IA
   trabaja (cotizando, cotizado, negociando), celeste en marcha (aprobado, pendiente de entrega, recibido), ámbar te
   necesita (datos incompletos, pendiente de aprobación) y rojo cancelado. Ámbar y rojo no están en la plantilla: son
   colores funcionales de alerta, nunca decorativos.
5. **Datos de ejemplo**: etiqueta con rayado gris (`tono="ejemplo"`), para no confundirse con ningún estado.
6. Tablas con encabezado grafito; botones en píldora; bloques oscuros con las facetas de la portada (`components/Facetas.tsx`).
