// Tipos del bloque 4 (Proveedores y negociación). Espejo de backend/app/perfiles.py y app/ranking.py.

export type NivelConfianza = "alta" | "media" | "baja" | "sin_datos";
export type EstadoAlta = "activo" | "en_revision" | "rechazado";

export interface Antiguedad {
  fecha_alta: string | null;
  dias: number | null;
  texto: string;
}

export interface Confianza {
  nivel: NivelConfianza;
  desvio_promedio_pp: number | null;
  negociaciones: number;
  motivo: string;
  incluye_ejemplos: boolean;
}

export interface Ficha {
  id: string;
  nombre: string;
  rubro: string;
  canal_preferido: string;
  confiabilidad: number | null;
  antiguedad: Antiguedad;
  cumplimiento_historico_pct: number | null;
  garantia_meses: number | null;
  email: string | null;
  whatsapp: boolean | null;
  alta_por: "usuario" | "agente";
  estado: EstadoAlta;
  datos_ejemplo: boolean;
}

export interface ResumenPerfil {
  sensible_a: string[];
  no_sensible_a: string[];
  concesion_tipica: string;
  concesion_tipica_rango: string | null;
  precio_piso_pct: number | null;
}

export interface ProveedorListado extends Ficha {
  productos: string[];
  perfil: ResumenPerfil | null;
  confianza: Confianza;
  habitual: boolean;
}

export interface Listado {
  proveedores: ProveedorListado[];
  datos_ejemplo: string[];
  umbrales_confianza: { alta_pp: number; media_pp: number; min_negociaciones: number };
}

export interface FilaHistorial {
  origen: "real" | "ejemplo";
  negociacion_id: string | null;
  pedido_id: string | null;
  fecha: string | null;
  estrategia: string | null;
  estado: string;
  concesion_simulada_pct: number | null;
  concesion_real_pct: number | null;
  desvio_pp: number | null;
  llamada_id: string | null;
  llamada_modo: "real" | "simulada" | null;
  cuenta_para_confianza: boolean;
  nota: string | null;
  ejemplo: boolean;
}

export interface TiempoCanal {
  canal: string;
  respuestas: number;
  promedio_segundos: number;
  mediana_segundos: number;
}

export interface TiempoRespuesta {
  canales: TiempoCanal[];
  llamadas: { realizadas: number; atendidas: number; duracion_promedio_segundos: number | null } | null;
  mas_rapido: string | null;
  fuente: string;
}

export interface EdicionHistorial {
  fecha: string;
  usuario: string;
  motivo: string | null;
  cambios: Record<string, { antes: unknown; despues: unknown }>;
}

export interface CamposPerfil {
  estilo: string;
  condiciones_habituales: string;
  precio_piso_pct: number | null;
  sensible_a: string[];
  no_sensible_a: string[];
  concesion_tipica: string;
}

export interface Perfil extends CamposPerfil {
  proveedor: Ficha;
  concesion_tipica_rango: string | null;
  negociaciones_observadas: number;
  confianza: Confianza;
  editado: boolean;
  actualizado_el: string | null;
  actualizado_por: string | null;
  version: number;
  historial_ediciones: EdicionHistorial[];
  historial_negociaciones: FilaHistorial[];
  tiempo_respuesta: TiempoRespuesta;
  /** Solo proveedores dados de alta en Abasto: datos y conversación del agente (RF-19). */
  alta: Alta | null;
}

export type EdicionPerfil = Partial<CamposPerfil> & { motivo?: string; usuario?: string };

// ─────────── Altas (RF-19)
export interface TurnoAlta {
  rol: "abasto" | "proveedor";
  texto: string;
  canal: string;
  segundo: number;
}

export interface CondicionesAlta {
  plazo_pago_dias: number | null;
  plazo_entrega_dias: number | null;
  pedido_minimo: string | null;
  envio: string | null;
  garantia_meses: number | null;
}

export interface Alta {
  id: string;
  nombre: string;
  razon_social: string;
  rubro: string;
  contacto: { nombre: string | null; email: string | null; telefono: string | null };
  whatsapp: boolean;
  canales: string[];
  canal_preferido: string;
  condiciones: CondicionesAlta;
  productos: string[];
  estado: EstadoAlta;
  alta_por: "usuario" | "agente";
  creado_en: string;
  aprobado_por: string | null;
  conversacion: TurnoAlta[];
  simulada: boolean;
  pedido_id?: string | null;
}

export interface AltaManual {
  nombre: string;
  razon_social?: string;
  rubro?: string;
  contacto?: { nombre?: string; email?: string; telefono?: string };
  whatsapp?: boolean;
  canal_preferido?: string;
  condiciones?: Partial<CondicionesAlta>;
  productos?: string[];
  usuario?: string;
}

export interface AltaAgente {
  nombre: string;
  telefono?: string;
  email?: string;
  canal: "whatsapp" | "email" | "llamada";
  rubro?: string;
  productos?: string[];
  pedido_id?: string;
  motivo?: string;
}

// ─────────── Ranking (RF-07)
export interface Candidato {
  proveedor_id: string;
  nombre: string;
  cotizacion_id: string;
  costo_comparable: number;
  subtotal: number;
  costo_envio: number;
  entrega_dias: number;
  pago_dias: number;
  garantia_meses: number | null;
  especificaciones: string;
  descripcion_original: string | null;
  evidencia: string;
  antiguedad_dias: number | null;
  antiguedad: string;
  cumplimiento_historico_pct: number | null;
  datos_ejemplo: boolean;
  en_plan: boolean;
  motivo: string;
  // en el ranking
  posicion?: number;
  criterio?: "precio" | "atributos" | "antiguedad";
  atributos_ganados?: string[];
  // en excluidos
  tipo_exclusion?: "minimo" | "plazo" | "revisar";
}

export interface RankingProducto {
  producto_id: string;
  nombre: string;
  unidad: string;
  cantidad: number;
  necesario_para: string;
  dias_requeridos: number;
  ranking: Candidato[];
  excluidos: Candidato[];
  sin_cotizar: string[];
  pocos_proveedores: boolean;
  sugerencia_alta: string | null;
}

export interface Ranking {
  pedido_id: string;
  calculado_en: string;
  regla: string[];
  tolerancia_empate_pct: number;
  minimo_proveedores: number;
  hay_plan: boolean;
  datos_ejemplo: string[];
  productos: RankingProducto[];
}

// ─────────── Evaluación (RF-16)
export type ResultadoDim = "mejora" | "iguala" | "peor" | "sin_dato";
export type Dimension = "precio" | "entrega" | "pago" | "garantia";

export interface FilaDimension {
  propio: number | null;
  mejor_del_resto: number | null;
  proveedor: string | null;
  resultado: ResultadoDim;
}

export interface Comparacion {
  proveedor_id: string;
  nombre: string;
  elegible: boolean;
  motivo_no_elegible: string | null;
  propio_total: number;
  otro_total: number;
  otro_entrega_dias: number;
  otro_pago_dias: number;
  otro_garantia_meses: number | null;
  resultado: Record<Dimension, ResultadoDim>;
  supera: boolean;
}

export interface RiesgoPlazo {
  nivel: "bajo" | "aceptable" | "alto" | "sin_dato";
  diferencia_dias: number | null;
  texto: string;
}

export interface EvaluacionEstrategia {
  nombre: "competencia" | "volumen" | "plazo";
  ensayada: boolean;
  recomendada: boolean;
  concesion_obtenida_pct: number;
  ganancia_esperada_uyu: number;
  oferta: {
    precios: Record<string, number>;
    total: number;
    entrega_dias: number;
    pago_dias: number;
    garantia_meses: number | null;
  };
  dimensiones: Record<Dimension, FilaDimension>;
  comparaciones: Comparacion[];
  supera_a: number;
  elegibles: number;
  gana: boolean;
  riesgo_gemelo: "bajo" | "medio" | "alto";
  riesgo_plazo: RiesgoPlazo;
  riesgo: "bajo" | "medio" | "alto";
  conclusion: string;
}

export interface Evaluacion {
  negociacion_id: string;
  pedido_id: string;
  proveedor_id: string;
  proveedor_nombre: string;
  elegida: string;
  items: { producto_id: string; nombre: string; cantidad: number; precio_cotizado: number }[];
  condiciones_actuales: { entrega_dias: number; pago_dias: number; garantia_meses: number | null };
  referencia_regular: { proveedor_id: string | null; nombre: string; entrega_dias: number; criterio: string } | null;
  margen_riesgo_dias: number;
  estrategias: EvaluacionEstrategia[];
  datos_ejemplo: string[];
  regla: string;
}
