import type { UnidadCanonica } from "../types";

/** 12340.5 → "12.340,50". Manual a propósito: Intl en "es" no agrupa números de 4 cifras. */
export function formatNumero(n: number, decimales = 0): string {
  const fijo = Math.abs(n).toFixed(decimales);
  const [entero, dec] = fijo.split(".");
  const conPuntos = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const signo = n < 0 && Number(fijo) !== 0 ? "−" : "";
  return signo + conPuntos + (dec ? "," + dec : "");
}

/** Totales: "$ 498.454". */
export function pesos(n: number): string {
  return `$ ${formatNumero(Math.round(n))}`;
}

/** Precios unitarios: con centavos solo si son chicos ("$ 178,69", "$ 27.459"). */
export function precioUnitario(n: number): string {
  const chico = Math.abs(n) < 1000 && Math.round(n * 100) % 100 !== 0;
  return `$ ${formatNumero(n, chico ? 2 : 0)}`;
}

export function porcentaje(n: number, decimales = 1): string {
  return `${formatNumero(n, decimales)} %`;
}

export function monedaOriginal(precio: number, moneda: string): string {
  const decimales = Math.round(precio * 100) % 100 !== 0 ? 2 : 0;
  return `${moneda === "USD" ? "USD" : "$"} ${formatNumero(precio, decimales)}`;
}

export function unidad(u: UnidadCanonica | string, cantidad = 2): string {
  if (u === "l") return "L";
  if (u === "kg") return "kg";
  return cantidad === 1 ? "unidad" : "unidades";
}

/** "2026-10-28" → "28/10". */
export function fechaCorta(iso: string): string {
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}`;
}

export function hora(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Días entre dos fechas YYYY-MM-DD (b − a). */
export function diasEntre(a: string, b: string): number {
  const ms = Date.parse(b.slice(0, 10)) - Date.parse(a.slice(0, 10));
  return Math.round(ms / 86_400_000);
}

export function plazoPago(dias: number): string {
  return dias === 0 ? "Contado" : `Pago a ${dias} días`;
}

/** Normaliza porcentajes que puedan venir como fracción (0.05) en vez de 0–100 (5). */
export function aPorcentaje(v: number): number {
  return Math.abs(v) < 1 && v !== 0 ? v * 100 : v;
}
