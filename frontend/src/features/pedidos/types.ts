// Tipos del Bloque 1 — Pedidos (RF-05, RF-10, RF-12, RF-18). Espejo de backend/app/historial_pedidos.py
// y backend/app/rutas_pedidos.py. Montos: number, sin IVA y en pesos salvo que se diga otra cosa.
// Fechas: "AAAA-MM-DD"; fechas y horas: ISO sin zona, como el resto de la API.

export type EstadoPedido =
  | "nuevo"
  | "datos_incompletos"
  | "cotizando"
  | "cotizado"
  | "negociando"
  | "pendiente_aprobacion"
  | "aprobado"
  | "pendiente_entrega"
  | "recibido"
  | "cerrado"
  | "cancelado";

export type ClienteInterno = "ventas" | "personal";
export type OrigenPedido = "solicitud_voz" | "solicitud_email" | "stock_minimo" | "zafra" | "demo";
export type Situacion = "en_tramite" | "recibidos" | "todos";
export type CanalMensaje = "whatsapp" | "email" | "pdf" | "foto" | "audio" | "llamada" | "nota_voz";
export type Proposito = "solicitud" | "cotizacion" | "negociacion" | "orden";
export type ResultadoLlamada = "atendida" | "no_atendida" | "buzon" | "fallida" | "en_curso";

export interface ProductoResumen {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  cantidad: number;
  unidad: string;
}

export interface ResumenPedido {
  id: string;
  numero: string; // "PED-0142"
  titulo: string;
  productos: ProductoResumen[];
  cliente_interno: ClienteInterno;
  origen: OrigenPedido;
  proveedores: string[]; // nombres
  ordenes: string[]; // números de OC
  estado: EstadoPedido;
  creado_en: string;
  actualizado_en: string;
  ejemplo: boolean;
  demo: boolean;
}

export interface ListadoPedidos {
  pedidos: ResumenPedido[];
  conteos: { en_tramite: number; recibidos: number; todos: number };
  total: number;
}

export interface FiltrosPedidos {
  q?: string;
  estado?: EstadoPedido | "";
  cliente_interno?: ClienteInterno | "";
  origen?: OrigenPedido | "";
  desde?: string;
  hasta?: string;
  situacion?: Situacion;
}

export interface EventoEstado {
  estado: EstadoPedido;
  en: string | null;
  detalle: string | null;
}

export interface LineaDetalle {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  unidad: string;
  cantidad: number;
  necesario_para: string | null;
  proveedor_id: string | null;
  proveedor_nombre: string | null;
}

export interface ItemCotizacionDetalle {
  producto_id: string;
  nombre: string;
  precio_original: number;
  moneda_original: string;
  incluye_iva_original: boolean;
  unidad_original: string;
  precio_unitario_sin_iva: number;
  conversion_aplicada: string | null;
  cantidad_minima: number | null;
  evidencia: string;
}

export interface CotizacionDetalle {
  id: string;
  proveedor_id: string;
  proveedor_nombre: string;
  canal: CanalMensaje | null;
  recibida_en: string | null;
  items: ItemCotizacionDetalle[];
  costo_envio: number;
  plazo_pago_dias: number;
  lead_time_dias: number | null;
  validez_dias: number | null;
  vigencia_dias: number;
  vence_el: string | null;
  estado: string;
  observaciones: string[];
}

export interface AsignacionDetalle {
  producto_id: string;
  nombre: string;
  proveedor_id: string;
  proveedor_nombre: string;
  cantidad: number;
  precio_unitario_sin_iva: number;
  subtotal: number;
}

export interface PlanDetalle {
  costo_total: number;
  costo_baseline: number | null;
  ahorro: number | null;
  ahorro_pct: number | null;
  proveedores_usados: string[];
  explicacion: string | null;
  asignaciones: AsignacionDetalle[];
}

export interface LineaOrdenDetalle {
  producto_id: string;
  nombre: string;
  cantidad: number;
  unidad: string;
  precio_unitario_sin_iva: number;
  subtotal: number;
  aprobacion: "automatica" | "manual" | "supera_tope" | null;
  motivo: string | null;
  evidencia: string | null;
}

export interface OrdenDetalle {
  id: string;
  numero: string;
  proveedor_id: string;
  proveedor_nombre: string;
  estado: "pendiente_aprobacion" | "emitida" | "pendiente_entrega" | "recibida" | "cancelada";
  estado_agente: "esperando_aprobacion" | "enviada_simulada" | "rechazada" | null;
  requiere_aprobacion: boolean;
  motivos: string[];
  emitida_por: "agente" | "usuario" | null;
  aprobada_por: string | null;
  emitida_en: string | null;
  recibida_en: string | null;
  envio: number;
  total_sin_iva: number;
  total_con_iva: number;
  lineas: LineaOrdenDetalle[];
  negociacion_id: string | null;
  negociada: boolean;
  corrida_id: string | null; // para aprobar o rechazar (docs/AGENTE.md)
  mensaje: string | null;
}

export interface EstrategiaResumen {
  nombre: string;
  descripcion: string;
  concesion_obtenida_pct: number;
  ganancia_esperada_uyu: number | null;
  riesgo: string;
}

export interface NegociacionDetalle {
  id: string;
  proveedor_id: string;
  proveedor_nombre: string;
  estado: string; // simulada | aprobada | enviada_simulada
  elegida: string;
  mensaje_propuesto: string;
  estrategias: EstrategiaResumen[];
  llamada_id: string | null;
  resultado: string | null;
}

export interface TurnoTranscripcion {
  rol: "abasto" | "proveedor" | "cliente_interno";
  quien: string;
  texto: string;
  segundo: number | null;
}

export interface InfoLlamada {
  tipo: string | null;
  intento: number | null;
  resultado: ResultadoLlamada;
  duracion_segundos: number | null;
  modo: "real" | "simulada" | null;
  audio_disponible_hasta: string | null;
  resumen: string | null;
  acuerdo: boolean | null;
  precio_acordado: number | null;
  telefono: string | null;
}

export interface MensajePedido {
  id: string;
  conversacion_id: string;
  canal: CanalMensaje;
  sentido: "recibido" | "enviado";
  de: string;
  para: string;
  participante: string;
  fecha: string | null;
  texto: string | null;
  transcripcion: TurnoTranscripcion[] | null;
  duracion_segundos: number | null;
  archivo_url: string | null;
  llamada: InfoLlamada | null;
  etiqueta: string | null;
  motivo: string | null;
  nota: string | null;
}

export interface Conversacion {
  id: string;
  contraparte: string;
  contraparte_tipo: "proveedor" | "cliente_interno";
  proveedor_id: string | null;
  proposito: Proposito;
  canales: CanalMensaje[];
  inicio: string | null;
  mensajes: MensajePedido[];
}

export interface DetallePedido {
  id: string;
  numero: string;
  titulo: string;
  descripcion: string | null;
  ejemplo: boolean;
  demo: boolean;
  negocio: string;
  cliente_interno: ClienteInterno;
  origen: OrigenPedido;
  solicitante: string | null;
  creado_en: string;
  actualizado_en: string;
  necesario_desde: string | null;
  necesario_hasta: string | null;
  estado: EstadoPedido;
  historial_estados: EventoEstado[];
  motivo_cancelacion: string | null;
  acciones: ("recibir" | "cerrar")[];
  lineas: LineaDetalle[];
  cotizaciones: CotizacionDetalle[];
  plan: PlanDetalle | null;
  ordenes: OrdenDetalle[];
  negociaciones: NegociacionDetalle[];
  conversaciones: Conversacion[];
  corrida_id: string | null;
  avisos: string[];
}

export type ParteInforme = "pedido" | "dialogo";
