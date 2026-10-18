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
}

// ─────────── Agente de compras e inventario (docs/AGENTE.md §4) ───────────

export type ModoCompra = "automatico" | "manual";

export interface ItemInventario {
  producto_id: string;
  nombre: string;
  nombre_corto: string; // para frases: "resmas", "tóner"
  unidad: UnidadCanonica;
  tipo: "consumible" | "equipamiento";
  stock_actual: number;
  stock_minimo: number;
  en_camino: number; // en órdenes que el agente ya mandó
  multiplo_compra: number;
  modo: ModoCompra;
  tope_automatico_uyu: number | null; // sin IVA; null = sin tope
  proveedores: { id: string; nombre: string }[];
  historial: { mes: string; cantidad: number }[]; // 24 meses
  pronostico: {
    nivel: number;
    consumo_diario: number;
    meses: { mes: string; indice: number; cantidad: number }[];
    total: number;
    evidencia: string;
  } | null; // null: equipamiento
  reposicion: {
    cantidad: number; // 0 = alcanza
    necesario_para: string;
    cobertura_dias: number | null;
    evidencia: string;
  } | null;
  alerta: "bajo_minimo" | "reponer" | null;
}

export interface Inventario {
  fecha: string;
  horizonte_meses: number;
  meses_pronostico: string[];
  plazo_minimo_dias: number;
  productos: ItemInventario[];
}

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
  unidad: UnidadCanonica;
  cantidad: number;
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
  unidad: UnidadCanonica;
  cantidad: number;
  precio_unitario_sin_iva: number;
  subtotal: number;
  aprobacion: "automatica" | "manual" | "supera_tope";
  motivo: string;
  cotizacion_id: string | null;
  evidencia: string | null;
}

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
  estado: "esperando_aprobacion" | "enviada_simulada" | "rechazada";
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

export interface OpcionesCorrida {
  horizonte_meses: number | null;
  esperar_confirmacion: boolean;
  llamar_si_no_responde: boolean;
  negociar: boolean;
  /** El agente le repregunta al proveedor lo dudoso y confirma con su respuesta. */
  resolver_dudas: boolean;
  /** "total" = piloto automático: confirma, manda el mensaje negociado y aprueba todas las órdenes. */
  autonomia: "topes" | "total";
}

export interface NuevaCorrida extends Partial<OpcionesCorrida> {
  texto?: string | null;
}

export interface CorridaAgente {
  id: string;
  pedido_id: string;
  texto: string | null;
  horizonte_meses: number;
  opciones: OpcionesCorrida;
  estado: EstadoCorrida;
  pasos: PasoAgente[];
  interpretacion: {
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
  } | null;
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
