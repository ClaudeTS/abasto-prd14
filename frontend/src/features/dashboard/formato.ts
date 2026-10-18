import { formatNumero } from "@/lib/format";
import type { CanalContacto, Kpi, UnidadKpi } from "./types";

/** Minutos legibles: "7,8 min", "1 h 54 min", "1 d 2 h". */
export function duracion(minutos: number): string {
  if (minutos < 60) return `${formatNumero(minutos, minutos < 10 ? 1 : 0)} min`;
  const total = Math.round(minutos);
  if (total < 24 * 60) {
    const h = Math.floor(total / 60);
    const m = total % 60;
    return m ? `${h} h ${m} min` : `${h} h`;
  }
  const d = Math.floor(total / (24 * 60));
  const h = Math.round((total % (24 * 60)) / 60);
  return h ? `${d} d ${h} h` : `${d} d`;
}

export function valorKpi(valor: number, unidad: UnidadKpi, id?: string): string {
  if (unidad === "min") return duracion(valor);
  if (unidad === "h") return `${formatNumero(valor, 1)} h`;
  if (unidad === "pp") return `${id === "precision_gemelo" ? "±" : ""}${formatNumero(valor, 1)} pp`;
  return `${formatNumero(valor, valor >= 99.95 || valor === 0 ? 0 : 1)} %`;
}

/** Diferencia contra el período anterior: texto y si es una mejora. */
export function variacion(k: Kpi): { texto: string; mejora: boolean | null } | null {
  if (k.valor === null || k.valor_anterior === null) return null;
  const diff = k.valor - k.valor_anterior;
  if (Math.abs(diff) < 0.05) return { texto: "Igual que el período anterior", mejora: null };
  const signo = diff > 0 ? "+" : "−";
  const abs = Math.abs(diff);
  const cuanto =
    k.unidad === "%" || k.unidad === "pp"
      ? `${formatNumero(abs, 1)} pp`
      : k.unidad === "h"
        ? `${formatNumero(abs, 1)} h`
        : duracion(abs);
  const mejora = k.mejor_si === null ? null : k.mejor_si === "mayor" ? diff > 0 : diff < 0;
  return { texto: `${signo}${cuanto} contra el período anterior`, mejora };
}

export const NOMBRE_CANAL: Record<CanalContacto, string> = {
  llamada: "Llamada",
  whatsapp: "WhatsApp",
  email: "Email",
};

export function saludo(hora = new Date().getHours()): string {
  if (hora >= 5 && hora < 13) return "Buen día";
  if (hora >= 13 && hora < 20) return "Buenas tardes";
  return "Buenas noches";
}

/** "2026-10-17T20:24:00" → "17/10 20:24". */
export function fechaHora(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
