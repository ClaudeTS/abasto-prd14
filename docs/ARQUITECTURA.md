# Arquitectura — Abasto (MVP hackatón)

## 1. Contexto y objetivos

Demostrar, de punta a punta y en vivo, tres capacidades que no existen sin IA:
(1) entender cotizaciones desordenadas, (4) optimizar la compra con un solver y
(5) ensayar la negociación contra un gemelo del proveedor.

Decisiones de diseño que valen para todo:
- **Todo en memoria + JSON en disco.** Sin base de datos.
- **El LLM nunca decide números finales.** Extrae (con evidencia), explica y conversa. El solver optimiza.
- **Todo lo que el usuario ve tiene trazabilidad** al mensaje original.

## 2. Vista general

```
┌──────────────┐  REST/polling  ┌─────────────────────────────────────────┐
│  Frontend    │ ─────────────▶ │  FastAPI                                │
│  React/Vite  │ ◀───────────── │                                         │
└──────────────┘                │  simulador ─▶ mensajes crudos           │
                                │       │                                 │
                                │  extraccion (LLM + pdfplumber + visión) │
                                │       │  Cotizacion[] con evidencia     │
                                │  optimizacion (PuLP MILP) ─▶ Plan       │
                                │       │  explicar_plan (LLM)            │
                                │  negociacion (LLM × LLM) ─▶ estrategias │
                                │                                         │
                                │  store.py ──▶ backend/data/runtime/*.json│
                                └─────────────────────────────────────────┘
```

Flujo de la demo: `POST /pedidos/{id}/cotizar` dispara el simulador en background → cada mensaje
crudo que llega pasa por extracción → el frontend hace polling y pinta burbujas y tarjetas →
`POST /optimizar` → `POST /negociar/{proveedor}` → `POST /aprobar`.

## 3. Modelo de datos (Pydantic)

```python
class Producto(BaseModel):
    id: str                      # "notebook"
    nombre: str                  # "Notebook 15\" i5 / 16 GB / 512 GB"
    unidad_canonica: Literal["unidad", "l", "kg"]

class LineaPedido(BaseModel):
    producto_id: str
    cantidad: float              # en unidad canónica
    necesario_para: date         # fecha límite de entrega

class Pedido(BaseModel):
    id: str
    negocio: str                 # "Tecnova S.A."
    lineas: list[LineaPedido]
    proveedor_habitual_id: str   # para calcular el baseline de ahorro
    estado: Literal["nuevo", "cotizando", "cotizado", "optimizado", "negociando", "aprobado"]

class Proveedor(BaseModel):
    id: str
    nombre: str
    rubro: str                   # "informática / importador", "papelería", ...
    canal_preferido: Literal["whatsapp_texto", "whatsapp_audio", "pdf", "foto"]
    confiabilidad: float         # 0–1, cumplimiento de entregas (dato "histórico" seedeado)
    # Solo el simulador conoce: tabla de precios real, perfil de concesión, personalidad.

class MensajeCrudo(BaseModel):
    id: str
    pedido_id: str
    proveedor_id: str
    canal: str
    contenido_texto: str | None  # texto del mensaje o transcripción
    archivo: str | None          # ruta a pdf/imagen/audio en runtime/
    recibido_en: datetime
    estado: Literal["pendiente", "leyendo", "extraido", "error"]

class ItemCotizado(BaseModel):
    producto_id: str
    precio_unitario_sin_iva: Decimal   # UYU por unidad canónica (ya convertido)
    precio_original: Decimal           # tal como vino
    moneda_original: Literal["UYU", "USD"]
    incluye_iva_original: bool
    unidad_original: str               # "caja de 12", "bolsa 25kg"
    conversion_aplicada: str | None    # "USD 780 × 40,00 = UYU 31.200" / "caja de 5 resmas → 5 unidad" / "con IVA / 1,22"
    cantidad_minima: float | None
    evidencia: str                     # fragmento literal del mensaje

class Cotizacion(BaseModel):
    id: str
    mensaje_id: str                    # trazabilidad
    proveedor_id: str
    items: list[ItemCotizado]
    costo_envio: Decimal               # 0 si no se menciona
    pedido_minimo_total: Decimal | None
    plazo_pago_dias: int               # 0 = contado
    lead_time_dias: int
    validez_dias: int | None
    observaciones: list[str]           # "precio sujeto a cambio por dólar"
    confianza: float                   # 0–1 autoevaluación del extractor
    campos_dudosos: list[str]          # para resaltar en UI

class Asignacion(BaseModel):
    producto_id: str
    proveedor_id: str
    cantidad: float
    precio_unitario_sin_iva: Decimal
    subtotal: Decimal

class Plan(BaseModel):
    pedido_id: str
    asignaciones: list[Asignacion]
    costo_total: Decimal
    costo_baseline: Decimal            # todo al proveedor habitual
    ahorro: Decimal
    ahorro_pct: float
    proveedores_usados: list[str]
    restricciones_activas: list[str]   # "mínimo de 20 unidades de Mueblería Rivera"
    relajaciones: list[str]            # si hubo que relajar algo
    explicacion: str                   # generada por LLM a partir de lo anterior
    oportunidad_negociacion: str | None # proveedor_id con mayor brecha vs. mejor precio

class EstrategiaNegociacion(BaseModel):
    nombre: Literal["competencia", "volumen", "plazo"]
    descripcion: str
    transcripcion: list[dict]          # [{"rol": "abasto"|"proveedor", "texto": ...}]
    concesion_obtenida_pct: float      # promedio de las corridas
    ganancia_esperada_uyu: Decimal
    riesgo: Literal["bajo", "medio", "alto"]

class Negociacion(BaseModel):
    id: str
    pedido_id: str
    proveedor_id: str
    estrategias: list[EstrategiaNegociacion]
    elegida: str
    mensaje_propuesto: str
    estado: Literal["simulada", "aprobada", "enviada_simulada"]
```

## 4. Endpoints

| Método | Ruta | Qué hace | Devuelve |
|---|---|---|---|
| GET | `/health` | ping | `{"ok": true}` |
| GET | `/pedidos/demo` | pedido precargado de Tecnova S.A. (con catálogo, conversiones y tipo de cambio) | `Pedido` |
| POST | `/pedidos/{id}/cotizar` | lanza simulador en background (BackgroundTasks) | `{"estado": "cotizando"}` |
| GET | `/pedidos/{id}/mensajes` | mensajes crudos + estado de extracción (polling) | `MensajeCrudo[]` |
| GET | `/pedidos/{id}/cotizaciones` | cotizaciones extraídas | `Cotizacion[]` |
| POST | `/extraer` | extrae una cotización de texto/archivo (uso directo y para pruebas) | `Cotizacion` |
| POST | `/pedidos/{id}/optimizar` | corre MILP + explicación | `Plan` |
| POST | `/pedidos/{id}/negociar/{proveedor_id}` | ensaya estrategias | `Negociacion` |
| POST | `/negociaciones/{id}/aprobar` | marca aprobada y "envía" (simulado) | `Negociacion` |
| POST | `/reset` | borra runtime y re-seedea | `{"ok": true}` |

Errores: siempre `{"error": "mensaje legible", "detalle": ...}` con 4xx/5xx. El frontend muestra el
mensaje tal cual; nunca falla en silencio.

## 5. Capa 1 — Extracción

Pipeline por mensaje:

1. **Obtener texto:**
   - `whatsapp_texto` → directo.
   - `pdf` → `pdfplumber.extract_text()`; si devuelve < 50 caracteres, rasterizar la página y pasar a visión.
   - `foto` → LLM con la imagen adjunta.
   - `whatsapp_audio` → transcripción (Whisper) si `ENABLE_AUDIO=1`; si no, usar `contenido_texto` precargado.
2. **Extraer + normalizar en una sola llamada** (prompt `extractor`, ver `PROMPTS.md`) con el catálogo de productos del pedido como contexto, para que mapee "tóner 85a" → `toner` pero no un "tóner compatible" si el catálogo pide original, y marque como dudoso lo que no esté claro.
3. **Validar** con Pydantic. Reintentar una vez si falla.
4. **Reglas post-LLM (en código, no en prompt):**
   - Si `moneda_original == "USD"` → multiplicar por `config.tipo_cambio_usd` y registrar en `conversion_aplicada`.
   - Si `incluye_iva_original` → `precio_sin_iva = precio / 1.22`.
   - Conversión de unidades según la tabla `conversiones` de `pedido_demo.json` (`caja de 5 resmas`, `bidón de 5 L`, `docena`, etc.). Si la unidad no está en la tabla, marcar `campos_dudosos`.
   - `confianza < 0.6` → estado `extraido` pero tarjeta con borde amarillo y texto "Revisar".

Por qué una sola llamada: menos latencia y menos puntos de falla. La evidencia por ítem obliga al
modelo a anclar cada número en el texto.

## 6. Capa 4 — Optimización (MILP con PuLP)

Conjuntos: productos `i`, proveedores `j` con cotización válida para `i`.

Variables:
- `x[i,j] ≥ 0` cantidad del producto `i` comprada a `j`.
- `y[j] ∈ {0,1}` si se le compra algo a `j`.
- `z[i,j] ∈ {0,1}` si se compra `i` a `j` (para mínimos por ítem).

Parámetros:
- `p[i,j]` precio unitario sin IVA.
- `d[i]` demanda del pedido.
- `env[j]` costo de envío.
- `min_total[j]` pedido mínimo en UYU; `min_item[i,j]` cantidad mínima.
- `lead[j]`, `plazo_pago[j]`, `conf[j]` confiabilidad 0–1.
- `w_riesgo` (default 0.03), `w_plazo` (default 0.0005 por día de plazo de pago): pesos de penalización/bonificación. Son chicos a propósito: ordenan empates, no dominan el precio. Referencia: 30 días de plazo = 1,5 % de bonificación; el riesgo máximo de la demo (confiabilidad 0,8) = 0,6 % de penalización. Con 0.002, 30 días valían 6 %, lo que ya no es desempate.
- `max_prov` (default 4; con los datos de demo el óptimo usa 3 proveedores, Compuservice, Papelera del Sur y Ofisillas, así que esta restricción no queda activa).

Objetivo (minimizar):
```
Σ p[i,j]·x[i,j]  +  Σ env[j]·y[j]  +  w_riesgo · Σ p[i,j]·x[i,j]·(1 − conf[j])
                 −  w_plazo · Σ p[i,j]·x[i,j]·plazo_pago[j]
```

Restricciones:
```
Σ_j x[i,j] = d[i]                         ∀ i            (cubrir la demanda)
x[i,j] ≤ d[i]·z[i,j]                      ∀ i,j          (vínculo)
z[i,j] ≤ y[j]                             ∀ i,j
x[i,j] ≥ min_item[i,j]·z[i,j]             ∀ i,j          (mínimo por ítem)
Σ_i p[i,j]·x[i,j] ≥ min_total[j]·y[j]     ∀ j            (mínimo de pedido)
y[j] = 0  si lead[j] > días hasta necesario_para          (plazo de entrega)
Σ_j y[j] ≤ max_prov
```

Baseline: mismo modelo con `y[j]=1` solo para el proveedor habitual (si no cotiza algo, ese ítem
se compra al más barato restante). `ahorro = baseline − óptimo`.

Si es infactible, relajar en orden: `max_prov` → mínimos (convertir a penalización de 500 UYU) →
plazo. Registrar en `relajaciones` y pasarlo a la explicación.

Explicación: prompt `explicar_plan` recibe asignaciones, ahorro, restricciones activas y relajaciones,
y escribe 3–5 oraciones. Debe mencionar explícitamente cuando no se eligió al más barato y por qué
(mínimo de pedido, plazo, confiabilidad). **Nunca** cambia números.

Oportunidad de negociación: para cada proveedor usado, brecha = su precio − mejor precio cotizado
para ese ítem, ponderada por cantidad. El de mayor brecha total es `oportunidad_negociacion`.

## 7. Capa 5 — Negociación ensayada

Entradas: pedido, cotización del proveedor objetivo, mejor precio alternativo por ítem, perfil del
proveedor (del simulador: `perfil_concesion`, `sensible_a`, `personalidad`).

Para cada estrategia en `["competencia", "volumen", "plazo"]`:
1. Correr 2 simulaciones de 3 rondas: turno de **Abasto** (prompt `negociador` con la estrategia) y turno del **gemelo** (prompt `proveedor_gemelo`, que conoce su precio de piso y su perfil, y responde en personaje). Temperatura 0.7.
2. Al final, el gemelo emite su oferta final en JSON (`{"precio_final_por_item": {...}, "acepta": bool}`).
3. `concesion_pct` = promedio de reducción vs. cotización original; `ganancia_esperada_uyu` = concesión × cantidades del plan.
4. `riesgo`: "alto" si el gemelo mostró molestia o cortó; "bajo" si cerró en ≤ 2 rondas.

Elegida = mayor `ganancia_esperada_uyu` con riesgo ≠ alto (si todas son altas, la de mayor ganancia).
Mensaje propuesto = prompt `redactar_mensaje` con la estrategia elegida, tono de WhatsApp, ≤ 80 palabras,
en español rioplatense, sin revelar el precio piso ni inventar competidores: solo usa los precios reales
de las otras cotizaciones.

Costo: 3 × 2 × 3 = 18 turnos de negociador + 18 del gemelo + 6 cierres. Paralelizar las 6 corridas con
`asyncio.gather`. Objetivo: < 40 s en total.

**Humano al mando:** nada se "envía" sin `POST /aprobar`. El mensaje es editable antes de aprobar.

## 8. Simulador de proveedores

Cada entrada de `data/proveedores_sim.json` tiene lo público (`Proveedor`) y lo privado:
`tabla_precios` (precio real por producto, unidad en la que cotiza, si incluye IVA), `precio_piso_pct`
(hasta dónde cede), `perfil_concesion` (texto), `sensible_a` (lista), `personalidad`, `demora_factor`,
`canal_preferido`, `muletillas`.

`POST /cotizar` → por proveedor, una tarea en background que:
1. Espera `SIM_DELAY_SECONDS × demora_factor` (uno responde a los 40 s a propósito: "el que tarda").
2. Genera la respuesta con prompt `proveedor_responde` en su canal:
   - `whatsapp_texto`: mensaje informal, a veces con cantidades en unidades propias o sin aclarar IVA.
   - `whatsapp_audio`: texto hablado, con muletillas; si hay TTS, generar mp3; si no, se muestra como "🎤 audio (transcripto)".
   - `pdf`: genera HTML de presupuesto → PDF (`weasyprint` o `reportlab`), con tabla, moneda y "precios más IVA".
   - `foto`: genera una imagen de presupuesto "a mano" con PIL sobre una plantilla de papel, fuente tipo manuscrita, o usa una imagen precargada en `data/img/`.
3. Guarda `MensajeCrudo` y dispara extracción.

**Cache determinístico:** la primera vez que se genera una respuesta para `(pedido_id, proveedor_id)`
se guarda en `runtime/cache/`. `make reset` conserva el cache salvo `make reset-hard`. Así la demo es
igual en cada ensayo y no depende de la latencia del LLM.

## 9. Frontend

Páginas: `Pedido` → `Feed` → `Cotizaciones` → `Plan` → `Negociación` → `Visión`.

- `api.ts`: funciones `cotizar`, `getMensajes`, `getCotizaciones`, `optimizar`, `negociar`, `aprobar`, `reset`.
- Feed: polling cada 1,5 s mientras `estado == "cotizando"`. Burbujas con avatar del proveedor, ícono por canal, estado "leyendo…" con animación, luego link a la tarjeta.
- Tarjeta de cotización: ítems con precio normalizado, tooltip/acordeón con `evidencia`, badges de IVA/envío/plazo/lead time, borde amarillo si `confianza < 0.6`.
- Plan: número de ahorro en grande arriba, tabla, explicación, botón "Negociar con {proveedor}" sobre `oportunidad_negociacion`.
- Negociación: 3 columnas con spinner mientras corre; transcripción colapsable; la elegida resaltada; textarea con el mensaje; botón Aprobar → toast "Enviado (simulado)".
- Visión: 3 tarjetas estáticas (perfil del proveedor, predicción, índice de mercado) con etiqueta "Próximamente".

## 10. Decisiones y trade-offs

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| Extracción + normalización en una llamada | Dos llamadas | Latencia y menos puntos de falla; la evidencia por ítem compensa. |
| MILP con PuLP | Heurística greedy | El solver es el argumento "científico" del pitch y maneja mínimos de pedido bien. Greedy queda como corte. |
| LLM × LLM para negociación | Reglas | Es la capacidad que no existe sin IA y la más vistosa. Acotada a 18 turnos. |
| Polling | WebSockets | Cero riesgo de integración; 1,5 s es imperceptible en demo. |
| Cache de respuestas simuladas | Generar siempre | Demo reproducible, inmune a latencia de la API. |
| JSON en disco | SQLite | Menos código; `make reset` es borrar una carpeta. |
