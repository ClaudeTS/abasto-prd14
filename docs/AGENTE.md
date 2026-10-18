# Agente de compras — Abasto

El agente hace la compra entera. Lucía le habla (o le escribe) y el agente:

1. entiende qué pidió;
2. revisa el inventario (stock, mínimo y pronóstico con estacionalidad);
3. le propone la compra;
4. pide cotizaciones y llama a quien no responde;
5. arma el plan y ensaya la negociación;
6. emite las órdenes de compra.

Cada producto está en modo **automático** (el agente compra solo, hasta un tope en pesos) o **manual**
(espera el OK de Lucía). Para el pitch: **Lucía decide qué se compra solo.**

- **Backend (A):** `app/inventario.py`, `app/interpretacion.py`, `app/agente.py` y
  `app/rutas_agente.py`. Está listo y testeado (`tests/test_agente.py`).
- **Pantallas (B):** Agente e Inventario. Este documento es el contrato.

Las pantallas de antes (Feed, Cotizaciones, Plan, Negociación) quedan como vistas de detalle: el agente
usa el mismo pedido (`pedido_demo_oct_2026`) y los mismos endpoints.

**Para desarrollar sin LLM**, levantá el back con `SIM_DELAY_SECONDS=0` y sin `ANTHROPIC_API_KEY`. Después:

1. `GET /agente/ejemplo`, para tener el texto de la demo;
2. `POST /agente` con ese texto.

La compra entera tarda unos segundos (sin key, la negociación da error y la compra sigue igual). En
`docs/ejemplos_agente/` está el JSON de cada estado, sacado de una corrida real en modo fijo (con un
gemelo de prueba en la negociación), para los mocks.

## 1. Los pasos

La corrida tiene siempre estos 9 pasos, en este orden. La UI los muestra como una línea de tiempo con el
`detalle` de cada uno: son frases en primera persona, listas para mostrar.

| `id` | `titulo` | Qué hace | ¿Espera a Lucía? |
|---|---|---|---|
| `entender` | Entender el pedido | Interpreta la voz o el texto con el LLM (prompt `interpretar_pedido`, PROMPTS §7). Sin texto queda `omitido`: solo reposición. | No |
| `inventario` | Revisar el inventario | Valida lo pedido contra el stock y suma la reposición de consumibles: pronóstico del horizonte + mínimo − stock − en camino, redondeado al múltiplo de compra. | No |
| `confirmar` | Tu OK para cotizar | Muestra la propuesta. Lucía puede cambiar cantidades o sacar líneas. | **Sí** (`esperando_confirmacion`) |
| `cotizar` | Pedir cotizaciones | Lanza el simulador de siempre: los 6 proveedores. | No |
| `insistir` | Llamar a quien no responde | A los 25 s llama (simulado salvo `LLAMADAS_MODO=real`) al que no contestó: en la demo, Papelera del Sur. | No |
| `revisar` | Revisar respuestas dudosas | Si una cotización quedó para revisar (el IVA de Compuservice), espera que Lucía la confirme. | **Sí** (`esperando_revision`) |
| `optimizar` | Armar el plan de compra | El solver de siempre (`POST /pedidos/{id}/optimizar` por dentro). | No |
| `negociar` | Ensayar la negociación | Gemelo del proveedor sugerido por el plan (`oportunidad_negociacion`). Si falla, queda en `error` y la compra sigue. | No |
| `ordenes` | Órdenes de compra | Una orden por proveedor. Sale sola si todas sus líneas son automáticas y no superan su tope; si no, espera. | **Sí** (`esperando_aprobacion`) |

Estados de un paso: `pendiente`, `en_curso`, `esperando`, `hecho`, `omitido`, `error`.

## 2. Estados de la corrida → qué muestra la UI

| `estado` | Pantalla |
|---|---|
| `en_curso` | Línea de tiempo con el paso `en_curso` animado. Sin botones, salvo "Cancelar". |
| `esperando_confirmacion` | Tabla de `propuesta`. Cada línea muestra cantidad (editable), fecha, `origen` ("lo pediste" / "reposición"), `evidencia` y `dudas`. Botones: "Confirmar y pedir cotizaciones" y "Cancelar". |
| `esperando_revision` | Una tarjeta por cada elemento de `revision`, con su `pregunta`. Si `pide_iva`: "Incluyen IVA" / "Son + IVA". Si no: "Está bien así". |
| `esperando_aprobacion` | Tarjetas de `ordenes`. Las `enviada_simulada` con `aprobada_por: "agente"` llevan "La mandó el agente" y el motivo de cada línea. Las `esperando_aprobacion` muestran `motivos`, `mensaje` y los botones "Aprobar" / "Rechazar". |
| `completada` | `resumen` y las órdenes. |
| `error` | `error`, y el paso con `estado: "error"` marcado. Botón "Empezar de nuevo" (`POST /agente`; si el pedido ya se cotizó, `POST /reset` antes). |
| `cancelada` | "Cancelaste la compra." |

`avisos` (lista de frases) va siempre visible arriba si no está vacía: lo que no estaba en el catálogo,
el que no respondió, las relajaciones del plan, etc.

**Polling:** `GET /agente/{id}` cada 1,5 s mientras el estado no sea `completada`, `error` ni `cancelada`.
Al abrir la pantalla, `GET /agente/actual`: si da 404, mostrar el micrófono.

## 3. Endpoints

Todos los errores tienen la forma de siempre: `{"error": "mensaje legible", "detalle": ...}`.

| Método | Ruta | Body | Devuelve | Errores |
|---|---|---|---|---|
| GET | `/inventario?horizonte_meses=1` | — | `Inventario` | 422 si el horizonte no va de 1 a 6 |
| PATCH | `/inventario/{producto_id}` | `{modo?, tope_automatico_uyu?, stock_actual?, stock_minimo?}` | `ItemInventario` | 404 producto, 422 negativo |
| GET | `/agente/ejemplo` | — | `{texto}`: la frase de la demo | — |
| POST | `/agente` | `NuevaCorrida` (todo opcional) | `CorridaAgente` (201) | 409 si hay otra compra en curso (`detalle.corrida_id`) o si el pedido ya se cotizó (reset) |
| GET | `/agente/actual` | — | la última `CorridaAgente` | 404 si nunca hubo |
| GET | `/agente/{id}` | — | `CorridaAgente` | 404 |
| POST | `/agente/{id}/confirmar` | `{lineas?: [{producto_id, cantidad}]}` | `CorridaAgente` | 409 si no espera confirmación, 422 producto que no está en la propuesta |
| POST | `/agente/{id}/ordenes/{orden_id}/aprobar` | — | `CorridaAgente` | 404, 409 si ya se resolvió |
| POST | `/agente/{id}/ordenes/{orden_id}/rechazar` | — | `CorridaAgente` | 404, 409 |
| POST | `/agente/{id}/cancelar` | — | `CorridaAgente` | 409 si ya terminó |

Detalles:

- **`PATCH /inventario/...`:** `http()` de `api.ts` hoy acepta solo `GET | POST`; hay que sumarle
  `"PATCH"` (CORS ya permite todos los métodos). Manda solo los campos que cambian;
  `tope_automatico_uyu: null` es "sin tope". El modo y el tope valen para las órdenes que el agente
  todavía no emitió, también las de la compra en curso. `POST /reset` vuelve todo a
  `data/inventario_demo.json`.
- **`POST /agente/{id}/confirmar`:** sin body, confirma la propuesta tal cual. Con `lineas` hay que
  mandar **todas** las que quedan: la que falta o va con cantidad 0 se saca. No se pueden agregar
  productos.
- **Revisión:** no tiene endpoint propio. Es el de siempre, `POST /cotizaciones/{cotizacion_id}/confirmar`
  (`confirmarCampo(id, "iva", true|false)` o `confirmarLectura(id)` en `api.ts`). El agente lo ve en el
  próximo polling y sigue solo.
- **Negociación:** la orden del proveedor negociado trae `negociacion_id`. El panel es el de siempre:
  `GET /negociaciones/{id}`, `POST /negociaciones/{id}/aprobar` y `POST /negociaciones/{id}/llamar`.
  Sugerencia: en esa tarjeta, "Ver negociación" o el `mensaje_propuesto` con "Aprobar mensaje",
  independiente de aprobar la orden.
- **Llamadas:** `llamada_ids` lista las que hizo el agente. `GET /llamadas/{id}` alimenta el
  `PanelLlamada` que ya existe.
- **Detalle:** feed (`/pedidos/{id}/mensajes`, `/proveedores/estado`), cotizaciones y plan
  (`GET /pedidos/{id}/plan`, cuando `optimizar` está `hecho`): los endpoints de siempre, con el
  `pedido_id` de la corrida.

### `NuevaCorrida`

```json
{
  "texto": "Abasto, armá la compra del mes. Entran diez personas nuevas el 28…",
  "horizonte_meses": null,
  "esperar_confirmacion": true,
  "llamar_si_no_responde": true,
  "negociar": true
}
```

- **`texto`:** lo que dijo o escribió Lucía. Vacío o ausente quiere decir "reponé lo de siempre".
- **`horizonte_meses`:** de 1 a 6. Si es `null`, vale el que dijo Lucía ("para los próximos dos meses") o
  el de siempre (1).
- **`esperar_confirmacion: false`:** saltea el OK previo, salvo que haya dudas.

## 4. Tipos (para `types.ts`)

Los montos llegan como `number` (sin IVA, en UYU) y las fechas como `"AAAA-MM-DD"`. Los `*_en` son
fecha y hora ISO, sin zona, igual que en el resto de la API.

```ts
export type ModoCompra = "automatico" | "manual";

export interface ItemInventario {
  producto_id: string;
  nombre: string;
  nombre_corto: string; // para frases: "resmas", "tóner"
  unidad: "unidad" | "l" | "kg";
  tipo: "consumible" | "equipamiento";
  stock_actual: number;
  stock_minimo: number;
  en_camino: number; // en órdenes que el agente ya mandó
  multiplo_compra: number; // resmas de a 5 (caja), desinfectante de a 5 L (bidón)
  modo: ModoCompra;
  tope_automatico_uyu: number | null; // sin IVA; null = sin tope
  proveedores: { id: string; nombre: string }[];
  historial: { mes: string; cantidad: number }[]; // 24 meses, "2024-10" … "2026-09"
  pronostico: {
    nivel: number; // promedio de los últimos 12 meses
    consumo_diario: number;
    meses: { mes: string; indice: number; cantidad: number }[]; // índice estacional del mes
    total: number;
    evidencia: string; // la cuenta, para mostrar
  } | null; // null: equipamiento, se compra cuando se pide
  reposicion: {
    cantidad: number; // 0 = alcanza
    necesario_para: string;
    cobertura_dias: number | null; // null: ya está bajo el mínimo
    evidencia: string;
  } | null;
  alerta: "bajo_minimo" | "reponer" | null;
}

export interface Inventario {
  fecha: string; // el "hoy" de la demo: 2026-10-20
  horizonte_meses: number;
  meses_pronostico: string[]; // ["2026-11"]
  plazo_minimo_dias: number; // 3: lo antes que puede llegar algo
  productos: ItemInventario[];
}

export type PasoId =
  | "entender" | "inventario" | "confirmar" | "cotizar" | "insistir"
  | "revisar" | "optimizar" | "negociar" | "ordenes";

export interface PasoAgente {
  id: PasoId;
  titulo: string;
  estado: "pendiente" | "en_curso" | "esperando" | "hecho" | "omitido" | "error";
  detalle: string | null;
  inicio: string | null;
  fin: string | null;
}

export interface LineaPropuesta {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  unidad: "unidad" | "l" | "kg";
  cantidad: number; // 0 si Lucía no dijo cuántos y no hay cuenta: tiene una duda
  necesario_para: string;
  origen: "pedido" | "reposicion"; // lo pidió Lucía | lo calculó el inventario
  modo: ModoCompra;
  tope_automatico_uyu: number | null;
  stock_actual: number;
  evidencia: string;
  dudas: string[];
}

export interface RevisionPendiente {
  cotizacion_id: string;
  proveedor_id: string;
  proveedor_nombre: string;
  campos_dudosos: string[];
  pide_iva: boolean; // sí: "Incluyen IVA" / "Son + IVA"; no: "Está bien así"
  pregunta: string;
}

export interface LineaOrden {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  unidad: "unidad" | "l" | "kg";
  cantidad: number;
  precio_unitario_sin_iva: number;
  subtotal: number;
  aprobacion: "automatica" | "manual" | "supera_tope";
  motivo: string;
  cotizacion_id: string | null;
  evidencia: string | null; // de la cotización: de dónde sale el precio
}

export interface OrdenCompra {
  id: string; // "oc_papelera_del_sur"
  numero: string; // "OC-1003"
  proveedor_id: string;
  proveedor_nombre: string;
  lineas: LineaOrden[];
  envio: number;
  total_sin_iva: number; // con envío
  total_con_iva: number;
  requiere_aprobacion: boolean;
  motivos: string[]; // por qué espera: "Tóner: $ 25.574 supera el tope automático de $ 20.000."
  estado: "esperando_aprobacion" | "enviada_simulada" | "rechazada";
  aprobada_por: "agente" | "lucia" | null;
  negociacion_id: string | null;
  mensaje: string; // el WhatsApp de la orden (simulado)
  enviada_en: string | null;
}

export interface CorridaAgente {
  id: string;
  pedido_id: string;
  texto: string | null;
  horizonte_meses: number;
  opciones: {
    horizonte_meses: number | null;
    esperar_confirmacion: boolean;
    llamar_si_no_responde: boolean;
    negociar: boolean;
  };
  estado:
    | "en_curso" | "esperando_confirmacion" | "esperando_revision" | "esperando_aprobacion"
    | "completada" | "error" | "cancelada";
  pasos: PasoAgente[];
  interpretacion: {
    origen: "llm" | "fijo"; // fijo: sin LLM, la frase de la demo
    items: { producto_id: string; descripcion: string; cantidad: number | null;
             necesario_para: string | null; evidencia: string }[];
    no_entendido: string[];
    excluir: string[];
    horizonte_meses: number | null;
    evidencia_horizonte: string | null;
    dudas: string[];
  } | null;
  propuesta: LineaPropuesta[];
  avisos: string[];
  revision: RevisionPendiente[];
  llamada_ids: string[];
  sin_respuesta: string[]; // proveedores que nunca contestaron
  negociacion_id: string | null;
  ordenes: OrdenCompra[];
  resumen: string | null;
  error: string | null;
  creada_en: string;
  actualizada_en: string;
}
```

## 5. Voz

La voz es dictado del navegador (Web Speech API). El texto que sale va a `POST /agente` como `texto`.
No hace falta nada en el back.

```ts
const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
// Sin SR (Firefox): mostrar solo el textarea.
const rec = new SR();
rec.lang = "es-UY";
rec.interimResults = true; // el texto aparece mientras habla
rec.continuous = false; // corta solo al terminar la frase
rec.onresult = (e: any) =>
  setTexto(Array.from(e.results).map((r: any) => r[0].transcript).join(" "));
rec.onend = () => setEscuchando(false);
rec.start();
```

- Funciona en Chrome y Edge, en `https` (Vercel) o `localhost`. Pide permiso de micrófono la primera vez.
- Sugerencia: no mandar apenas termina de hablar. Mostrar el texto en el textarea (editable) y un botón
  "Mandar", así Lucía corrige si el dictado entendió mal.
- Botón "Usar el ejemplo" (`GET /agente/ejemplo`) para la demo sin micrófono.
- **Sin LLM** (sin key, o si falla), el back solo entiende la frase de la demo, escrita o dictada: no
  importan tildes, puntuación ni "10" en vez de "diez". Cualquier otro pedido da `error` con el motivo.

## 6. Pantallas sugeridas

**Agente** (nueva home):

- Arriba: micrófono, textarea, "Usar el ejemplo" y "Comprar".
- Abajo: la línea de tiempo de los 9 pasos y, según el estado, la tarjeta de la tabla del §2.
- Desde cada paso, un link a la vista de detalle de siempre: `cotizar` → Feed, `optimizar` → Plan,
  `negociar` → Negociación.

**Inventario:**

- Una fila por producto: stock, mínimo, en camino, alerta (`bajo_minimo` en rojo, `reponer` en ámbar)
  y la reposición con su evidencia.
- Gráfico de los 24 meses de `historial`, con los meses de `pronostico` punteados. Ahí se ve la
  estacionalidad: resmas y tóner bajan en enero y febrero, y el desinfectante sube en invierno.
- Selector de horizonte (1 a 6 meses): `GET /inventario?horizonte_meses=N`.
- Por producto, un switch Automático/Manual y el tope en pesos (`PATCH`).

Los números que se muestran tienen que tener su evidencia al lado (AGENTS §10): `pronostico.evidencia`,
`reposicion.evidencia`, `LineaPropuesta.evidencia` y `LineaOrden.evidencia`.

## 7. Qué cambia en la demo

Con los datos de `data/inventario_demo.json`, la frase de la demo arma exactamente el pedido de
siempre: 10 notebooks y 15 sillas (lo pedido), más 150 resmas, 8 tóner y 60 L de desinfectante
(reposición). Por eso el plan y el ahorro del guion no cambian: $ 498.454 + IVA y 8,1 %. Las órdenes:

| Orden | Proveedor | Qué lleva | Sale |
|---|---|---|---|
| OC-1001 | Compuservice | notebooks (manual), tóner ($ 25.574, supera su tope de $ 20.000) | espera a Lucía |
| OC-1002 | Ofisillas | sillas (manual) + la negociación | espera a Lucía |
| OC-1003 | Papelera del Sur | resmas ($ 26.804, tope $ 30.000) y desinfectante ($ 6.787, tope $ 10.000) | **sola** |

Para el guion (`docs/PITCH_Y_DEMO.md`, de B), estos momentos:

1. "Abasto, armá la compra del mes…" por voz.
2. El agente muestra el porqué de cada línea, con la cuenta de las resmas: noviembre viene 14 % arriba
   y ya están bajo el mínimo.
3. A los 25 s llama solo a Papelera del Sur.
4. Pregunta por el IVA de Compuservice.
5. Manda sola la orden de Papelera y deja las otras para Lucía.

En `/vision`, la Capa 3 ("Predicción de precios y consumo") pasa a tener una parte real: el
pronóstico de consumo del Inventario. La de precios sigue siendo diseño.

Para mostrar el control, en Inventario, antes de que el agente emita las órdenes (el reset para
repetir la compra vuelve los modos a los de siempre):

- Pasar el desinfectante a manual: la orden de Papelera también espera.
- Pasar el tóner a "sin tope": la orden de Compuservice sigue esperando, por los notebooks.
