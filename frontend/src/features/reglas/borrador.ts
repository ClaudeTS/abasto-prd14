// Borrador del panel de reglas: los números se editan como texto (coma decimal) y se convierten al
// guardar. Solo viajan los campos que cambiaron respecto de lo guardado.
import type { ClienteInterno } from "@/lib/auth";
import type { Moneda, PropuestaReglas, Reglas, Sustituto } from "./types";

export interface ProveedorBorrador {
  proveedor_id: string;
  minimo_compra: string;
  unidad_venta: string;
  factor_conversion: string;
}

export interface Borrador {
  compra_automatica: boolean;
  stock_minimo: string;
  stock_base: string;
  zafra_inicio: string; // "dd/mm"
  zafra_fin: string;
  zafra_cantidad: string;
  tope_precio_unitario: string;
  moneda_tope: Moneda;
  tope_automatico_uyu: string;
  plazo_entrega_max_dias: string;
  plazo_pago_requerido_dias: string;
  proveedores: ProveedorBorrador[]; // en orden de prioridad
  sustitutos: Sustituto[];
  descuento_objetivo_pct: string;
  concesion_maxima_pct: string;
  cliente_interno: ClienteInterno;
}

export const aTexto = (n: number | null | undefined): string =>
  n === null || n === undefined ? "" : String(n).replace(".", ",");

const ddmm = (mmdd: string) => `${mmdd.slice(3)}/${mmdd.slice(0, 2)}`;

export function desdeReglas(r: Reglas): Borrador {
  return {
    compra_automatica: r.compra_automatica,
    stock_minimo: aTexto(r.stock_minimo),
    stock_base: aTexto(r.stock_base),
    zafra_inicio: r.zafra ? ddmm(r.zafra.inicio) : "",
    zafra_fin: r.zafra ? ddmm(r.zafra.fin) : "",
    zafra_cantidad: r.zafra ? aTexto(r.zafra.cantidad) : "",
    tope_precio_unitario: aTexto(r.tope_precio_unitario),
    moneda_tope: r.moneda_tope,
    tope_automatico_uyu: aTexto(r.tope_automatico_uyu),
    plazo_entrega_max_dias: aTexto(r.plazo_entrega_max_dias),
    plazo_pago_requerido_dias: aTexto(r.plazo_pago_requerido_dias),
    proveedores: [...r.proveedores]
      .sort((a, b) => a.prioridad - b.prioridad)
      .map((p) => ({
        proveedor_id: p.proveedor_id,
        minimo_compra: aTexto(p.minimo_compra),
        unidad_venta: p.unidad_venta ?? "",
        factor_conversion: aTexto(p.factor_conversion),
      })),
    sustitutos: r.sustitutos,
    descuento_objetivo_pct: aTexto(r.descuento_objetivo_pct),
    concesion_maxima_pct: aTexto(r.concesion_maxima_pct),
    cliente_interno: r.cliente_interno,
  };
}

/** "1.500" (miles) · "178,5" · "178.5" → número. "" → null. */
export function aNumero(texto: string): number | null | "invalido" {
  let t = texto.trim().replace(/\s/g, "");
  if (!t) return null;
  if (t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  const n = Number(t);
  return Number.isFinite(n) ? n : "invalido";
}

/** "1/5" o "01/05" → "05-01". */
function aMesDia(texto: string): string | null {
  const m = texto.trim().match(/^(\d{1,2})\/(\d{1,2})$/);
  if (!m) return null;
  return `${m[2]!.padStart(2, "0")}-${m[1]!.padStart(2, "0")}`;
}

const estable = (v: unknown): string =>
  JSON.stringify(v, (_, x) =>
    x && typeof x === "object" && !Array.isArray(x)
      ? Object.fromEntries(Object.entries(x).sort(([a], [b]) => a.localeCompare(b)))
      : x,
  );

/** Reglas candidatas + errores locales (formato) + solo los campos que cambian. */
export function aPropuesta(b: Borrador, original: Reglas): { propuesta: PropuestaReglas; errores: Record<string, string> } {
  const errores: Record<string, string> = {};
  const num = (campo: string, texto: string, entero = false): number | null => {
    const n = aNumero(texto);
    if (n === "invalido" || (entero && n !== null && !Number.isInteger(n))) {
      errores[campo] = entero ? "Tiene que ser un número entero." : "Tiene que ser un número.";
      return (original as unknown as Record<string, number | null>)[campo] ?? null;
    }
    return n;
  };
  const candidato: Reglas = {
    ...original,
    compra_automatica: b.compra_automatica,
    stock_minimo: num("stock_minimo", b.stock_minimo) ?? 0,
    stock_base: num("stock_base", b.stock_base),
    tope_precio_unitario: num("tope_precio_unitario", b.tope_precio_unitario),
    moneda_tope: b.moneda_tope,
    tope_automatico_uyu: num("tope_automatico_uyu", b.tope_automatico_uyu),
    plazo_entrega_max_dias: num("plazo_entrega_max_dias", b.plazo_entrega_max_dias, true),
    plazo_pago_requerido_dias: num("plazo_pago_requerido_dias", b.plazo_pago_requerido_dias, true),
    descuento_objetivo_pct: num("descuento_objetivo_pct", b.descuento_objetivo_pct),
    concesion_maxima_pct: num("concesion_maxima_pct", b.concesion_maxima_pct),
    sustitutos: b.sustitutos,
    cliente_interno: b.cliente_interno,
  };
  if (b.stock_minimo.trim() === "") errores.stock_minimo = "El stock mínimo no puede quedar vacío.";

  const algoDeZafra = [b.zafra_inicio, b.zafra_fin, b.zafra_cantidad].some((t) => t.trim());
  if (!algoDeZafra) candidato.zafra = null;
  else {
    const inicio = aMesDia(b.zafra_inicio);
    const fin = aMesDia(b.zafra_fin);
    const cantidad = aNumero(b.zafra_cantidad);
    if (!inicio || !fin) errores.zafra = "El período va como día/mes, ej. 01/05 – 31/08.";
    else if (cantidad === null || cantidad === "invalido") errores.zafra = "Falta la cantidad de zafra.";
    else candidato.zafra = { inicio, fin, cantidad };
  }

  candidato.proveedores = b.proveedores.map((p, i) => {
    const minimo = aNumero(p.minimo_compra);
    const factor = aNumero(p.factor_conversion);
    if (minimo === "invalido" || factor === "invalido") errores.proveedores = "Revisá los números de la tabla de proveedores.";
    return {
      proveedor_id: p.proveedor_id,
      prioridad: i + 1,
      minimo_compra: minimo === "invalido" ? null : minimo,
      unidad_venta: p.unidad_venta.trim() || null,
      factor_conversion: factor === "invalido" || factor === null ? 1 : factor,
    };
  });

  const propuesta: PropuestaReglas = {};
  for (const clave of Object.keys(candidato) as (keyof Reglas)[]) {
    if (errores[clave]) continue;
    if (estable(candidato[clave]) !== estable(original[clave])) {
      (propuesta as Record<string, unknown>)[clave] = candidato[clave];
    }
  }
  return { propuesta, errores };
}
