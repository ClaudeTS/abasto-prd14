// Espejo de los modelos Pydantic de docs/ARQUITECTURA.md §3.
// Los Decimal llegan como string desde FastAPI: api.ts los normaliza a number antes de llegar acá.

export type Moneda = "UYU" | "USD";
export type UnidadCanonica = "unidad" | "l" | "kg";
/** "llamada": la transcripción de una llamada del agente viene en contenido_texto ("Abasto: …" / "<Proveedor>: …"). */
export type Canal = "whatsapp_texto" | "whatsapp_audio" | "pdf" | "foto" | "llamada";

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
  cotizacion_id?: string | null; // al llegar a "extraido"
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
  /** Lo decide el backend: "revisar" = borde amarillo y no entra al plan hasta confirmarla. */
  estado: "valida" | "revisar" | "confirmada";
}

export interface Asignacion {
  producto_id: string;
  proveedor_id: string;
  cantidad: number;
  precio_unitario_sin_iva: number;
  subtotal: number;
}

/** Caso donde el solver no eligió al más barato, con el motivo que calculó el backend. */
export interface NoMasBarato {
  producto_id: string;
  mas_barato_id: string;
  precio_mas_barato: number;
  elegido_id: string;
  precio_elegido: number;
  motivo: string;
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
  /** Del backend (el solver decide). El modo mock no los manda: la UI calcula un respaldo. */
  no_mas_barato?: NoMasBarato[];
  cotizaciones_excluidas?: string[];
  brecha_oportunidad?: number | null;
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
  /** Si se aprobó para negociar por teléfono ("Aprobar y llamar"). */
  llamada_id?: string | null;
}

// ─────────── Llamadas telefónicas del agente (ElevenLabs + Twilio, o simuladas) ───────────

export interface ConfigLlamadas {
  modo: "real" | "simulada";
  /** En modo real: si está todo configurado para llamar. */
  lista: boolean;
  /** Variables de entorno que faltan (modo real). */
  faltan: string[];
  proveedores_con_telefono: string[];
}

export interface TurnoLlamada {
  rol: "abasto" | "proveedor";
  texto: string;
  segundo: number | null;
}

export interface ResultadoLlamada {
  resumen: string | null;
  acuerdo: boolean | null;
  /** Por unidad canónica, sin IVA. */
  precio_acordado: number | null;
  condicion: string | null;
}

export type EstadoLlamada = "iniciando" | "sonando" | "en_curso" | "procesando" | "terminada" | "fallida";

export interface Llamada {
  id: string;
  pedido_id: string;
  proveedor_id: string;
  tipo: "cotizacion" | "negociacion";
  negociacion_id: string | null;
  modo: "real" | "simulada";
  estado: EstadoLlamada;
  /** Ya enmascarado por el backend: "+598 99• ••• 222". */
  telefono: string | null;
  conversation_id: string | null;
  call_sid: string | null;
  /** Crece durante la llamada. */
  transcripcion: TurnoLlamada[];
  /** Al terminar. */
  resultado: ResultadoLlamada | null;
  duracion_segundos: number | null;
  /** Tipo cotización: el mensaje que entró al feed. */
  mensaje_id: string | null;
  error: string | null;
  iniciada_en: string;
  /** RF-06 (opcionales): intento 1 o 2, si atendió, hasta cuándo se guarda el audio y la secuencia de contacto. */
  intento?: number | null;
  atendida?: boolean | null;
  audio_disponible_hasta?: string | null;
  secuencia?: SecuenciaContacto | null;
}

export type EstadoPasoContacto =
  | "pendiente"
  | "programado"
  | "en_curso"
  | "atendida"
  | "no_atendida"
  | "enviado"
  | "omitido"
  | "cancelado"
  | "error";

export interface PasoContacto {
  paso: "llamada" | "reintento" | "whatsapp" | "email";
  estado: EstadoPasoContacto;
  programado_para: string | null;
  hecho_en: string | null;
  detalle: string | null;
}

/** Si no atiende: reintento a los 30 min, después WhatsApp con el motivo (o email si no tiene WhatsApp). */
export interface SecuenciaContacto {
  id: string;
  estado: "en_curso" | "reintento_programado" | "atendida" | "respondio" | "aviso_enviado" | "interrumpida";
  intento: number;
  reintento_minutos: number;
  reintento_en: string | null;
  tiene_whatsapp: boolean;
  pasos: PasoContacto[];
}
