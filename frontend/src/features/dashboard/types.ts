// Tipos del dashboard (RF-09). Espejo de backend/app/kpi.py y backend/app/recomendaciones.py.

export type ClienteInterno = "ventas" | "personal";
export type CanalContacto = "llamada" | "whatsapp" | "email";
export type UnidadKpi = "%" | "h" | "min" | "pp";

export interface Meta {
  texto: string;
  valor: number | null;
  cumple: boolean | null;
}

export interface Fuentes {
  reales: number;
  ejemplo: number;
}

export interface TiempoCanal {
  canal: CanalContacto;
  minutos: number | null;
  muestras: number;
  ejemplo: boolean;
}

export interface Kpi {
  id: string;
  nombre: string;
  /** null: no hay observaciones en el período (no se inventa un valor). */
  valor: number | null;
  unidad: UnidadKpi;
  detalle: string | null;
  como_se_calcula: string;
  /** null: meta a definir con la línea base del primer mes. */
  meta: Meta | null;
  /** Usa al menos un dato del histórico de ejemplo. */
  ejemplo: boolean;
  fuentes: Fuentes;
  valor_anterior: number | null;
  mejor_si: "mayor" | "menor" | null;
  por_canal: TiempoCanal[] | null;
}

export interface Pendiente {
  id: string;
  tipo: "orden" | "negociacion";
  titulo: string;
  detalle: string;
  pedido_id: string;
  proveedor_id: string;
  monto_sin_iva: number | null;
  enlace: string;
}

export interface Dashboard {
  desde: string;
  hasta: string;
  cliente_interno: ClienteInterno | null;
  generado_en: string;
  kpis: Kpi[];
  tiempo_por_canal: TiempoCanal[];
  pendientes: Pendiente[];
  ejemplo: boolean;
  nota_ejemplo: string;
}

export type TipoRecomendacion = "alza_precio" | "oferta_otro_proveedor" | "canal_mas_rapido" | "pendiente_aprobacion";

export interface DatoRespaldo {
  etiqueta: string;
  valor: string;
  ejemplo: boolean;
}

export interface Recomendacion {
  id: string;
  tipo: TipoRecomendacion;
  titulo: string;
  texto: string;
  texto_origen: "llm" | "plantilla";
  datos: DatoRespaldo[];
  enlace: { ruta: string; etiqueta: string };
  producto_id: string | null;
  proveedor_id: string | null;
  ejemplo: boolean;
  estado: "nueva" | "descartada";
  fecha: string;
  prioridad: number;
}

export interface Recomendaciones {
  recomendaciones: Recomendacion[];
  descartadas: number;
  umbral_alza_pct: number;
  redaccion: "llm" | "plantilla";
  ejemplo: boolean;
}

export interface FiltrosDashboard {
  /** Días hacia atrás desde hoy, inclusive. */
  dias: number;
  cliente: ClienteInterno | "todos";
}

/** Fila de "Pedidos recientes", normalizada desde GET /pedidos (bloque 1), sea cual sea su forma. */
export interface PedidoReciente {
  id: string;
  titulo: string;
  cliente: string | null;
  origen: string | null;
  estado: string | null;
  actualizado: string | null;
}
