// Llamadas del Bloque 1 — Pedidos. Usa http() de src/api.ts (adjunta el token de sesión).
import { CLAVE_TOKEN, http } from "@/api";
import { ApiError } from "@/lib/errores";
import type { DetallePedido, FiltrosPedidos, ListadoPedidos, ParteInforme } from "./types";

/** Mismo backend que src/api.ts (no exporta la URL): para el PDF y los archivos adjuntos. */
export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "/api";

export function urlArchivo(ruta: string): string {
  return /^https?:\/\//.test(ruta) ? ruta : API_URL + ruta;
}

export function listarPedidos(filtros: FiltrosPedidos): Promise<ListadoPedidos> {
  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== null && String(valor).trim() !== "") params.set(clave, String(valor).trim());
  }
  const qs = params.toString();
  return http<ListadoPedidos>("GET", `/pedidos${qs ? `?${qs}` : ""}`);
}

export function detallePedido(id: string): Promise<DetallePedido> {
  return http<DetallePedido>("GET", `/pedidos/${encodeURIComponent(id)}/detalle`);
}

export function recibirPedido(id: string): Promise<DetallePedido> {
  return http<DetallePedido>("POST", `/pedidos/${encodeURIComponent(id)}/recibir`);
}

export function cerrarPedido(id: string): Promise<DetallePedido> {
  return http<DetallePedido>("POST", `/pedidos/${encodeURIComponent(id)}/cerrar`);
}

/** Órdenes del agente (docs/AGENTE.md). Devuelven la corrida; después se recarga el detalle. */
export function aprobarOrden(corridaId: string, ordenId: string): Promise<unknown> {
  return http("POST", `/agente/${encodeURIComponent(corridaId)}/ordenes/${encodeURIComponent(ordenId)}/aprobar`);
}

export function rechazarOrden(corridaId: string, ordenId: string): Promise<unknown> {
  return http("POST", `/agente/${encodeURIComponent(corridaId)}/ordenes/${encodeURIComponent(ordenId)}/rechazar`);
}

/** RF-18: baja el informe en PDF con lo elegido (datos del pedido, diálogo del agente o ambos). */
export async function descargarInforme(id: string, numero: string, incluir: ParteInforme[]): Promise<void> {
  const ruta = `/pedidos/${encodeURIComponent(id)}/informe.pdf?incluir=${incluir.join(",")}`;
  let res: Response;
  try {
    let token: string | null = null;
    try {
      token = localStorage.getItem(CLAVE_TOKEN);
    } catch {
      /* sin storage */
    }
    res = await fetch(API_URL + ruta, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  } catch {
    throw new ApiError(`No se pudo conectar con el backend (${API_URL}).`);
  }
  if (!res.ok) {
    let mensaje = `Error ${res.status} al generar el PDF`;
    try {
      const datos = (await res.json()) as { error?: string };
      if (datos.error) mensaje = datos.error;
    } catch {
      /* no era JSON */
    }
    throw new ApiError(mensaje);
  }
  const blob = await res.blob();
  const sufijo = incluir.length === 2 ? "completo" : incluir[0];
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${numero}-${sufijo}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
