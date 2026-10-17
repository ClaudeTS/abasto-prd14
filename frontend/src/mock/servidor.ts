import pedidoJson from "../../../data/pedido_demo.json";
import respuestasJson from "../../../data/respuestas_fijas.json";
import { ApiError } from "../lib/errores";
import { diasEntre, formatNumero, pesos, porcentaje, precioUnitario } from "../lib/format";
import { nombreProveedor, proveedor } from "../lib/proveedores";
import { guardarSesion, leerSesion } from "../lib/sesion";
import type {
  Asignacion,
  Canal,
  ConfigCompra,
  ConfigLlamadas,
  Conversion,
  Cotizacion,
  EstadoPedido,
  ItemCotizado,
  LineaPedido,
  Llamada,
  MensajeCrudo,
  Negociacion,
  Pedido,
  PedidoDemo,
  Plan,
  Producto,
} from "../types";
import { EXTRACCIONES, type ItemExtraido } from "./extracciones";
import { ensayarEstrategias, mensajePropuesto, type Alternativa } from "./negociaciones";

// Backend simulado en el navegador. Reproduce el flujo de la demo con data/*.json para que el
// frontend funcione sin FastAPI: simulador con demoras, extracción, reglas post-LLM, un solver
// por fuerza bruta equivalente al MILP de ARQUITECTURA.md §6 y la negociación ensayada.

const VELOCIDAD = Math.max(0.05, Number(import.meta.env.VITE_MOCK_SPEED ?? "1") || 1);

const DEMO: PedidoDemo = {
  pedido: pedidoJson.pedido as Pedido,
  catalogo: pedidoJson.catalogo as Producto[],
  config: pedidoJson.config as ConfigCompra,
  conversiones: pedidoJson.conversiones as Record<string, Conversion>,
};
const RESPUESTAS = respuestasJson.respuestas;

interface EstadoMock {
  cotizarEn: number | null;
  ivaConfirmado: Record<string, boolean>;
  lecturaConfirmada: Record<string, true>;
  plan: Plan | null;
  negociaciones: Record<string, Negociacion>;
  aprobado: boolean;
  llamadas?: Record<string, LlamadaMock>;
}

/** Llamada simulada: el guion se arma al llamar y el estado se deriva del reloj (como los mensajes). */
interface LlamadaMock {
  base: Llamada;
  inicio: number; // ms epoch
  /** Momento (ms desde inicio) en que se escucha cada turno. */
  turnos: { rol: "abasto" | "proveedor"; texto: string; en: number }[];
  atiende: number; // ms desde inicio: sonando → en_curso
  corta: number; // ms desde inicio: en_curso → procesando
  fin: number; // ms desde inicio: procesando → terminada
  resultado: Llamada["resultado"];
}

const INICIAL: EstadoMock = {
  cotizarEn: null,
  ivaConfirmado: {},
  lecturaConfirmada: {},
  plan: null,
  negociaciones: {},
  aprobado: false,
  llamadas: {},
};

const leer = (): EstadoMock => leerSesion("mock", INICIAL);
const guardar = (e: EstadoMock) => guardarSesion("mock", e);
const esperar = (ms: number) => new Promise((r) => setTimeout(r, ms * VELOCIDAD));

// ───────────────────────── Pedido ─────────────────────────

function estadoPedido(e: EstadoMock): EstadoPedido {
  if (!e.cotizarEn) return "nuevo";
  if (e.aprobado) return "aprobado";
  if (Object.keys(e.negociaciones).length) return "negociando";
  if (e.plan) return "optimizado";
  const listos = mensajes().filter((m) => m.estado === "extraido").length;
  return listos === RESPUESTAS.length ? "cotizado" : "cotizando";
}

export async function pedidoDemo(): Promise<PedidoDemo> {
  return { ...DEMO, pedido: { ...DEMO.pedido, estado: estadoPedido(leer()) } };
}

export async function cotizar(): Promise<{ estado: string }> {
  const e = leer();
  if (!e.cotizarEn) guardar({ ...e, cotizarEn: Date.now() });
  return { estado: "cotizando" };
}

// ───────────────────────── Simulador + extracción ─────────────────────────

function htmlATexto(html: string): string {
  return html
    .replace(/<\/(h\d|p|tr)>/gi, "\n")
    .replace(/<\/t[dh]>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

export function mensajes(): MensajeCrudo[] {
  const e = leer();
  const { cotizarEn } = e;
  if (!cotizarEn) return [];
  const ahora = Date.now();
  return RESPUESTAS.flatMap((r) => {
    // Si Abasto lo llamó antes de que contestara, la respuesta es la llamada (llega al cortar).
    const llamada = llamadaDeCotizacion(e, r.proveedor_id);
    const porWhatsapp = cotizarEn + r.demora_segundos * 1000 * VELOCIDAD;
    const llegada = llamada ? llamada.inicio + llamada.fin : porWhatsapp;
    if (ahora < llegada) return [];
    const lectura = (EXTRACCIONES[r.proveedor_id]?.segundos_lectura ?? 3) * 1000 * VELOCIDAD;
    const canal: Canal = llamada ? "llamada" : (r.canal as Canal);
    const mensaje: MensajeCrudo = {
      id: `msg_${r.proveedor_id}`,
      pedido_id: DEMO.pedido.id,
      proveedor_id: r.proveedor_id,
      canal,
      contenido_texto: llamada
        ? textoTranscripcion(llamada)
        : canal === "foto"
          ? null
          : canal === "pdf"
            ? htmlATexto(r.contenido)
            : r.contenido,
      archivo: canal === "pdf" || canal === "foto" ? `mock:${canal}:${r.proveedor_id}` : null,
      recibido_en: new Date(llegada).toISOString(),
      estado: ahora < llegada + 500 ? "pendiente" : ahora < llegada + 500 + lectura ? "leyendo" : "extraido",
    };
    return [mensaje];
  });
}

/** Reglas post-LLM (en código, como pide ARQUITECTURA.md §5): USD → UYU, IVA y unidades. */
function normalizar(item: ItemExtraido, incluyeIva: boolean): ItemCotizado {
  const { tipo_cambio_usd: tc, iva } = DEMO.config;
  let precio = item.precio;
  const pasos: string[] = [];
  if (item.moneda === "USD") {
    precio = precio * tc;
    pasos.push(`USD ${formatNumero(item.precio)} × ${formatNumero(tc, 2)} = UYU ${formatNumero(precio)}`);
  }
  if (incluyeIva) {
    precio = precio / (1 + iva);
    pasos.push(`con IVA / ${formatNumero(1 + iva, 2)}`);
  }
  const conversion = DEMO.conversiones[item.unidad_original];
  if (conversion) {
    precio = precio / conversion.factor;
    pasos.push(`${item.unidad_original} → ${conversion.factor} ${conversion.a}`);
  }
  return {
    producto_id: item.producto_id,
    descripcion_original: item.descripcion_original,
    precio_unitario_sin_iva: Math.round(precio * 100) / 100,
    precio_original: item.precio,
    moneda_original: item.moneda,
    incluye_iva_original: incluyeIva,
    unidad_original: item.unidad_original,
    conversion_aplicada: pasos.length ? pasos.join(" · ") : null,
    cantidad_minima: item.cantidad_minima,
    evidencia: item.evidencia,
  };
}

function construirCotizacion(proveedorId: string, e: EstadoMock): Cotizacion {
  const x = EXTRACCIONES[proveedorId];
  const confirmado = e.ivaConfirmado[proveedorId];
  const lecturaOk = e.lecturaConfirmada?.[proveedorId] === true;
  const dudosos = confirmado === undefined ? x.campos_dudosos : x.campos_dudosos.filter((c) => c !== "iva");
  // Mismo criterio que el backend (CONTRATO_BACKEND.md): confianza < 0,6 o una duda que cambia el precio.
  const estado =
    confirmado !== undefined || lecturaOk
      ? "confirmada"
      : x.confianza < 0.6 || dudosos.length > 0
        ? "revisar"
        : "valida";
  return {
    estado,
    id: `cot_${proveedorId}`,
    mensaje_id: `msg_${proveedorId}`,
    proveedor_id: proveedorId,
    items: x.items.map((i) => normalizar(i, confirmado ?? i.incluye_iva_original)),
    costo_envio: x.costo_envio,
    pedido_minimo_total: x.pedido_minimo_total,
    plazo_pago_dias: x.plazo_pago_dias,
    lead_time_dias: x.lead_time_dias,
    validez_dias: x.validez_dias,
    observaciones:
      confirmado === undefined
        ? x.observaciones
        : [
            ...x.observaciones.filter((o) => !/aclara.*IVA/i.test(o)),
            `IVA confirmado por quien compra: ${confirmado ? "precios con IVA incluido" : "precios más IVA"}`,
          ],
    confianza: confirmado === undefined ? x.confianza : 1,
    campos_dudosos: dudosos,
  };
}

export function cotizaciones(): Cotizacion[] {
  const e = leer();
  return mensajes()
    .filter((m) => m.estado === "extraido" && EXTRACCIONES[m.proveedor_id])
    .map((m) => construirCotizacion(m.proveedor_id, e));
}

export async function confirmar(cotizacionId: string, campo: string, valor: boolean): Promise<Cotizacion> {
  await esperar(400);
  const proveedorId = cotizacionId.replace(/^cot_/, "");
  if (!EXTRACCIONES[proveedorId]) throw new ApiError(`No existe la cotización ${cotizacionId}`);
  if (campo !== "iva") throw new ApiError(`El campo "${campo}" no se puede confirmar todavía`);
  const e = leer();
  const nuevo = { ...e, ivaConfirmado: { ...e.ivaConfirmado, [proveedorId]: valor } };
  guardar(nuevo);
  return construirCotizacion(proveedorId, nuevo);
}

export async function confirmarLectura(cotizacionId: string): Promise<Cotizacion> {
  await esperar(400);
  const proveedorId = cotizacionId.replace(/^cot_/, "");
  if (!EXTRACCIONES[proveedorId]) throw new ApiError(`No existe la cotización ${cotizacionId}`);
  const e = leer();
  const x = EXTRACCIONES[proveedorId];
  if (x.campos_dudosos.includes("iva") && e.ivaConfirmado[proveedorId] === undefined) {
    throw new ApiError("Falta indicar si los precios incluyen IVA");
  }
  const nuevo = { ...e, lecturaConfirmada: { ...(e.lecturaConfirmada ?? {}), [proveedorId]: true as const } };
  guardar(nuevo);
  return construirCotizacion(proveedorId, nuevo);
}

// ───────────────────────── Archivos (PDF y foto simulados) ─────────────────────────

function escaparXml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function archivoUrl(archivo: string): string {
  const [, canal, proveedorId] = archivo.split(":");
  const r = RESPUESTAS.find((x) => x.proveedor_id === proveedorId);
  if (!r) return "";
  if (canal === "pdf") {
    const html = `<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:Arial,Helvetica,sans-serif;color:#1f2937;margin:0;padding:28px 32px;font-size:12px;background:#fff}
h2{color:#0c4a6e;border-bottom:3px solid #0c4a6e;padding-bottom:6px;margin:0 0 8px;font-size:20px}
table{border-collapse:collapse;width:100%;margin:14px 0}th{background:#e0f2fe;text-align:left}
th,td{border:1px solid #cbd5e1;padding:6px 8px}td:nth-child(n+3){text-align:right}p{line-height:1.5;margin:6px 0}
</style></head><body>${r.contenido}</body></html>`;
    return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
  }
  const lineas = r.contenido.split("\n");
  const renglones = Array.from({ length: 14 }, (_, i) => 90 + i * 46)
    .map((y) => `<line x1="0" x2="640" y1="${y}" y2="${y}" stroke="#bfd3e6" stroke-width="1"/>`)
    .join("");
  const texto = lineas
    .map((l, i) => `<text x="${i === 0 ? 220 : 46}" y="${80 + i * 46 + (i > 0 ? 46 : 0)}">${escaparXml(l)}</text>`)
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="520" viewBox="0 0 640 520">
<rect width="640" height="520" fill="#f4ecd8"/>${renglones}<line x1="34" x2="34" y1="0" y2="520" stroke="#e9a3a3" stroke-width="1.5"/>
<g transform="rotate(-2 320 260)" font-family="Segoe Print, Bradley Hand, Comic Sans MS, cursive" font-size="25" fill="#1e3a8a">${texto}</g></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// ───────────────────────── Optimización (equivalente al MILP, por fuerza bruta) ─────────────────────────

interface Opcion {
  cot: Cotizacion;
  item: ItemCotizado;
}

interface Reglas {
  maxProv: number | null;
  minimos: boolean;
  plazo: boolean;
}

const W_RIESGO = 0.03;
const W_PLAZO = 0.002;
const PENALIZACION_MINIMO = 500;

const fechaPedido = () => DEMO.pedido.fecha ?? new Date().toISOString().slice(0, 10);
const nombreProducto = (id: string) => DEMO.catalogo.find((p) => p.id === id)?.nombre ?? id;

function opcionesTodas(linea: LineaPedido, cots: Cotizacion[]): Opcion[] {
  return cots.flatMap((cot) =>
    cot.items.filter((i) => i.producto_id === linea.producto_id).map((item) => ({ cot, item })),
  );
}

function opciones(linea: LineaPedido, cots: Cotizacion[], r: Reglas): Opcion[] {
  const dias = diasEntre(fechaPedido(), linea.necesario_para);
  return opcionesTodas(linea, cots)
    .filter(({ item }) => !r.minimos || (item.cantidad_minima ?? 0) <= linea.cantidad)
    .filter(({ cot }) => !r.plazo || cot.lead_time_dias <= dias);
}

function evaluar(lineas: LineaPedido[], combo: Opcion[], r: Reglas): number | null {
  const gasto = new Map<string, { cot: Cotizacion; total: number }>();
  let objetivo = 0;
  combo.forEach(({ cot, item }, k) => {
    const sub = item.precio_unitario_sin_iva * lineas[k].cantidad;
    const conf = proveedor(cot.proveedor_id).confiabilidad;
    objetivo += sub + W_RIESGO * sub * (1 - conf) - W_PLAZO * sub * cot.plazo_pago_dias;
    if (!r.minimos && (item.cantidad_minima ?? 0) > lineas[k].cantidad) objetivo += PENALIZACION_MINIMO;
    const g = gasto.get(cot.proveedor_id) ?? { cot, total: 0 };
    g.total += sub;
    gasto.set(cot.proveedor_id, g);
  });
  if (r.maxProv !== null && gasto.size > r.maxProv) return null;
  for (const { cot, total } of gasto.values()) {
    objetivo += cot.costo_envio;
    if (cot.pedido_minimo_total && total < cot.pedido_minimo_total) {
      if (r.minimos) return null;
      objetivo += PENALIZACION_MINIMO;
    }
  }
  return objetivo;
}

function mejorCombinacion(lineas: LineaPedido[], cots: Cotizacion[], r: Reglas): Opcion[] | null {
  const porLinea = lineas.map((l) => opciones(l, cots, r));
  if (porLinea.some((o) => o.length === 0)) return null;
  const mejor = { combo: null as Opcion[] | null, valor: Infinity };
  const recorrer = (k: number, actual: Opcion[]) => {
    if (k === lineas.length) {
      const valor = evaluar(lineas, actual, r);
      if (valor !== null && valor < mejor.valor) Object.assign(mejor, { combo: actual, valor });
      return;
    }
    for (const o of porLinea[k]) recorrer(k + 1, [...actual, o]);
  };
  recorrer(0, []);
  return mejor.combo;
}

function costoDe(lineas: LineaPedido[], combo: Opcion[]): number {
  const envios = new Map(combo.map(({ cot }) => [cot.proveedor_id, cot.costo_envio]));
  const subtotal = combo.reduce((s, { item }, k) => s + item.precio_unitario_sin_iva * lineas[k].cantidad, 0);
  return subtotal + [...envios.values()].reduce((a, b) => a + b, 0);
}

function motivoNoMasBarato(linea: LineaPedido, barato: Opcion, elegido: Opcion): string {
  const nombre = nombreProveedor(barato.cot.proveedor_id);
  const dias = diasEntre(fechaPedido(), linea.necesario_para);
  if ((barato.item.cantidad_minima ?? 0) > linea.cantidad)
    return `${nombre} exige un mínimo de ${barato.item.cantidad_minima} unidades y se necesitan ${linea.cantidad}`;
  if (barato.cot.lead_time_dias > dias)
    return `${nombre} entrega en ${barato.cot.lead_time_dias} días y se necesita en ${dias}`;
  if (barato.cot.pedido_minimo_total)
    return `${nombre} tiene un pedido mínimo de ${pesos(barato.cot.pedido_minimo_total)}`;
  return `sumando envío, confiabilidad y plazo de pago conviene ${nombreProveedor(elegido.cot.proveedor_id)}`;
}

function resolverPlan(cots: Cotizacion[]): Plan {
  const habitual = DEMO.pedido.proveedor_habitual_id;
  const pasos: { reglas: Reglas; nota: string | null }[] = [
    { reglas: { maxProv: 4, minimos: true, plazo: true }, nota: null },
    { reglas: { maxProv: null, minimos: true, plazo: true }, nota: "se permitió comprar a más de 4 proveedores" },
    {
      reglas: { maxProv: null, minimos: false, plazo: true },
      nota: `se aceptaron mínimos no cumplidos con una penalización de ${pesos(PENALIZACION_MINIMO)}`,
    },
    {
      reglas: { maxProv: null, minimos: false, plazo: false },
      nota: "se aceptaron proveedores que entregan después de la fecha necesaria",
    },
  ];

  const relajaciones: string[] = [];
  const cubiertas = DEMO.pedido.lineas.filter((l) => opcionesTodas(l, cots).length > 0);
  DEMO.pedido.lineas
    .filter((l) => !cubiertas.includes(l))
    .forEach((l) => relajaciones.push(`nadie cotizó ${nombreProducto(l.producto_id)}: queda fuera del plan`));

  let combo: Opcion[] | null = null;
  for (const paso of pasos) {
    combo = mejorCombinacion(cubiertas, cots, paso.reglas);
    if (combo) break;
    if (paso.nota) relajaciones.push(paso.nota);
  }
  if (!combo) throw new ApiError("No se encontró un plan factible ni relajando restricciones.");
  const elegido = combo;

  const asignaciones: Asignacion[] = elegido.map(({ cot, item }, k) => ({
    producto_id: cubiertas[k].producto_id,
    proveedor_id: cot.proveedor_id,
    cantidad: cubiertas[k].cantidad,
    precio_unitario_sin_iva: item.precio_unitario_sin_iva,
    subtotal: Math.round(item.precio_unitario_sin_iva * cubiertas[k].cantidad * 100) / 100,
  }));
  const costoTotal = costoDe(cubiertas, elegido);

  // Baseline: todo al habitual; lo que el habitual no vende, al más barato.
  const baseline = cubiertas.map(
    (l) =>
      opcionesTodas(l, cots).find(({ cot }) => cot.proveedor_id === habitual) ??
      opcionesTodas(l, cots).sort((a, b) => a.item.precio_unitario_sin_iva - b.item.precio_unitario_sin_iva)[0],
  );
  const costoBaseline = costoDe(cubiertas, baseline);
  const ahorro = costoBaseline - costoTotal;

  const comparables = cubiertas.map((_, k) => baseline[k].cot.proveedor_id === habitual);
  const baseComparable = costoDe(
    cubiertas.filter((_, k) => comparables[k]),
    baseline.filter((_, k) => comparables[k]),
  );
  const noComparable = asignaciones.filter((_, k) => !comparables[k]).reduce((s, a) => s + a.subtotal, 0);
  const ahorroComparable = baseComparable - (costoTotal - noComparable);

  const casos = cubiertas.flatMap((l, k) => {
    const barato = opcionesTodas(l, cots).sort(
      (a, b) => a.item.precio_unitario_sin_iva - b.item.precio_unitario_sin_iva,
    )[0];
    if (barato.cot.proveedor_id === elegido[k].cot.proveedor_id) return [];
    return [{ linea: l, barato, elegido: elegido[k], motivo: motivoNoMasBarato(l, barato, elegido[k]) }];
  });

  const usados = [...new Set(asignaciones.map((a) => a.proveedor_id))];
  const brechas = usados.map((id) => ({
    id,
    brecha: cubiertas.reduce((s, l, k) => {
      if (elegido[k].cot.proveedor_id !== id) return s;
      const mejor = Math.min(...opcionesTodas(l, cots).map((o) => o.item.precio_unitario_sin_iva));
      return s + (elegido[k].item.precio_unitario_sin_iva - mejor) * l.cantidad;
    }, 0),
  }));
  const oportunidad = brechas.filter((b) => b.brecha > 0).sort((a, b) => b.brecha - a.brecha)[0];

  const ahorroPct = costoBaseline ? (ahorro / costoBaseline) * 100 : 0;
  const ahorroPctComparable = baseComparable ? (ahorroComparable / baseComparable) * 100 : null;
  const nombres = usados.map(nombreProveedor);

  // Explicación: en el backend la escribe el LLM (prompt explicar_plan) a partir de estos números.
  const oraciones = [
    `Comprando a ${usados.length} proveedores (${nombres.slice(0, -1).join(", ")}${nombres.length > 1 ? " y " : ""}${nombres[nombres.length - 1]}) el pedido cuesta ${pesos(costoTotal)} sin IVA, ${pesos(ahorro)} menos (${porcentaje(ahorroPct)}) que comprarle todo a ${nombreProveedor(habitual)}${ahorroPctComparable !== null && comparables.includes(false) ? `; sobre lo que ${nombreProveedor(habitual)} sí vende, el ahorro es de ${porcentaje(ahorroPctComparable)}` : ""}.`,
    ...casos.map(
      (c) =>
        `${nombreProducto(c.linea.producto_id)}: no se compra al más barato porque ${c.motivo}, así que va a ${nombreProveedor(c.elegido.cot.proveedor_id)} a ${precioUnitario(c.elegido.item.precio_unitario_sin_iva)} por unidad.`,
    ),
    `Todos los precios se comparan sin IVA y los cotizados en dólares se convirtieron a ${formatNumero(DEMO.config.tipo_cambio_usd, 2)} pesos.`,
  ];
  if (relajaciones.length) oraciones.push(`Para encontrar un plan factible ${relajaciones.join("; ")}.`);

  return {
    pedido_id: DEMO.pedido.id,
    asignaciones,
    costo_total: Math.round(costoTotal * 100) / 100,
    costo_baseline: Math.round(costoBaseline * 100) / 100,
    ahorro: Math.round(ahorro * 100) / 100,
    ahorro_pct: Math.round(ahorroPct * 100) / 100,
    ahorro_comparable: Math.round(ahorroComparable * 100) / 100,
    ahorro_pct_comparable: ahorroPctComparable === null ? null : Math.round(ahorroPctComparable * 100) / 100,
    proveedores_usados: usados,
    restricciones_activas: casos.map(
      (c) => `${nombreProducto(c.linea.producto_id)}: ${c.motivo}`,
    ),
    relajaciones,
    explicacion: oraciones.join(" "),
    oportunidad_negociacion: oportunidad?.id ?? null,
  };
}

export async function optimizar(forzar = false): Promise<Plan> {
  await esperar(2500);
  const todas = cotizaciones();
  if (!todas.length) throw new ApiError("Todavía no llegó ninguna cotización para optimizar.");
  // Igual que el backend: lo que sigue para revisar no entra al solver (409, o afuera con forzar).
  const aRevisar = todas.filter((c) => c.estado === "revisar");
  if (aRevisar.length && !forzar) {
    throw new ApiError(
      `Hay cotizaciones para revisar antes de optimizar: ${aRevisar.map((c) => c.proveedor_id).join(", ")}`,
    );
  }
  const cots = todas.filter((c) => c.estado !== "revisar");
  const plan = resolverPlan(cots);
  guardar({ ...leer(), plan });
  return plan;
}

// ───────────────────────── Negociación ensayada ─────────────────────────

export async function negociar(proveedorId: string): Promise<Negociacion> {
  await esperar(9000);
  const e = leer();
  const cot = cotizaciones().find((c) => c.proveedor_id === proveedorId);
  if (!cot) throw new ApiError(`No hay cotización de ${nombreProveedor(proveedorId)} para negociar.`);

  const enPlan = e.plan?.asignaciones.filter((a) => a.proveedor_id === proveedorId) ?? [];
  const base = enPlan.length
    ? enPlan.reduce((s, a) => s + a.subtotal, 0)
    : cot.items.reduce((s, i) => {
        const l = DEMO.pedido.lineas.find((x) => x.producto_id === i.producto_id);
        return s + (l ? l.cantidad * i.precio_unitario_sin_iva : 0);
      }, 0);

  // Mejor alternativa real para el ítem de más peso del proveedor.
  const alternativas: Alternativa[] = cot.items.flatMap((i) => {
    const otra = cotizaciones()
      .filter((c) => c.proveedor_id !== proveedorId)
      .flatMap((c) => c.items.filter((x) => x.producto_id === i.producto_id).map((x) => ({ c, x })))
      .sort((a, b) => a.x.precio_unitario_sin_iva - b.x.precio_unitario_sin_iva)[0];
    return otra && otra.x.precio_unitario_sin_iva < i.precio_unitario_sin_iva
      ? [
          {
            proveedor: nombreProveedor(otra.c.proveedor_id),
            producto: nombreProducto(i.producto_id ?? "").toLowerCase(),
            precio: otra.x.precio_unitario_sin_iva,
          },
        ]
      : [];
  });
  const alternativa = alternativas[0] ?? null;

  const estrategias = ensayarEstrategias(proveedorId, alternativa).map((s) => ({
    ...s,
    ganancia_esperada_uyu: Math.round((base * s.concesion_obtenida_pct) / 100),
  }));
  const candidatas = estrategias.some((s) => s.riesgo !== "alto")
    ? estrategias.filter((s) => s.riesgo !== "alto")
    : estrategias;
  const elegida = [...candidatas].sort((a, b) => b.ganancia_esperada_uyu - a.ganancia_esperada_uyu)[0];

  const negociacion: Negociacion = {
    id: `neg_${proveedorId}`,
    pedido_id: DEMO.pedido.id,
    proveedor_id: proveedorId,
    estrategias,
    elegida: elegida.nombre,
    mensaje_propuesto: mensajePropuesto(proveedorId, elegida, base, alternativa),
    estado: "simulada",
  };
  const actual = leer();
  guardar({ ...actual, negociaciones: { ...actual.negociaciones, [proveedorId]: negociacion } });
  return negociacion;
}

export async function aprobar(negociacionId: string, mensaje: string): Promise<Negociacion> {
  await esperar(700);
  const e = leer();
  const neg = Object.values(e.negociaciones).find((n) => n.id === negociacionId);
  if (!neg) throw new ApiError(`No existe la negociación ${negociacionId}`);
  const aprobada: Negociacion = { ...neg, mensaje_propuesto: mensaje, estado: "enviada_simulada" };
  guardar({ ...e, aprobado: true, negociaciones: { ...e.negociaciones, [neg.proveedor_id]: aprobada } });
  return aprobada;
}

// ───────────────────────── Llamadas del agente (simuladas) ─────────────────────────

const COMPRADOR = (DEMO.pedido.comprador ?? "compras").split(" (")[0];
const ACTIVAS: Llamada["estado"][] = ["iniciando", "sonando", "en_curso", "procesando"];

export async function configLlamadas(): Promise<ConfigLlamadas> {
  return { modo: "simulada", lista: true, faltan: [], proveedores_con_telefono: [] };
}

function llamadaDeCotizacion(e: EstadoMock, proveedorId: string): LlamadaMock | undefined {
  return Object.values(e.llamadas ?? {}).find(
    (l) => l.base.tipo === "cotizacion" && l.base.proveedor_id === proveedorId,
  );
}

function textoTranscripcion(l: LlamadaMock): string {
  const nombre = nombreProveedor(l.base.proveedor_id);
  return l.turnos.map((t) => `${t.rol === "abasto" ? "Abasto" : nombre}: ${t.texto}`).join("\n");
}

/** Mismos tiempos que el modo simulado del backend (llamadas.py), escalados por VITE_MOCK_SPEED. */
function armarLlamada(
  base: Omit<Llamada, "estado" | "transcripcion" | "resultado" | "duracion_segundos" | "error">,
  guion: { rol: "abasto" | "proveedor"; texto: string }[],
  resultado: Llamada["resultado"],
): LlamadaMock {
  const ms = (s: number) => s * 1000 * VELOCIDAD;
  const atiende = ms(2.5);
  let cursor = atiende;
  const turnos = guion.map((t) => {
    cursor += ms(Math.max(1.4, Math.min(t.texto.length / 45, 9)));
    return { ...t, en: cursor };
  });
  const corta = cursor + ms(1);
  return {
    base: { ...base, estado: "sonando", transcripcion: [], resultado: null, duracion_segundos: null, error: null },
    inicio: Date.now(),
    turnos,
    atiende,
    corta,
    fin: corta + ms(1.5),
    resultado,
  };
}

function vistaLlamada(l: LlamadaMock): Llamada {
  const t = Date.now() - l.inicio;
  const estado: Llamada["estado"] = t < l.atiende ? "sonando" : t < l.corta ? "en_curso" : t < l.fin ? "procesando" : "terminada";
  const terminada = estado === "terminada";
  return {
    ...l.base,
    estado,
    transcripcion: l.turnos
      .filter((x) => x.en <= t)
      .map((x) => ({ rol: x.rol, texto: x.texto, segundo: Math.round((x.en - l.atiende) / 1000 / VELOCIDAD) })),
    resultado: terminada ? l.resultado : null,
    duracion_segundos: t >= l.corta ? Math.round((l.corta - l.atiende) / 1000 / VELOCIDAD) : null,
    mensaje_id: terminada && l.base.tipo === "cotizacion" ? `msg_${l.base.proveedor_id}` : null,
  };
}

function guardarLlamada(l: LlamadaMock, cambios: Partial<EstadoMock> = {}) {
  const e = leer();
  guardar({ ...e, ...cambios, llamadas: { ...(e.llamadas ?? {}), [l.base.id]: l } });
}

function activaDe(proveedorId: string): Llamada | undefined {
  return Object.values(leer().llamadas ?? {})
    .map(vistaLlamada)
    .find((l) => l.proveedor_id === proveedorId && ACTIVAS.includes(l.estado));
}

function baseLlamada(proveedorId: string, tipo: Llamada["tipo"], negociacionId: string | null) {
  return {
    id: `lla_${proveedorId}_${Math.random().toString(16).slice(2, 8)}`,
    pedido_id: DEMO.pedido.id,
    proveedor_id: proveedorId,
    tipo,
    negociacion_id: negociacionId,
    modo: "simulada" as const,
    telefono: "+598 99• ••• 222",
    conversation_id: null,
    call_sid: null,
    mensaje_id: null,
    iniciada_en: new Date().toISOString(),
  };
}

export async function llamarParaCotizar(proveedorId: string): Promise<Llamada> {
  await esperar(500);
  const e = leer();
  const nombre = nombreProveedor(proveedorId);
  if (!e.cotizarEn) throw new ApiError("Primero hay que pedir la cotización");
  const enCurso = activaDe(proveedorId);
  if (enCurso) return enCurso;
  if (mensajes().some((m) => m.proveedor_id === proveedorId)) throw new ApiError(`${nombre} ya respondió`);
  const fijo = RESPUESTAS.find((r) => r.proveedor_id === proveedorId);
  const contenido = fijo?.canal === "pdf" ? htmlATexto(fijo.contenido) : fijo?.contenido;
  const l = armarLlamada(
    baseLlamada(proveedorId, "cotizacion", null),
    [
      {
        rol: "abasto",
        texto: `Hola, ¿hablo con ${nombre}? Te llamo de parte de ${COMPRADOR}, de ${DEMO.pedido.negocio}, por la cotización que les pedimos por WhatsApp. ¿Tenés un minuto?`,
      },
      { rol: "proveedor", texto: contenido ?? "Sí, decime. Ahora te paso los precios por WhatsApp." },
      { rol: "abasto", texto: "Perfecto, anoto todo. ¡Muchas gracias!" },
    ],
    { resumen: `${nombre} pasó la cotización por teléfono.`, acuerdo: null, precio_acordado: null, condicion: null },
  );
  guardarLlamada(l);
  return vistaLlamada(l);
}

export async function llamarParaNegociar(negociacionId: string, mensaje: string): Promise<Llamada> {
  await esperar(500);
  const e = leer();
  const neg = Object.values(e.negociaciones).find((n) => n.id === negociacionId);
  if (!neg) throw new ApiError(`No existe la negociación ${negociacionId}`);
  if (!e.plan) throw new ApiError("El plan cambió: volvé a optimizar y a negociar");
  const asignado = e.plan.asignaciones.filter((a) => a.proveedor_id === neg.proveedor_id);
  const nombre = nombreProveedor(neg.proveedor_id);
  if (!asignado.length) throw new ApiError(`${nombre} no tiene ítems en el plan`);
  const enCurso = activaDe(neg.proveedor_id);
  if (enCurso) return enCurso;

  const estrategia = neg.estrategias.find((s) => s.nombre === neg.elegida);
  // El mock cierra siempre con acuerdo: la concesión de la estrategia elegida, o un 5 %.
  const concesion = estrategia?.concesion_obtenida_pct || 5;
  const precio = Math.round(asignado[0].precio_unitario_sin_iva * (1 - concesion / 100) * 100) / 100;
  const l = armarLlamada(
    baseLlamada(neg.proveedor_id, "negociacion", neg.id),
    [
      {
        rol: "abasto",
        texto: `Hola, ¿hablo con ${nombre}? Te llamo de parte de ${COMPRADOR}, de ${DEMO.pedido.negocio}, por la cotización de ${nombreProducto(asignado[0].producto_id).toLowerCase()}. ¿Tenés un minuto?`,
      },
      ...(estrategia?.transcripcion ?? []),
      { rol: "abasto", texto: `Perfecto, quedamos así. ${COMPRADOR} te confirma por WhatsApp. ¡Gracias!` },
    ],
    {
      resumen: `${nombre} aceptó un ${formatNumero(concesion, 1)} % de descuento con la estrategia ${neg.elegida}.`,
      acuerdo: true,
      precio_acordado: precio,
      condicion: null,
    },
  );
  const aprobada: Negociacion = { ...neg, mensaje_propuesto: mensaje, estado: "aprobada", llamada_id: l.base.id };
  guardarLlamada(l, { aprobado: true, negociaciones: { ...e.negociaciones, [neg.proveedor_id]: aprobada } });
  return vistaLlamada(l);
}

export async function llamada(id: string): Promise<Llamada> {
  const l = leer().llamadas?.[id];
  if (!l) throw new ApiError(`No existe la llamada '${id}'`);
  return vistaLlamada(l);
}

export async function reset(): Promise<{ ok: boolean }> {
  guardar(INICIAL);
  return { ok: true };
}
