# Llamadas del agente — ElevenLabs + Twilio

Abasto puede llamar por teléfono con un agente de voz en dos momentos de la demo:

1. **Pedir la cotización a quien no respondió.** En el feed, el proveedor que está "esperando" (la Papelera del
   Sur) tiene un botón **Llamar**. La transcripción de la llamada entra al feed como un mensaje de canal `llamada`
   y pasa por la extracción como cualquier otro.
2. **Negociar por teléfono.** En la negociación, **Aprobar y llamar** aprueba la estrategia y el mensaje (la
   aprobación de Lucía sigue siendo obligatoria) y el agente llama con eso. Al terminar se muestran el resumen, si
   hubo acuerdo y el precio acordado.

Cómo está hecho: agente de **ElevenLabs** con un número de **Twilio** importado (integración nativa). El backend
dispara la llamada con `POST /v1/convai/twilio/outbound-call` y la sigue consultando
`GET /v1/convai/conversations/{id}` cada 2,5 s. **No usa webhooks**: no hace falta una URL pública ni un túnel.
Las instrucciones de cada llamada llegan al agente como variables dinámicas; el agente se configura una sola vez.

Modos (`LLAMADAS_MODO` en `backend/.env`):

| Modo | Qué pasa |
|---|---|
| `simulada` (default) | Sin costo ni red. La transcripción aparece de a poco, armada con los datos de la demo. |
| `real` | Llama de verdad, solo a los números de `TELEFONOS_PROVEEDORES`. |

En modo real, si una llamada falla en el escenario, la pantalla ofrece **Simular llamada** (la misma acción con
`?simulada=true`).

---

## 1. Twilio: un número que pueda llamar a Uruguay

No hace falta un número uruguayo: alcanza con un número de EE. UU. con capacidad de **Voice** y el permiso
geográfico de Uruguay habilitado.

1. **Comprar el número:** Console → Phone Numbers → Buy a number → país United States, capacidad **Voice**.
2. **Habilitar Uruguay:** Console → Voice → Settings → **Geo permissions** → marcar **Uruguay** (la categoría que
   corresponda: celulares y/o fijos) → Save. Sin esto, las llamadas a +598 fallan.
3. **Cuenta trial:** solo puede llamar a **números verificados** (Console → Phone Numbers → Verified Caller IDs →
   agregar los celulares del equipo) y Twilio antepone un aviso de cuenta de prueba al inicio de cada llamada.
   Para el pitch conviene cargar saldo y salir del trial.
4. Anotá el **Account SID** y el **Auth Token**, o mejor creá una **API Key** (Console → Account → API keys) para
   dársela a ElevenLabs con permisos acotados.

## 2. ElevenLabs: el agente

> **Ya creado (17/10):** agente **"Abasto compras"** (el ID está en el `.env` del equipo, no en el repo).
> Voz Melisa (rioplatense), LLM `claude-haiku-5-5` (temp. 0,3), zona `America/Montevideo`, End call habilitado,
> data collection `acuerdo` / `precio_acordado` / `condicion`, resúmenes en español. Lo de abajo queda como
> referencia para recrearlo.
>
> **Seguridad (el repo es público):** el agente tiene **autenticación activada** (Security → Enable authentication),
> así que nadie puede abrir una conversación solo con el ID; las llamadas salientes del backend van con la API key.
> Límites: 2 llamadas simultáneas y 60 por día. El número de Twilio **no tiene agente asignado**, para que una
> llamada entrante de un desconocido no lo active (para salientes no hace falta).

En ElevenLabs → **Agents** → crear un agente nuevo, por ejemplo "Abasto compras".

- **Idioma:** Español. **Voz:** una voz en español (idealmente rioplatense).
- **First message:**
  ```
  {{primer_mensaje}}
  ```
- **System prompt:**
  ```
  Sos el asistente de compras con inteligencia artificial de {{negocio}} y llamás por teléfono a proveedores en
  nombre de {{comprador}}. Hablás en español rioplatense, con frases cortas y naturales, como alguien de compras
  que conoce al proveedor.
  Al empezar (en el primer mensaje) te presentás como asistente de inteligencia artificial de {{negocio}} y avisás
  que la llamada se graba. Si te preguntan, confirmás que sos una inteligencia artificial; nunca lo negás.
  La llamada no tiene duración máxima: no apures al proveedor.

  Tarea de esta llamada ({{tipo_llamada}}) con {{proveedor_nombre}}:
  {{instrucciones}}

  Reglas:
  - No inventes precios, cantidades ni competidores: usá solo los datos de la tarea y lo que diga el proveedor.
  - Cuando el proveedor te dé precios, repetilos para confirmar (producto, precio unitario, si incluye IVA).
  - No cierres compras: {{comprador}} confirma todo por escrito.
  - Si el proveedor no puede hablar, preguntá cuándo llamar y despedite.
  - Cuando termines, despedite y cortá la llamada.
  ```
  El `primer_mensaje` que manda el backend ya trae la presentación, por ejemplo: *"Hola, ¿hablo con Papelera del
  Sur? Soy el asistente de inteligencia artificial de Tecnova S.A. y te aviso que esta llamada se graba. Te llamo
  de parte de Lucía por la cotización que les pedimos por WhatsApp. ¿Tenés un minuto?"*
- **Duración y grabación (RF-06):** en Advanced, la duración máxima de la conversación al máximo que permita la
  cuenta (no hay duración máxima). En Privacy/retención: transcripción sin vencimiento y audio **60 días**
  (`GET /llamadas/{id}` informa `audio_disponible_hasta` en las llamadas reales).
- **Variables dinámicas:** el backend manda `negocio`, `comprador`, `proveedor_nombre`, `tipo_llamada`,
  `instrucciones` y `primer_mensaje`. Para probar desde la consola, cargá valores por defecto.
- **Tools:** habilitar la herramienta de sistema **End call** (para que el agente corte al terminar).
- **Analysis → Data collection** (lo usa la negociación para mostrar el resultado):

  | Identificador | Tipo | Descripción |
  |---|---|---|
  | `acuerdo` | boolean | ¿El proveedor aceptó una propuesta concreta de precio o condiciones? |
  | `precio_acordado` | number | Precio unitario acordado, sin IVA, en pesos uruguayos. Vacío si no hubo acuerdo. |
  | `condicion` | string | Condición del acuerdo (ej. "si se equipan 10 puestos más"). Vacío si no hubo. |

  Si no los configurás, la llamada funciona igual: solo se muestra el resumen.

- **Security:** activar **Enable authentication** y poner límites de llamadas (el repo es público: no publiques el
  Agent ID, y aunque se filtre, con autenticación no sirve sin la API key).
- Copiá el **Agent ID** (está en la configuración del agente) al `.env`, nunca a la doc ni al código.

**Importar el número de Twilio:** Agents → **Phone Numbers** → Import → Twilio → número, SID y token (o API Key).
Para llamadas salientes no hace falta asignarle el agente.

## 3. Variables en `backend/.env`

```
LLAMADAS_MODO=real
ELEVENLABS_API_KEY=sk_...
ELEVENLABS_AGENT_ID=agent_...
ELEVENLABS_PHONE_NUMBER_ID=phnum_...
TELEFONOS_PROVEEDORES=papelera_del_sur:+59899111222,ofisillas:+59899333444
LLAMADA_REINTENTO_MINUTOS=30   # opcional: espera del reintento si no atiende (sección 6)
```

- `ELEVENLABS_PHONE_NUMBER_ID`: lo da `python -m scripts.probar_llamada --numeros`.
- `TELEFONOS_PROVEEDORES`: `proveedor_id:+598…`, separados por coma. **Solo los celulares del equipo**: el agente
  nunca llama a un número que no esté acá. En la UI y en la API se muestran enmascarados.
- Para leer la cotización de una llamada real hace falta la extracción con LLM (`ANTHROPIC_API_KEY`). Sin eso, la
  transcripción entra al feed pero queda marcada con error en vez de inventar una lectura.

## 4. Probar antes del pitch

```bash
cd backend
python -m scripts.probar_llamada --numeros           # ¿está importado el número? ¿cuál es su id?
python -m scripts.probar_llamada papelera_del_sur    # llama al celular cargado para la papelera
```

El segundo comando muestra la transcripción mientras sucede y el resumen al final. Después, el recorrido completo
desde la UI con `LLAMADAS_MODO=real`.

## 5. En el pitch

- **Momento 1 (feed):** "La papelera todavía no contestó. En vez de esperar, Abasto la llama." → clic en
  **Llamar** → suena el celular de Guzmán (que hace de la vendedora) → la transcripción aparece en vivo → al cortar,
  la cotización entra al feed con evidencia, como si hubiera llegado por WhatsApp.
- **Momento 2 (negociación):** "Lucía aprueba la estrategia de volumen y, en vez de mandar un WhatsApp, deja que
  Abasto llame." → **Aprobar y llamar** → suena el celular de Emiliano (Ofisillas) → resultado con precio acordado.
- **Respaldo:** si falla la red o el celular no suena, **Simular llamada**; si no, `LLAMADAS_MODO=simulada` y
  reiniciar el backend.

## 6. Secuencia de contacto (RF-06, PRD 1.4 §11.1)

Las llamadas de **cotización** siguen esta secuencia; las de negociación no (las aprueba Lucía una por una).

1. **Llamada.** Si atiende, la secuencia termina (`atendida`).
2. **No atiende** (real: `call_result` `busy`, `no_answer` o `failed`, o la conversación `failed`; simulada:
   `?simular_no_atiende=true`) → **reintento** a los `LLAMADA_REINTENTO_MINUTOS` (30 por defecto). En simulado cada
   minuto dura 1 s × `SIM_DELAY_SECONDS` / 4 (30 min → 30 s con la base 4, 7,5 s con `SIM_DELAY_SECONDS=1`). Si
   antes del reintento el proveedor respondió por otro canal, no se lo vuelve a llamar (`respondio`). Si alguien
   aprieta **Llamar** con el reintento programado, esa llamada es el reintento.
3. **Tampoco atiende** → **WhatsApp** (simulado) con el motivo del llamado; si el proveedor **no tiene WhatsApp**,
   **email** (simulado) con la solicitud de cotización (`aviso_enviado`). Quién tiene WhatsApp y el email salen de
   `contacto_proveedores` en `data/historial_compras.json` (datos de ejemplo); si un proveedor no está, se deduce
   de su canal preferido. En la demo, TecnoImport no tiene WhatsApp.

Una falla técnica en la primera llamada (ElevenLabs rechaza el pedido) no es "no atendió": la secuencia queda
`interrumpida` y se ofrece la llamada simulada como hasta ahora. `POST /reset` cancela los reintentos programados.

Cada contacto enviado queda en la colección `contactos` (la lee el detalle del pedido):
`{id, pedido_id, proveedor_id, canal: "whatsapp"|"email"|"llamada", sentido: "enviado", texto, enviado_en (ISO sin
zona), motivo: "solicitud_cotizacion"|"reintento"|"aviso_no_atendio"|"negociacion"}`. La primera llamada es
`solicitud_cotizacion`, la segunda `reintento`, el WhatsApp o el email `aviso_no_atendio` y la llamada de
negociación `negociacion`; en las llamadas, `texto` es el primer mensaje del agente.

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/llamadas/config` | Modo, si está todo configurado, qué falta y qué proveedores tienen teléfono. |
| POST | `/pedidos/{id}/llamar/{proveedor_id}` | Llama para pedir la cotización. 409 si ya respondió o falta configuración. `?simulada=true` fuerza la simulada; `?simular_no_atiende=true` (simulada) hace que nadie atienda, ni la llamada ni el reintento. |
| POST | `/negociaciones/{id}/llamar` | "Aprobar y llamar". Body opcional `{"mensaje": "…"}`. Deja la negociación `aprobada` con `llamada_id`. |
| GET | `/llamadas/{id}` | Estado y transcripción (polling ~1 s): `iniciando → sonando → en_curso → procesando → terminada` (o `fallida` con `error`). Campos opcionales: `intento` (1 o 2), `atendida`, `audio_disponible_hasta` (reales) y `secuencia` (estado, `reintento_en`, pasos `llamada`/`reintento`/`whatsapp`/`email` con su estado, `contacto_ids`). |
| GET | `/pedidos/{id}/llamadas` | Llamadas del pedido. |
