import type { Moneda } from "../types";

// Lo que devolvería el prompt `extractor` (docs/PROMPTS.md §1) para cada mensaje de
// data/respuestas_fijas.json, ANTES de las reglas post-LLM (moneda, IVA, unidades).
// Cada evidencia es un fragmento literal del mensaje: la UI lo resalta en el original.

export interface ItemExtraido {
  producto_id: string;
  descripcion_original: string;
  precio: number;
  moneda: Moneda;
  unidad_original: string;
  incluye_iva_original: boolean;
  cantidad_minima: number | null;
  evidencia: string;
}

export interface Extraccion {
  items: ItemExtraido[];
  costo_envio: number;
  pedido_minimo_total: number | null;
  plazo_pago_dias: number;
  lead_time_dias: number;
  validez_dias: number | null;
  observaciones: string[];
  confianza: number;
  campos_dudosos: string[];
  segundos_lectura: number; // cuánto "tarda" Abasto en leerlo en el feed
}

export const EXTRACCIONES: Record<string, Extraccion> = {
  distribuidora_oriental: {
    items: [
      {
        producto_id: "resma_a4",
        descripcion_original: "Resma A4 75g",
        precio: 235,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: "Resma A4 75g $235",
      },
      {
        producto_id: "toner",
        descripcion_original: "Tóner HP 85A original",
        precio: 4600,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: "Tóner HP 85A original $4.600",
      },
      {
        producto_id: "desinfectante",
        descripcion_original: "Desinfectante de pisos bidón 5L",
        precio: 790,
        moneda: "UYU",
        unidad_original: "bidón de 5 L",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: "Desinfectante de pisos bidón 5L $790",
      },
      {
        producto_id: "silla",
        descripcion_original: "Silla ergonómica",
        precio: 12400,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: "Silla ergonómica $12.400",
      },
    ],
    costo_envio: 0,
    pedido_minimo_total: 8000,
    plazo_pago_dias: 30,
    lead_time_dias: 2,
    validez_dias: null,
    observaciones: ["Precios + IVA", "No maneja notebooks", "Mínimo de compra $ 8.000"],
    confianza: 0.93,
    campos_dudosos: [],
    segundos_lectura: 2.5,
  },

  compuservice: {
    items: [
      {
        producto_id: "notebook",
        descripcion_original: "Notebook 15 i5 16gb 512",
        precio: 33500,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: 5,
        evidencia: "Notebook 15 i5 16gb 512 33500",
      },
      {
        producto_id: "toner",
        descripcion_original: "Toner 85a",
        precio: 3900,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: "Toner 85a 3900",
      },
    ],
    costo_envio: 0,
    pedido_minimo_total: null,
    plazo_pago_dias: 0,
    lead_time_dias: 3,
    validez_dias: null,
    observaciones: ["Mínimo 5 notebooks", "No aclara si los precios incluyen IVA"],
    confianza: 0.55,
    campos_dudosos: ["iva"],
    segundos_lectura: 2.5,
  },

  ofisillas: {
    items: [
      {
        producto_id: "silla",
        descripcion_original: "Silla ergonómica mod. Prime, respaldo mesh",
        precio: 10900,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia:
          "silla ergonómica mod. Prime, respaldo mesh, apoyabrazos regulables, $10.900 + IVA c/u",
      },
    ],
    costo_envio: 1200,
    pedido_minimo_total: null,
    plazo_pago_dias: 30,
    lead_time_dias: 7,
    validez_dias: null,
    observaciones: ["Envío $ 1.200", "Entrega 7 días hábiles", "Sin mínimo"],
    confianza: 0.95,
    campos_dudosos: [],
    segundos_lectura: 2.5,
  },

  tecnoimport: {
    items: [
      {
        producto_id: "notebook",
        descripcion_original: 'Notebook 15.6" Core i5 / 16 GB RAM / 512 GB SSD / Win 11 Pro',
        precio: 780,
        moneda: "USD",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: 'Notebook 15.6" Core i5 / 16 GB RAM / 512 GB SSD / Win 11 Pro 10 780,00',
      },
      {
        producto_id: "toner",
        descripcion_original: "Tóner HP 85A original (CE285A)",
        precio: 95,
        moneda: "USD",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: null,
        evidencia: "Tóner HP 85A original (CE285A) 8 95,00",
      },
    ],
    costo_envio: 0,
    pedido_minimo_total: null,
    plazo_pago_dias: 30,
    lead_time_dias: 5,
    validez_dias: 5,
    observaciones: [
      "Precios en USD más IVA, pagaderos al tipo de cambio BCU del día de facturación",
      "Validez 5 días: sujeto a variación del tipo de cambio",
    ],
    confianza: 0.9,
    campos_dudosos: [],
    segundos_lectura: 4,
  },

  muebleria_rivera: {
    items: [
      {
        producto_id: "silla",
        descripcion_original: "Silla ergo mod. 2",
        precio: 9800,
        moneda: "UYU",
        unidad_original: "unidad",
        incluye_iva_original: false,
        cantidad_minima: 20,
        evidencia: "Silla ergo mod. 2 ... 9.800 x unidad s/iva",
      },
    ],
    costo_envio: 0,
    pedido_minimo_total: null,
    plazo_pago_dias: 0,
    lead_time_dias: 10,
    validez_dias: null,
    observaciones: ["Mínimo 20 unidades (fabrica por lote)", "50 % anticipo, resto contra entrega"],
    confianza: 0.8,
    campos_dudosos: [],
    segundos_lectura: 5,
  },

  papelera_del_sur: {
    items: [
      {
        producto_id: "resma_a4",
        descripcion_original: "Caja de cinco resmas",
        precio: 1090,
        moneda: "UYU",
        unidad_original: "caja de 5 resmas",
        incluye_iva_original: true,
        cantidad_minima: null,
        evidencia: "la caja de cinco resmas te la dejo a mil noventa",
      },
      {
        producto_id: "desinfectante",
        descripcion_original: "Desinfectante de pisos, bidón de cinco litros",
        precio: 690,
        moneda: "UYU",
        unidad_original: "bidón de 5 L",
        incluye_iva_original: true,
        cantidad_minima: null,
        evidencia: "el bidón de cinco litros, seiscientos noventa. Todo con el IVA adentro ya",
      },
    ],
    costo_envio: 0,
    pedido_minimo_total: null,
    plazo_pago_dias: 0,
    lead_time_dias: 1,
    validez_dias: null,
    observaciones: [
      "Envío sin cargo si el pedido supera $ 5.000",
      "Avisa que el papel aumenta el mes que viene por el dólar",
      "No maneja tóner",
    ],
    confianza: 0.82,
    campos_dudosos: [],
    segundos_lectura: 4,
  },
};
