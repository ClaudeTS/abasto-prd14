// Tipos del bloque 3 (reglas, configuración e ingreso). Espejo de backend/app/reglas.py y app/auth.py.
import type { ClienteInterno, Rol } from "@/lib/auth";

export type Moneda = "UYU" | "USD";
export type MotivoReposicion = "pronostico" | "stock_base" | "zafra";

export interface Zafra {
  inicio: string; // "MM-DD"
  fin: string; // "MM-DD"
  cantidad: number;
}

export interface ProveedorHabilitado {
  proveedor_id: string;
  prioridad: number;
  minimo_compra: number | null;
  unidad_venta: string | null;
  factor_conversion: number;
}

export interface Sustituto {
  nombre: string;
  producto_id?: string | null;
  aprobado_por?: string | null;
}

export interface Reglas {
  compra_automatica: boolean;
  stock_minimo: number;
  stock_base: number | null;
  zafra: Zafra | null;
  tope_precio_unitario: number | null;
  moneda_tope: Moneda;
  tope_automatico_uyu: number | null;
  plazo_entrega_max_dias: number | null;
  plazo_pago_requerido_dias: number | null;
  proveedores: ProveedorHabilitado[];
  sustitutos: Sustituto[];
  descuento_objetivo_pct: number | null;
  concesion_maxima_pct: number | null;
  cliente_interno: ClienteInterno;
}

export type PropuestaReglas = Partial<Reglas>;

export interface Reposicion {
  cantidad: number;
  necesario_para: string;
  cobertura_dias: number | null;
  evidencia: string;
  motivo?: MotivoReposicion;
}

export interface PrecioVigente {
  proveedor_id: string;
  proveedor_nombre: string;
  precio_sin_iva_uyu: number;
  cotizacion_id: string;
  pedido_id: string;
  validez_dias: number | null;
  evidencia: string;
}

export interface Contexto {
  unidad: string;
  stock_actual: number;
  en_camino: number;
  fecha_corte: string;
  proximo_cierre: string;
  reposicion: Reposicion | null;
  precios: PrecioVigente[];
  mejor_precio: PrecioVigente | null;
  tope_unitario_uyu: number | null;
  tipo_cambio_usd: number;
  en_zafra: boolean;
}

export interface VistaReglas {
  producto_id: string;
  nombre: string;
  nombre_corto: string;
  unidad: string;
  tipo: "consumible" | "equipamiento";
  reglas: Reglas;
  contexto: Contexto;
  actualizado_por: string | null;
  actualizado_en: string | null;
}

export interface CambioRegla {
  id: string;
  tabla: "regla_producto" | "configuracion";
  registro: string;
  campo: string;
  etiqueta: string;
  texto_anterior: string;
  texto_nuevo: string;
  usuario: string;
  fecha: string;
  motivo: string;
  lote: string;
  revierte: string | null;
  revertido_por: string | null;
}

export interface CambioCampo {
  campo: string;
  etiqueta: string;
  anterior: string;
  nuevo: string;
}

export interface VistaPrevia {
  valido: boolean;
  errores: Record<string, string>;
  cambios: CambioCampo[];
  aplica_cierre: boolean;
  dispara_compra: boolean;
  cantidad: number;
  motivo: MotivoReposicion | null;
  aprobacion: "automatica" | "requiere_aprobacion" | null;
  mejor_precio: PrecioVigente | null;
  tope_unitario_uyu: number | null;
  bajo_tope: boolean | null;
  texto: string;
  evidencia: string | null;
}

export interface Configuracion {
  tipo_cambio_usd: number;
  fecha_tipo_cambio: string | null;
  iva: number;
  vigencia_dias_default: number;
  moneda_base: Moneda;
  monedas: Moneda[];
  actualizado_por: string | null;
  actualizado_en: string | null;
}

export type CambioConfiguracion = Partial<
  Pick<Configuracion, "tipo_cambio_usd" | "fecha_tipo_cambio" | "iva" | "vigencia_dias_default" | "moneda_base">
> & { motivo?: string };

export interface UsuarioListado {
  id: string;
  nombre: string;
  email: string;
  rol: Rol;
  cliente_interno: ClienteInterno;
  activo: boolean;
  ultimo_ingreso: string | null;
}
