// Llamadas del agente de compras (docs/AGENTE.md §3). Usa `http` de src/api.ts (adjunta la sesión).
import { http } from "@/api";
import { ApiError } from "@/lib/errores";
import type { Negociacion } from "@/types";
import type { CorridaAgente, LineaOrden, NuevaCorrida, OrdenCompra } from "./types";

const num = (v: unknown): number => (typeof v === "number" ? v : Number(v));
const numONull = (v: unknown): number | null => (v === null || v === undefined ? null : num(v));

/** Por si algún monto llega como string (Decimal de FastAPI). */
function normCorrida(c: CorridaAgente): CorridaAgente {
  return {
    ...c,
    cliente_interno: c.cliente_interno ?? "personal",
    avisos: c.avisos ?? [],
    revision: c.revision ?? [],
    llamada_ids: c.llamada_ids ?? [],
    sin_respuesta: c.sin_respuesta ?? [],
    propuesta: (c.propuesta ?? []).map((l) => ({
      ...l,
      cantidad: num(l.cantidad),
      stock_actual: num(l.stock_actual),
      tope_automatico_uyu: numONull(l.tope_automatico_uyu),
      dudas: l.dudas ?? [],
    })),
    ordenes: (c.ordenes ?? []).map(
      (o): OrdenCompra => ({
        ...o,
        envio: num(o.envio),
        total_sin_iva: num(o.total_sin_iva),
        total_con_iva: num(o.total_con_iva),
        motivos: o.motivos ?? [],
        lineas: o.lineas.map(
          (l): LineaOrden => ({
            ...l,
            cantidad: num(l.cantidad),
            precio_unitario_sin_iva: num(l.precio_unitario_sin_iva),
            subtotal: num(l.subtotal),
          }),
        ),
      }),
    ),
  };
}

export async function ejemplo(): Promise<string> {
  return (await http<{ texto: string }>("GET", "/agente/ejemplo")).texto;
}

/** La última corrida, o null si nunca hubo (404). */
export async function actual(): Promise<CorridaAgente | null> {
  try {
    return normCorrida(await http<CorridaAgente>("GET", "/agente/actual"));
  } catch (e) {
    if (e instanceof ApiError && /todav[ií]a no hay/i.test(e.message)) return null;
    throw e;
  }
}

export async function obtener(id: string): Promise<CorridaAgente> {
  return normCorrida(await http("GET", `/agente/${id}`));
}

/** 409 con `detalle.corrida_id` si hay otra en curso, o `detalle.estado_pedido` si el pedido ya se cotizó. */
export async function iniciar(nueva: NuevaCorrida): Promise<CorridaAgente> {
  return normCorrida(await http("POST", "/agente", nueva));
}

/** Sin `lineas`: la propuesta tal cual. Con `lineas`: todas las que quedan (la que falta se saca). */
export async function confirmar(
  id: string,
  lineas?: { producto_id: string; cantidad: number }[],
): Promise<CorridaAgente> {
  return normCorrida(await http("POST", `/agente/${id}/confirmar`, lineas ? { lineas } : undefined));
}

export async function aprobarOrden(id: string, ordenId: string): Promise<CorridaAgente> {
  return normCorrida(await http("POST", `/agente/${id}/ordenes/${ordenId}/aprobar`));
}

export async function rechazarOrden(id: string, ordenId: string): Promise<CorridaAgente> {
  return normCorrida(await http("POST", `/agente/${id}/ordenes/${ordenId}/rechazar`));
}

export async function cancelar(id: string): Promise<CorridaAgente> {
  return normCorrida(await http("POST", `/agente/${id}/cancelar`));
}

export async function getNegociacion(id: string): Promise<Negociacion> {
  const n = await http<Negociacion>("GET", `/negociaciones/${id}`);
  return {
    ...n,
    estrategias: n.estrategias.map((s) => ({
      ...s,
      concesion_obtenida_pct: num(s.concesion_obtenida_pct),
      ganancia_esperada_uyu: num(s.ganancia_esperada_uyu),
      transcripcion: s.transcripcion ?? [],
    })),
  };
}

/** Detalle de un 409 de POST /agente. */
export function detalle409(e: unknown): { corrida_id?: string; estado_pedido?: string | null } | null {
  if (!(e instanceof ApiError) || !e.detalle || typeof e.detalle !== "object") return null;
  return e.detalle as { corrida_id?: string; estado_pedido?: string | null };
}
