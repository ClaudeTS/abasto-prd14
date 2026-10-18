// Llamadas del dashboard (RF-09). Usa http() de src/api.ts, que adjunta el token de sesión.
import { http } from "@/api";
import type { Dashboard, FiltrosDashboard, PedidoReciente, Recomendacion, Recomendaciones } from "./types";

function isoLocal(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${dia}`;
}

export function rangoDe(dias: number, hoy = new Date()): { desde: string; hasta: string } {
  const desde = new Date(hoy);
  desde.setDate(hoy.getDate() - (dias - 1));
  return { desde: isoLocal(desde), hasta: isoLocal(hoy) };
}

export function getDashboard(f: FiltrosDashboard): Promise<Dashboard> {
  const { desde, hasta } = rangoDe(f.dias);
  const qs = new URLSearchParams({ desde, hasta });
  if (f.cliente !== "todos") qs.set("cliente_interno", f.cliente);
  return http<Dashboard>("GET", `/dashboard?${qs}`);
}

export function getRecomendaciones(): Promise<Recomendaciones> {
  return http<Recomendaciones>("GET", "/dashboard/recomendaciones");
}

export function descartarRecomendacion(id: string): Promise<Recomendacion> {
  return http<Recomendacion>("POST", `/dashboard/recomendaciones/${encodeURIComponent(id)}/descartar`);
}

type Crudo = Record<string, unknown>;
const texto = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : null);

function normalizarPedido(p: Crudo): PedidoReciente | null {
  const id = texto(p.id);
  if (!id) return null;
  const numero = texto(p.numero) ?? texto(p.codigo);
  const desc = texto(p.descripcion) ?? texto(p.titulo) ?? texto(p.resumen);
  return {
    id,
    titulo: [numero, desc].filter(Boolean).join(" · ") || id,
    cliente: texto(p.cliente_interno),
    origen: texto(p.origen),
    estado: texto(p.estado),
    actualizado: texto(p.actualizado_en) ?? texto(p.actualizado) ?? texto(p.creado_en) ?? texto(p.fecha),
  };
}

/**
 * Pedidos recientes desde GET /pedidos (lo implementa el bloque 1). Si el endpoint no existe todavía
 * (404) o falla, devuelve null y la sección no se muestra.
 */
export async function getPedidosRecientes(limite = 5): Promise<PedidoReciente[] | null> {
  try {
    const datos = await http<unknown>("GET", "/pedidos");
    const lista = Array.isArray(datos)
      ? datos
      : Array.isArray((datos as Crudo | null)?.pedidos)
        ? ((datos as Crudo).pedidos as unknown[])
        : Array.isArray((datos as Crudo | null)?.items)
          ? ((datos as Crudo).items as unknown[])
          : null;
    if (!lista) return null;
    const pedidos = lista
      .map((p) => (p && typeof p === "object" ? normalizarPedido(p as Crudo) : null))
      .filter((p): p is PedidoReciente => p !== null);
    pedidos.sort((a, b) => (b.actualizado ?? "").localeCompare(a.actualizado ?? ""));
    return pedidos.slice(0, limite);
  } catch {
    return null;
  }
}
