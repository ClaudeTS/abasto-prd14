// Tipos del agente de compras (docs/AGENTE.md §4). Montos sin IVA en UYU; fechas "AAAA-MM-DD".

export type ModoCompra = "automatico" | "manual";
export type Unidad = "unidad" | "l" | "kg";

/** PRD 1.4 RF-05: quién hizo el pedido. */
export type ClienteInterno = "ventas" | "personal";

export type PasoId =
  | "entender"
  | "inventario"
  | "confirmar"
  | "cotizar"
  | "insistir"
  | "revisar"
  | "optimizar"
  | "negociar"
  | "ordenes";

export type EstadoPaso = "pendiente" | "en_curso" | "esperando" | "hecho" | "omitido" | "error";

export interface PasoAgente {
  id: PasoId;
  titulo: string;
  estado: EstadoPaso;
  detalle: string | null;
  inicio: string | null;
  fin: string | null;
}

export interface LineaPropuesta {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  unidad: Unidad;
  cantidad: number; // 0 si no se dijo cuántos y no hay cuenta: tiene una duda
  necesario_para: string;
  origen: "pedido" | "reposicion";
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
  pide_iva: boolean;
  pregunta: string;
}

export interface LineaOrden {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  unidad: Unidad;
  cantidad: number;
  precio_unitario_sin_iva: number;
  subtotal: number;
  aprobacion: "automatica" | "manual" | "supera_tope";
  motivo: string;
  cotizacion_id: string | null;
  evidencia: string | null;
}

export type EstadoOrden = "esperando_aprobacion" | "enviada_simulada" | "rechazada";

export interface OrdenCompra {
  id: string;
  numero: string;
  proveedor_id: string;
  proveedor_nombre: string;
  lineas: LineaOrden[];
  envio: number;
  total_sin_iva: number;
  total_con_iva: number;
  requiere_aprobacion: boolean;
  motivos: string[];
  estado: EstadoOrden;
  aprobada_por: "agente" | "lucia" | null;
  negociacion_id: string | null;
  mensaje: string;
  enviada_en: string | null;
}

export type EstadoCorrida =
  | "en_curso"
  | "esperando_confirmacion"
  | "esperando_revision"
  | "esperando_aprobacion"
  | "completada"
  | "error"
  | "cancelada";

export interface Interpretacion {
  origen: "llm" | "fijo";
  items: {
    producto_id: string;
    descripcion: string;
    cantidad: number | null;
    necesario_para: string | null;
    evidencia: string;
  }[];
  no_entendido: string[];
  excluir: string[];
  horizonte_meses: number | null;
  evidencia_horizonte: string | null;
  dudas: string[];
}

export interface CorridaAgente {
  id: string;
  pedido_id: string;
  texto: string | null;
  /** Bloque 2 (PRD 1.4 RF-05). Las corridas viejas no lo traen: vale "personal". */
  cliente_interno?: ClienteInterno;
  horizonte_meses: number;
  opciones: {
    horizonte_meses: number | null;
    esperar_confirmacion: boolean;
    llamar_si_no_responde: boolean;
    negociar: boolean;
  };
  estado: EstadoCorrida;
  pasos: PasoAgente[];
  interpretacion: Interpretacion | null;
  propuesta: LineaPropuesta[];
  avisos: string[];
  revision: RevisionPendiente[];
  llamada_ids: string[];
  sin_respuesta: string[];
  negociacion_id: string | null;
  ordenes: OrdenCompra[];
  resumen: string | null;
  error: string | null;
  creada_en: string;
  actualizada_en: string;
}

export interface NuevaCorrida {
  texto?: string;
  cliente_interno?: ClienteInterno;
  horizonte_meses?: number | null;
  esperar_confirmacion?: boolean;
  llamar_si_no_responde?: boolean;
  negociar?: boolean;
}

export const TERMINADAS: EstadoCorrida[] = ["completada", "error", "cancelada"];
export const estaTerminada = (c: CorridaAgente | null | undefined) => !!c && TERMINADAS.includes(c.estado);
