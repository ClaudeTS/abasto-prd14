// Espejo de los modelos Pydantic de docs/ARQUITECTURA.md §3.
// Los Decimal llegan como string desde FastAPI: api.ts los normaliza a number antes de llegar acá.

export type Moneda = "UYU" | "USD";
export type UnidadCanonica = "unidad" | "l" | "kg";
export type Canal = "whatsapp_texto" | "whatsapp_audio" | "pdf" | "foto";

export interface Producto {
  id: string;
  nombre: string;
  unidad_canonica: UnidadCanonica;
}

export interface LineaPedido {
  producto_id: string;
  cantidad: number;
  necesario_para: string; // YYYY-MM-DD
}

export type EstadoPedido =
  | "nuevo"
  | "cotizando"
  | "cotizado"
  | "optimizado"
  | "negociando"
  | "aprobado";

export interface Pedido {
  id: string;
  negocio: string;
  lineas: LineaPedido[];
  proveedor_habitual_id: string;
  estado: EstadoPedido;
  comprador?: string;
  descripcion?: string;
  fecha?: string;
}

export interface ConfigCompra {
  moneda_base: string;
  tipo_cambio_usd: number;
  iva: number;
}

export interface Conversion {
  factor: number;
  a: UnidadCanonica;
}

/** Respuesta de GET /pedidos/demo: el pedido con su catálogo, configuración y tabla de conversiones. */
export interface PedidoDemo {
  pedido: Pedido;
  catalogo: Producto[];
  config: ConfigCompra;
  conversiones: Record<string, Conversion>;
}

export interface Proveedor {
  id: string;
  nombre: string;
  rubro: string;
  canal_preferido: Canal;
  confiabilidad: number; // 0–1
}

export type EstadoMensaje = "pendiente" | "leyendo" | "extraido" | "error";

export interface MensajeCrudo {
  id: string;
  pedido_id: string;
  proveedor_id: string;
  canal: Canal;
  contenido_texto: string | null;
  archivo: string | null;
  recibido_en: string; // ISO
  estado: EstadoMensaje;
  error?: string | null;
}

export interface ItemCotizado {
  producto_id: string | null; // null si el extractor no pudo mapearlo al catálogo
  descripcion_original?: string;
  precio_unitario_sin_iva: number; // UYU por unidad canónica
  precio_original: number;
  moneda_original: Moneda;
  incluye_iva_original: boolean;
  unidad_original: string;
  conversion_aplicada: string | null;
  cantidad_minima: number | null;
  evidencia: string;
}

export interface Cotizacion {
  id: string;
  mensaje_id: string;
  proveedor_id: string;
  items: ItemCotizado[];
  costo_envio: number;
  pedido_minimo_total: number | null;
  plazo_pago_dias: number;
  lead_time_dias: number;
  validez_dias: number | null;
  observaciones: string[];
  confianza: number; // 0–1
  campos_dudosos: string[];
}

export interface Asignacion {
  producto_id: string;
  proveedor_id: string;
  cantidad: number;
  precio_unitario_sin_iva: number;
  subtotal: number;
}

export interface Plan {
  pedido_id: string;
  asignaciones: Asignacion[];
  costo_total: number;
  costo_baseline: number;
  ahorro: number;
  ahorro_pct: number; // en %, 0–100
  ahorro_comparable?: number | null; // ahorro sobre lo que el habitual sí vende
  ahorro_pct_comparable?: number | null; // en %, 0–100
  proveedores_usados: string[];
  restricciones_activas: string[];
  relajaciones: string[];
  explicacion: string;
  oportunidad_negociacion: string | null;
}

export type NombreEstrategia = "competencia" | "volumen" | "plazo";

export interface TurnoNegociacion {
  rol: "abasto" | "proveedor";
  texto: string;
}

export interface EstrategiaNegociacion {
  nombre: NombreEstrategia;
  descripcion: string;
  transcripcion: TurnoNegociacion[];
  concesion_obtenida_pct: number; // en %, 0–100
  ganancia_esperada_uyu: number;
  riesgo: "bajo" | "medio" | "alto";
}

export interface Negociacion {
  id: string;
  pedido_id: string;
  proveedor_id: string;
  estrategias: EstrategiaNegociacion[];
  elegida: NombreEstrategia;
  mensaje_propuesto: string;
  estado: "simulada" | "aprobada" | "enviada_simulada";
}
