# AGENTS.md — Abasto

Instrucciones para agentes de código (Claude Code, Cursor, Codex, etc.) que trabajen en este repo.
Leé este archivo completo antes de tocar código. Si algo acá contradice un pedido del usuario, preguntá.

## 1. Qué es Abasto

**Director de compras con IA para empresas.** Una empresa carga lo que necesita comprar (equipamiento,
insumos, servicios), Abasto lo cotiza con sus proveedores, entiende las respuestas en cualquier formato (texto de
WhatsApp, PDF, foto, audio; en pesos o en dólares), arma el plan de compra óptimo repartido entre proveedores y ensaya la
negociación con un "gemelo digital" de cada proveedor antes de proponer un mensaje real.

**Contexto:** hackatón de 24 h. Prioridad absoluta: **una demo que funcione de punta a punta**
y que se pueda pitchear. Nada de infraestructura de producción.

**Regla de oro del producto:** si se le saca la IA, Abasto no sirve. Cada feature tiene que pasar
esa prueba. Comparar precios ya estructurados NO es el producto; entender cotizaciones desordenadas,
modelar proveedores y ensayar negociaciones SÍ lo es.

## 2. Alcance (congelado)

### Incluido en el MVP (en este orden de prioridad)
1. **Capa 1 — Percepción:** extraer cotizaciones estructuradas de mensajes crudos (texto, PDF, imagen; audio si hay tiempo).
2. **Capa 4 — Optimización:** plan de compra con un solver MILP (PuLP) + explicación en lenguaje natural.
3. **Capa 5 — Negociación ensayada:** simular estrategias contra el gemelo del proveedor, elegir la mejor, proponer mensaje. El humano aprueba.
4. **Simulador de proveedores:** 6 proveedores con personalidad que responden al pedido de cotización en su formato preferido.
5. **UI de demo:** feed en vivo de respuestas, tarjetas de cotización, plan de compra, panel de negociación, pantallas de "visión".

### Fuera de alcance (NO implementar aunque parezca fácil)
- Autenticación, multiusuario, roles.
- Envío real a WhatsApp/email. Todo es simulado.
- Base de datos real. Persistencia en JSON/SQLite en `backend/data/`.
- Capas 2, 3, 6 y 7 (perfil histórico, predicción, índice de mercado, agente-a-agente): solo pantallas estáticas en `/vision`.
- Tests exhaustivos. Solo smoke tests de los endpoints críticos.
- Deploy. Corre en localhost.

## 3. Stack

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn | `backend/` |
| LLM | SDK de Anthropic (`anthropic`), modelo por env `LLM_MODEL` | default `claude-sonnet-5-5`; nunca hardcodear el modelo |
| Visión (fotos de presupuestos) | Mismo LLM, input de imagen | |
| PDF | `pdfplumber` | fallback: enviar la página como imagen al LLM |
| Audio (opcional) | `openai` Whisper API o `faster-whisper` local | detrás de flag `ENABLE_AUDIO` |
| Optimización | `pulp==2.9.*` (solver CBC incluido) | no subir a 3.x: cambia la API de `LpVariable` y rompe el modelo |
| Frontend | React 19 + Vite + TypeScript + Tailwind v4 + shadcn/ui (preset Vega, base neutral) | `frontend/`; componentes en `src/components/ui/` (agregar con `npx shadcn@latest add <componente>`) |
| Comunicación | REST + polling cada 1,5 s para el feed | nada de WebSockets salvo que ya funcione todo |
| Persistencia | archivos JSON en `backend/data/runtime/` | se borran con `make reset` |

## 4. Estructura del repo

```
abasto/
├── AGENTS.md                 ← este archivo
├── README.md
├── Makefile                  ← make dev / make reset / make seed
├── docs/
│   ├── PLAN_24H.md           ← cronograma y cortes
│   ├── ARQUITECTURA.md       ← modelo de datos, endpoints, MILP
│   ├── PROMPTS.md            ← prompts canónicos (copiar de acá, no inventar)
│   ├── CONTRATO_BACKEND.md   ← endpoints reales y firmas que A implementa (leer antes de integrar)
│   └── PITCH_Y_DEMO.md       ← guion de demo y pitch
├── data/
│   ├── proveedores_sim.json  ← personas de los proveedores simulados
│   ├── pedido_demo.json      ← compra mensual de la empresa demo (Tecnova S.A.)
│   ├── respuestas_fijas.json ← respuestas crudas de ejemplo (fixtures y fallback)
│   └── extracciones_fijas.json ← salida esperada del extractor para esas respuestas
├── backend/
│   ├── app/
│   │   ├── main.py           ← FastAPI, routers
│   │   ├── models.py         ← Pydantic: Producto, Proveedor, Cotizacion, Pedido, Plan, Negociacion
│   │   ├── llm.py            ← (A) cliente LLM único, helpers de JSON estructurado
│   │   ├── extraccion.py     ← (A) Capa 1: extraer_crudo()
│   │   ├── explicacion.py    ← (A) explicar_plan()
│   │   ├── negociacion.py    ← (A) Capa 5: ensayar()
│   │   ├── config.py         ← (C) variables de entorno
│   │   ├── normalizacion.py  ← (C) reglas post-LLM: moneda, IVA, unidades
│   │   ├── pipeline.py       ← (C) mensaje → extracción → cotización (con fallback a fixtures)
│   │   ├── optimizacion.py   ← (C) Capa 4 (PuLP)
│   │   ├── integracion_a.py  ← (C) contexto de negociación y llamadas a las funciones de A
│   │   ├── simulador.py      ← (C) proveedores simulados
│   │   ├── archivos.py       ← (C) PDF y foto de los presupuestos simulados
│   │   ├── pedidos.py        ← (C) pedido en runtime
│   │   ├── prompts/          ← un .md por prompt, cargados por nombre
│   │   └── store.py          ← (C) lectura/escritura JSON
│   ├── tests/test_smoke.py
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        ├── pages/            ← Pedido, Feed, Plan, Negociacion, Vision
        ├── components/
        └── api.ts            ← único lugar que llama al backend
```

## 5. Cómo correr

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # completar ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173

# atajos
make dev     # levanta ambos
make seed    # carga data/*.json en backend/data/runtime/
make reset   # borra runtime y vuelve a seedear
```

Variables de entorno (`backend/.env`):
```
ANTHROPIC_API_KEY=
LLM_MODEL=claude-sonnet-5-5
OPENAI_API_KEY=          # solo si ENABLE_AUDIO=1
ENABLE_AUDIO=0
SIM_DELAY_SECONDS=4      # base 4 = demoras del guion (la papelera a los 40 s); 0 = instantáneo
SIM_MODE=fijo            # fijo = respuestas de data/; llm = las genera el LLM y se cachean
EXTRACCION_MODE=auto     # auto = LLM si está la Capa 1 y hay key, si no fixtures; fijo; llm
```

## 6. Reglas para trabajar con el LLM

1. **Un solo cliente**, en `app/llm.py`. Nunca instanciar el SDK en otro archivo.
2. **Prompts en archivos**, en `app/prompts/*.md`, copiados de `docs/PROMPTS.md`. No escribir prompts inline en el código.
3. **Salida estructurada siempre:** pedir JSON con el esquema explícito en el prompt y validar con Pydantic. Si falla el parseo, reintentar **una** vez pidiendo "solo JSON válido". Si vuelve a fallar, devolver error claro, no inventar datos.
4. **Trazabilidad obligatoria:** toda cotización extraída guarda `fuente_id` (id del mensaje crudo) y `evidencia` (fragmento textual de donde salió cada número). La UI muestra la evidencia. **Nunca** un precio sin fuente.
5. **El solver decide, el LLM explica.** La explicación del plan se genera a partir del resultado de PuLP; el LLM no elige proveedores.
6. **Temperatura baja** (0–0.2) para extracción y scoring; media (0.7) para personas de proveedores y negociador.
7. **Límite de costo:** la negociación ensayada corre máximo 3 estrategias × 2 corridas × 3 rondas. Paralelizar con `asyncio.gather`.
8. **Tiempo de respuesta:** ninguna llamada al LLM sin `timeout=60`. Si una extracción tarda más de 20 s en demo, es un bug.

## 7. Convenciones de código

- Python: `black` + type hints. Funciones chicas, nombres en español para el dominio (`cotizacion`, `proveedor`), en inglés para lo técnico (`parse_json`, `retry`).
- Toda función que llama al LLM es `async` y recibe/devuelve modelos Pydantic.
- Montos en **pesos uruguayos (UYU)**, enteros o `Decimal`. IVA 22 %: guardar siempre precio **sin IVA** y el flag `incluye_iva` original.
- Moneda: el extractor registra `moneda` (`UYU`/`USD`) sin convertir. La conversión USD → UYU se hace en código con `config.tipo_cambio_usd` y queda en `conversion_aplicada` ("USD 780 × 40,00 = UYU 31.200"). El tipo de cambio se muestra en la UI.
- Unidades canónicas: `unidad`, `l`, `kg`. Toda conversión (caja de 5 resmas, bidón de 5 L, docena) se hace en código con la tabla `conversiones` de `pedido_demo.json` y queda registrada en `conversion_aplicada`.
- Frontend: componentes funcionales, estado con `useState`/`useReducer`, sin librerías de estado global. Tailwind, sin CSS custom salvo animaciones del feed.
- Commits: `feat:`, `fix:`, `ui:`, `docs:`. Pushear seguido, main siempre corre.

## 8. Definición de "terminado" por feature

| Feature | Terminado cuando… |
|---|---|
| Extracción | Los 6 mensajes de `data/respuestas_fijas.json` (3 textos, uno ambiguo; PDF; imagen; audio transcripto) producen `Cotizacion` válida con evidencia, en < 20 s cada uno. |
| Simulador | `POST /pedidos/{id}/cotizar` genera respuestas de los 6 proveedores con demoras distintas y el feed las muestra llegando. |
| Optimización | `POST /pedidos/{id}/optimizar` devuelve plan factible, costo total, ahorro vs. "todo al proveedor habitual" y explicación de 3–5 oraciones. |
| Negociación | `POST /pedidos/{id}/negociar/{proveedor_id}` devuelve 3 estrategias con ganancia esperada, la elegida y el mensaje propuesto; botón "Aprobar" cambia el estado. |
| Demo | El recorrido completo de `docs/PITCH_Y_DEMO.md` corre dos veces seguidas sin tocar código. |

## 9. Qué hacer cuando algo no funciona

- **El LLM devuelve JSON roto:** revisar que el prompt termine con el esquema y "Respondé solo con el JSON". No agregar regex para "arreglar" JSON.
- **El MILP es infactible:** relajar en este orden: (1) límite de proveedores, (2) mínimos de pedido (permitir con penalización), (3) lead time. Loguear qué se relajó y mostrarlo en la explicación.
- **Un proveedor simulado no responde:** es comportamiento esperado para `papelera_del_sur` (responde tarde a propósito). Verificar `SIM_DELAY_SECONDS`.
- **Vas atrasado:** aplicar los cortes de `docs/PLAN_24H.md`, sección "Cortes". No inventar features nuevas.

## 10. No hacer

- No agregar dependencias pesadas (LangChain, LlamaIndex, bases vectoriales). No hacen falta.
- No crear abstracciones "para después". Es una hackatón.
- No tocar `data/*.json` sin actualizar `docs/PITCH_Y_DEMO.md` si cambia la demo.
- No dejar la UI rota en `main`. Si una página está a medias, ocultar el link.
- No mostrar en la UI ningún número que no tenga `evidencia`.
