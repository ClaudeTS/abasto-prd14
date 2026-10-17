# Contrato del backend — Abasto (rol C)

Qué expone el backend, qué espera de la Capa de IA (rol A) y qué tiene que saber el frontend (rol B).
Complementa `ARQUITECTURA.md`; donde difiere, manda este documento y la diferencia está anotada.

## Correr

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # ANTHROPIC_API_KEY solo hace falta para las capas de A
uvicorn app.main:app --reload --port 8000
python -m pytest -q                  # smoke + normalización + solver + archivos, sin API key
```

Documentación interactiva: http://localhost:8000/docs

### Variables (`backend/.env`)

| Variable | Default | Qué hace |
|---|---|---|
| `ANTHROPIC_API_KEY` | vacío | Sin key, todo corre con fixtures; la negociación devuelve 501. |
| `LLM_MODEL` | `claude-sonnet-5-5` | Lo lee A en `app/llm.py`. |
| `SIM_DELAY_SECONDS` | `4` | Escala las demoras de `respuestas_fijas.json`: con 4, la papelera responde a los 40 s. Con `0`, todo llega al instante. |
| `SIM_MODE` | `fijo` | `fijo` = respuestas de `data/respuestas_fijas.json` (demo determinística). `llm` = las genera A con el prompt `proveedor_responde` y las cachea. |
| `EXTRACCION_MODE` | `auto` | `auto` = usa el extractor de A si existe y hay key, si no los fixtures. `fijo` = siempre fixtures. `llm` = siempre A (error si no está). |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Orígenes del frontend. |
| `ABASTO_DATA_DIR` | `backend/data` | Dónde viven `runtime/` y `cache/`. |

**Recomendación para el pitch:** `SIM_MODE=fijo` y `EXTRACCION_MODE=auto` con la extracción de A ya
cacheada (corré la demo una vez antes: `backend/data/cache/` guarda las extracciones y `make reset` no lo borra).

## Endpoints

Errores: siempre `{"error": "mensaje legible", "detalle": ...}`. El frontend muestra `error` tal cual.

| Método | Ruta | Devuelve | Notas |
|---|---|---|---|
| GET | `/health` | `{ok, sim_mode, extraccion, llm_model, api_key}` | `extraccion` dice si se usa `llm` o `fijo`. |
| GET | `/pedidos/demo` | `PedidoCompleto` | Pedido + `catalogo`, `conversiones`, `tipo_cambio_usd`, `iva`. |
| GET | `/pedidos/{id}` | `PedidoCompleto` | Igual, con el `estado` actualizado. |
| GET | `/proveedores` | `Proveedor[]` | Solo los datos públicos. |
| POST | `/pedidos/{id}/cotizar` | `{estado: "cotizando", proveedores}` | Idempotente mientras corre (`ya_estaba_en_curso: true`). |
| GET | `/pedidos/{id}/mensajes` | `MensajeCrudo[]` | Polling cada 1,5 s. Orden de llegada. |
| GET | `/pedidos/{id}/proveedores/estado` | `EstadoProveedor[]` | **Nuevo.** `esperando` + `responde_en_segundos`, `respondio`. Para "Papelera del Sur no respondió todavía". |
| GET | `/pedidos/{id}/cotizaciones` | `Cotizacion[]` | |
| POST | `/cotizaciones/{id}/confirmar` | `Cotizacion` | **Nuevo.** Body `{"incluye_iva": true}`. El "un clic" de Lucía: re-normaliza y queda `estado: "confirmada"`. |
| POST | `/extraer` | `Cotizacion` | Form: `proveedor_id`, `canal`, `texto` y/o `archivo`. Texto libre requiere la Capa 1 de A (si no, 503). No toca el feed de la demo. |
| GET | `/archivos/{nombre}` | archivo | PDF y foto de los mensajes (`MensajeCrudo.archivo_url`). |
| POST | `/pedidos/{id}/optimizar` | `Plan` | 409 si faltan respuestas o hay cotizaciones para revisar (ver abajo). `?forzar=true` optimiza igual excluyéndolas. |
| GET | `/pedidos/{id}/plan` | `Plan` | El último calculado. |
| POST | `/pedidos/{id}/negociar/{proveedor_id}` | `Negociacion` | 501 hasta que A entregue la Capa 5 (el `detalle.contexto` muestra lo que A va a recibir). Timeout 90 s → 504. |
| GET | `/negociaciones/{id}` | `Negociacion` | |
| POST | `/negociaciones/{id}/aprobar` | `Negociacion` | Body opcional `{"mensaje": "texto editado"}`. Estado → `enviada_simulada`. |
| POST | `/reset` | `{ok}` | `?hard=true` también borra el cache. |

## Para B (frontend)

**Recorrido y estados del pedido:** `nuevo → cotizando → cotizado → optimizado → negociando → aprobado`.

1. **Feed.** Después de `POST /cotizar`, hacé polling de `/mensajes` y `/proveedores/estado`. Cada mensaje pasa
   `pendiente → leyendo → extraido` (o `error`, con `mensaje.error`). Al llegar a `extraido` trae `cotizacion_id`.
   Canal `pdf` y `foto`: mostrá `archivo_url` (prefijo `http://localhost:8000`). Canal `whatsapp_audio`: la
   transcripción viene en `contenido_texto` (burbuja 🎤).
2. **Tarjetas.** `ItemCotizado.evidencia` y `conversion_aplicada` (ej. `USD 780 × 40,00 = UYU 31.200`,
   `con IVA: 1.090 / 1,22 = 893,44 · caja de 5 resmas → 5 unidad: 893,44 / 5 = 178,69`).
   Borde amarillo "Revisar" si `estado == "revisar"` (confianza < 0,6 o una duda que cambia el precio).
3. **Confirmar IVA (necesario para el guion).** Compuservice no aclara el IVA: llega en `revisar` con
   `campos_dudosos: ["iva"]` y precio 33.500. Botón "Confirmar: incluye IVA" → `POST /cotizaciones/{id}/confirmar`
   con `{"incluye_iva": true}` → pasa a 27.459,02. **Sin este clic el plan da otro resultado** (las notebooks se
   van a TecnoImport).
4. **Optimizar.** Respuestas 409 posibles: `detalle.esperando` (faltan proveedores) o `detalle.revisar`
   (lista de `{cotizacion_id, proveedor_id, campos_dudosos}`). Mostrá `error` y ofrecé el atajo a la tarjeta.
5. **Plan.** Usá `ahorro`/`ahorro_pct` y `ahorro_comparable`/`ahorro_pct_comparable` (el guion pide los dos),
   `no_mas_barato` para el badge "por qué no el más barato" (las sillas), `oportunidad_negociacion` para el botón
   "Negociar con …". `explicacion_origen` dice si la explicación es del LLM o de la plantilla.
6. **Negociación.** Mientras A no entregue, `POST /negociar` devuelve 501: mostrá el mensaje. Cuando funcione,
   tarda hasta ~40 s: spinner en las 3 columnas.

Montos: números (no strings), en UYU sin IVA. Formato en pantalla: `$ 12.340`.

## Para A (IA)

El backend ya llama a estas funciones si existen. Implementalas con estas firmas exactas y no hace falta
tocar nada de C. Todas `async`. El prompt, el cliente y los reintentos quedan de tu lado (`app/llm.py`).

```python
# app/extraccion.py — Capa 1
async def extraer_crudo(*, texto: str | None, imagen: Path | None, canal: str,
                        proveedor: Proveedor, catalogo: list[Producto]) -> dict: ...
```
- Devuelve el JSON del prompt `extractor` **sin convertir nada** (moneda, IVA y unidades las aplica C en
  `app/normalizacion.py`). Referencia exacta de lo esperado para los 6 mensajes: `data/extracciones_fijas.json`.
- `texto` viene listo: WhatsApp, transcripción del audio o texto del PDF (pdfplumber). Si `texto` es None,
  `imagen` es la foto (`.jpg`) o un PDF escaneado: va a visión.
- Unidades: usá en `unidad_original` los nombres de `pedido_demo.json → conversiones` (`caja de 5 resmas`,
  `bidón de 5 L`) o `unidad`. Cualquier variante parecida (`bidon 5L`) también la entiende C. Si no, C marca
  `unidad:<producto>` como duda y la cotización queda para revisar.
- Si lanza una excepción en modo `auto`, C cae al fixture y lo loguea: la demo no se rompe.

```python
# app/explicacion.py — explicación del plan
async def explicar_plan(datos: dict[str, str]) -> str: ...
```
- `datos` trae las variables del prompt `explicar_plan` ya formateadas (`optimizacion.datos_para_explicar`).
- Si falla o no existe, C usa una explicación de plantilla. Nunca rompe `/optimizar`.

```python
# app/negociacion.py — Capa 5
async def ensayar(contexto: ContextoNegociacion) -> dict: ...
# → {"estrategias": [{"nombre", "descripcion", "transcripcion", "concesion_obtenida_pct", "riesgo"}, ...],
#    "elegida": "volumen", "mensaje_propuesto": "..."}
```
- `ContextoNegociacion` (en `models.py`) trae el perfil privado del gemelo (`precio_piso_pct`, `perfil_concesion`,
  `sensible_a`, …), la cotización, y por ítem la cantidad del plan y la **mejor alternativa real** con su condición
  (ej. Mueblería Rivera 9.800, "exige mínimo 20 unidades y el pedido es de 15"). Con eso armás `mejores_alternativas`
  sin inventar.
- **Los números los pone el código:** C recalcula `ganancia_esperada_uyu = valor_en_juego × concesión %` y aplica la
  regla de §7 para `elegida` (mayor ganancia con riesgo ≠ alto). Si tu `elegida` difiere, queda logueado.

```python
# app/llm.py — solo si se usa SIM_MODE=llm
async def completar(system: str, user: str, *, temperature: float, max_tokens: int) -> str: ...
```

## Extensiones respecto de ARQUITECTURA.md

| Cambio | Por qué |
|---|---|
| `Cotizacion.estado` (`valida`/`revisar`/`confirmada`) y `POST /cotizaciones/{id}/confirmar` | El solver solo usa cotizaciones validadas (pitch). Compuservice necesita la confirmación del IVA. |
| `Plan.ahorro_comparable`, `ahorro_pct_comparable`, `no_mas_barato`, `cotizaciones_excluidas`, `brecha_oportunidad`, `explicacion_origen`, `tipo_cambio_usd` | El guion muestra ambos ahorros y el caso de las sillas. |
| `GET /pedidos/{id}/proveedores/estado` | Para "no respondió todavía · Abasto va a insistir". |
| `MensajeCrudo.archivo_url`, `error`, `cotizacion_id` | La UI linkea el archivo y la tarjeta sin cruzar listas. |
| Plazo de entrega por ítem (`z[i,j]`) en vez de por proveedor (`y[j]`) | Cada línea tiene su fecha. |
| Demoras del simulador = `demora_segundos` del fixture × `SIM_DELAY_SECONDS / 4` | Respeta los 40 s de la papelera del guion. |
| Montos `Decimal` serializados como número | Sin strings en el frontend. |
