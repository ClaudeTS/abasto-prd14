// Único lugar que llama al backend (AGENTS.md §4). En modo mock delega en mock/servidor.ts.
import pedidoJson from "../../data/pedido_demo.json";
import { ApiError } from "./lib/errores";
import * as mock from "./mock/servidor";
import type {
  ConfigCompra,
  Conversion,
  Cotizacion,
  EstrategiaNegociacion,
  ItemCotizado,
  MensajeCrudo,
  Negociacion,
  Pedido,
  PedidoDemo,
  Plan,
  Producto,
} from "./types";

const API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "/api";

/**
 * Por defecto la UI usa el backend real. El mock es opt-in: VITE_MOCK=1 o ?modo=mock.
 * ?modo= se guarda en sessionStorage (solo esta pestaña): una sesión nueva vuelve al default, así un
 * mock olvidado de una prueba anterior no aparece en la demo.
 */
function resolverModo(): "mock" | "backend" {
  try {
    localStorage.removeItem("abasto_modo"); // versiones anteriores lo guardaban para siempre
    const param = new URLSearchParams(window.location.search).get("modo");
    if (param === "mock" || param === "backend") {
      sessionStorage.setItem("abasto_modo", param);
      return param;
    }
    const guardado = sessionStorage.getItem("abasto_modo");
    if (guardado === "mock" || guardado === "backend") return guardado;
  } catch {
    /* sin storage: usar la variable de entorno */
  }
  return import.meta.env.VITE_MOCK === "1" ? "mock" : "backend";
}

export const MODO = resolverModo();
const MOCK = MODO === "mock";

async function http<T>(metodo: "GET" | "POST", ruta: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + ruta, {
      method: metodo,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(`No se pudo conectar con el backend (${API_URL}). ¿Está corriendo uvicorn en el puerto 8000?`);
  }
  const texto = await res.text();
  let datos: unknown = null;
  if (texto) {
    try {
      datos = JSON.parse(texto);
    } catch {
      datos = texto;
    }
  }
  if (!res.ok) {
    const e = (datos ?? {}) as { error?: unknown; detail?: unknown; detalle?: unknown };
    const mensaje =
      typeof e.error === "string"
        ? e.error
        : typeof e.detail === "string"
          ? e.detail
          : res.status >= 500 && datos === null // el proxy de Vite responde 500 vacío si uvicorn no está
            ? `El backend no responde (${API_URL}). ¿Está corriendo uvicorn en el puerto 8000?`
            : `Error ${res.status} en ${metodo} ${ruta}`;
    throw new ApiError(mensaje, e.detalle ?? e.detail);
  }
  return datos as T;
}

// ─────────── Normalización (Decimal llega como string desde FastAPI) ───────────

const num = (v: unknown): number => (typeof v === "number" ? v : Number(v));
const numONull = (v: unknown): number | null => (v === null || v === undefined ? null : num(v));

function normItem(i: ItemCotizado): ItemCotizado {
  return {
    ...i,
    precio_unitario_sin_iva: num(i.precio_unitario_sin_iva),
    precio_original: num(i.precio_original),
    cantidad_minima: numONull(i.cantidad_minima),
  };
}

function normCotizacion(c: Cotizacion): Cotizacion {
  return {
    ...c,
    items: (c.items ?? []).map(normItem),
    costo_envio: num(c.costo_envio ?? 0),
    pedido_minimo_total: numONull(c.pedido_minimo_total),
    plazo_pago_dias: num(c.plazo_pago_dias ?? 0),
    lead_time_dias: num(c.lead_time_dias ?? 0),
    validez_dias: numONull(c.validez_dias),
    observaciones: c.observaciones ?? [],
    confianza: num(c.confianza ?? 1),
    campos_dudosos: c.campos_dudosos ?? [],
    estado: c.estado ?? "valida",
  };
}

function normPlan(p: Plan): Plan {
  return {
    ...p,
    asignaciones: p.asignaciones.map((a) => ({
      ...a,
      cantidad: num(a.cantidad),
      precio_unitario_sin_iva: num(a.precio_unitario_sin_iva),
      subtotal: num(a.subtotal),
    })),
    costo_total: num(p.costo_total),
    costo_baseline: num(p.costo_baseline),
    ahorro: num(p.ahorro),
    ahorro_pct: num(p.ahorro_pct),
    ahorro_comparable: numONull(p.ahorro_comparable),
    ahorro_pct_comparable: numONull(p.ahorro_pct_comparable),
    restricciones_activas: p.restricciones_activas ?? [],
    relajaciones: p.relajaciones ?? [],
  };
}

function normNegociacion(n: Negociacion): Negociacion {
  return {
    ...n,
    estrategias: n.estrategias.map(
      (s): EstrategiaNegociacion => ({
        ...s,
        concesion_obtenida_pct: num(s.concesion_obtenida_pct),
        ganancia_esperada_uyu: num(s.ganancia_esperada_uyu),
        transcripcion: s.transcripcion ?? [],
      }),
    ),
  };
}

/** Acepta el PedidoCompleto del backend (plano, con tipo_cambio_usd e iva) o {pedido, catalogo, config, conversiones}. */
function normPedidoDemo(raw: unknown): PedidoDemo {
  const r = raw as Partial<PedidoDemo> & Partial<Pedido> & Record<string, unknown>;
  const pedido = (r.pedido ?? r) as Pedido;
  // El tipo de cambio lo manda el backend: es el que usó para convertir, así que es el que se muestra.
  const config: ConfigCompra | undefined =
    (r.config as ConfigCompra | undefined) ??
    (r.tipo_cambio_usd != null
      ? { moneda_base: "UYU", tipo_cambio_usd: num(r.tipo_cambio_usd), iva: num(r.iva ?? pedidoJson.config.iva) }
      : undefined);
  return {
    pedido: { ...pedido, lineas: pedido.lineas.map((l) => ({ ...l, cantidad: num(l.cantidad) })) },
    // Catálogo y conversiones son datos seedeados: si el backend no los manda, se usan los de data/.
    catalogo: (r.catalogo as Producto[] | undefined) ?? (pedidoJson.catalogo as Producto[]),
    config: config ?? (pedidoJson.config as ConfigCompra),
    conversiones:
      (r.conversiones as Record<string, Conversion> | undefined) ??
      (pedidoJson.conversiones as Record<string, Conversion>),
  };
}

// ─────────── Endpoints (ARQUITECTURA.md §4) ───────────

export async function getPedidoDemo(): Promise<PedidoDemo> {
  if (MOCK) return mock.pedidoDemo();
  return normPedidoDemo(await http("GET", "/pedidos/demo"));
}

export async function cotizar(pedidoId: string): Promise<{ estado: string }> {
  if (MOCK) return mock.cotizar();
  return http("POST", `/pedidos/${pedidoId}/cotizar`);
}

export async function getMensajes(pedidoId: string): Promise<MensajeCrudo[]> {
  if (MOCK) return mock.mensajes();
  return http("GET", `/pedidos/${pedidoId}/mensajes`);
}

export async function getCotizaciones(pedidoId: string): Promise<Cotizacion[]> {
  if (MOCK) return mock.cotizaciones();
  const lista = await http<Cotizacion[]>("GET", `/pedidos/${pedidoId}/cotizaciones`);
  return lista.map(normCotizacion);
}

/** Quien compra resuelve un campo dudoso (ej. si los precios incluyen IVA). */
export async function confirmarCampo(cotizacionId: string, campo: string, valor: boolean): Promise<Cotizacion> {
  if (MOCK) return mock.confirmar(cotizacionId, campo, valor);
  return normCotizacion(await http("POST", `/cotizaciones/${cotizacionId}/confirmar`, { campo, valor }));
}

export async function optimizar(pedidoId: string): Promise<Plan> {
  if (MOCK) return mock.optimizar();
  return normPlan(await http("POST", `/pedidos/${pedidoId}/optimizar`));
}

export async function negociar(pedidoId: string, proveedorId: string): Promise<Negociacion> {
  if (MOCK) return mock.negociar(proveedorId);
  return normNegociacion(await http("POST", `/pedidos/${pedidoId}/negociar/${proveedorId}`));
}

export async function aprobar(negociacionId: string, mensaje: string): Promise<Negociacion> {
  if (MOCK) return mock.aprobar(negociacionId, mensaje);
  return normNegociacion(await http("POST", `/negociaciones/${negociacionId}/aprobar`, { mensaje }));
}

export async function reset(): Promise<void> {
  if (MOCK) {
    await mock.reset();
    return;
  }
  await http("POST", "/reset");
}

/** URL para mostrar el PDF / la foto / el audio de un mensaje crudo. */
export function archivoUrl(archivo: string): string {
  if (archivo.startsWith("mock:")) return mock.archivoUrl(archivo);
  if (/^(https?:|data:|blob:)/.test(archivo)) return archivo;
  const nombre = archivo.split(/[\\/]/).pop() ?? archivo;
  return `${API_URL}/archivos/${encodeURIComponent(nombre)}`;
}
