// Etiquetas, colores e íconos de pedidos: estados (§6.2), canales (RF-10), origen y cliente interno (RF-05).
import {
  AudioLinesIcon,
  CalendarRangeIcon,
  CameraIcon,
  FileTextIcon,
  MailIcon,
  MessageSquareIcon,
  MicIcon,
  PackageMinusIcon,
  PhoneIcon,
  PlayCircleIcon,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { CanalMensaje, ClienteInterno, EstadoPedido, OrigenPedido, ResultadoLlamada } from "./types";

/** El camino normal de un pedido, en orden (cancelado va aparte). */
export const CAMINO: EstadoPedido[] = [
  "nuevo",
  "datos_incompletos",
  "cotizando",
  "cotizado",
  "negociando",
  "pendiente_aprobacion",
  "aprobado",
  "pendiente_entrega",
  "recibido",
  "cerrado",
];
export const ESTADOS: EstadoPedido[] = [...CAMINO, "cancelado"];

export const ETIQUETA_ESTADO: Record<EstadoPedido, string> = {
  nuevo: "Nuevo",
  datos_incompletos: "Datos incompletos",
  cotizando: "Cotizando",
  cotizado: "Cotizado",
  negociando: "Negociando",
  pendiente_aprobacion: "Pendiente de aprobación",
  aprobado: "Aprobado",
  pendiente_entrega: "Pendiente de entrega",
  recibido: "Recibido",
  cerrado: "Cerrado",
  cancelado: "Cancelado",
};

const TONO = {
  neutro: "border-border bg-background text-foreground",
  gris: "border-transparent bg-muted text-muted-foreground",
  verde:
    "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300",
  ambar: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  azul: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
  rojo: "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  oscuro: "border-transparent bg-primary text-primary-foreground",
} as const;
export type TonoPedido = keyof typeof TONO;

const TONO_ESTADO: Record<EstadoPedido, TonoPedido> = {
  nuevo: "neutro",
  datos_incompletos: "ambar",
  cotizando: "gris",
  cotizado: "azul",
  negociando: "azul",
  pendiente_aprobacion: "ambar",
  aprobado: "verde",
  pendiente_entrega: "neutro",
  recibido: "verde",
  cerrado: "oscuro",
  cancelado: "rojo",
};

export function Marca({
  tono = "neutro",
  className,
  children,
  title,
}: {
  tono?: TonoPedido;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <Badge variant="outline" title={title} className={cn(TONO[tono], className)}>
      {children}
    </Badge>
  );
}

export function BadgeEstado({ estado, className }: { estado: EstadoPedido; className?: string }) {
  return (
    <Marca tono={TONO_ESTADO[estado]} className={className}>
      {ETIQUETA_ESTADO[estado]}
    </Marca>
  );
}

export function EtiquetaEjemplo({ className }: { className?: string }) {
  return (
    <Marca tono="gris" className={className} title="Pedido de ejemplo: no es una compra real">
      Datos de ejemplo
    </Marca>
  );
}

export const CANAL: Record<CanalMensaje, { etiqueta: string; icono: LucideIcon }> = {
  whatsapp: { etiqueta: "WhatsApp", icono: MessageSquareIcon },
  email: { etiqueta: "Email", icono: MailIcon },
  pdf: { etiqueta: "PDF", icono: FileTextIcon },
  foto: { etiqueta: "Foto", icono: CameraIcon },
  audio: { etiqueta: "Audio de WhatsApp", icono: AudioLinesIcon },
  llamada: { etiqueta: "Llamada", icono: PhoneIcon },
  nota_voz: { etiqueta: "Nota de voz", icono: MicIcon },
};

export function BadgeCanal({ canal }: { canal: CanalMensaje }) {
  const { etiqueta, icono: Icono } = CANAL[canal];
  return (
    <Marca tono="neutro">
      <Icono aria-hidden />
      {etiqueta}
    </Marca>
  );
}

export const ORIGEN: Record<OrigenPedido, { etiqueta: string; icono: LucideIcon }> = {
  solicitud_voz: { etiqueta: "Nota de voz", icono: MicIcon },
  solicitud_email: { etiqueta: "Email", icono: MailIcon },
  stock_minimo: { etiqueta: "Stock mínimo", icono: PackageMinusIcon },
  zafra: { etiqueta: "Zafra", icono: CalendarRangeIcon },
  demo: { etiqueta: "Demo guiada", icono: PlayCircleIcon },
};

export function Origen({ origen, className }: { origen: OrigenPedido; className?: string }) {
  const { etiqueta, icono: Icono } = ORIGEN[origen];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-foreground/80", className)}>
      <Icono className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      {etiqueta}
    </span>
  );
}

export const CLIENTE: Record<ClienteInterno, string> = { ventas: "Ventas", personal: "Personal" };

export const RESULTADO_LLAMADA: Record<ResultadoLlamada, { etiqueta: string; tono: TonoPedido }> = {
  atendida: { etiqueta: "Atendida", tono: "verde" },
  no_atendida: { etiqueta: "No atendió", tono: "rojo" },
  buzon: { etiqueta: "Buzón de voz", tono: "rojo" },
  fallida: { etiqueta: "Falló", tono: "rojo" },
  en_curso: { etiqueta: "En curso", tono: "azul" },
};

export const PROPOSITO: Record<string, string> = {
  solicitud: "Solicitud interna",
  cotizacion: "Cotización",
  negociacion: "Negociación",
  orden: "Orden de compra",
};

export const MOTIVO: Record<string, string> = {
  solicitud_cotizacion: "Solicitud de cotización",
  solicitud_datos: "Pedido de datos",
  reintento: "Secuencia de contacto",
  aviso_no_atendio: "Aviso: no atendió",
  negociacion: "Negociación",
  orden: "Orden de compra",
};

export function tonoEtiquetaMensaje(etiqueta: string): TonoPedido {
  if (/le[ií]da|confirmada/i.test(etiqueta)) return "verde";
  if (/revisar|leyendo/i.test(etiqueta)) return "ambar";
  if (/no se pudo/i.test(etiqueta)) return "rojo";
  return "neutro";
}

// ─────────── fechas ───────────
const dos = (n: number) => String(n).padStart(2, "0");

function parse(iso: string): Date | null {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "17/10 09:02". */
export function diaHora(iso: string | null): string {
  const d = iso ? parse(iso) : null;
  return d ? `${dos(d.getDate())}/${dos(d.getMonth() + 1)} ${dos(d.getHours())}:${dos(d.getMinutes())}` : "—";
}

/** "17/10/2026 09:02". */
export function fechaHoraLarga(iso: string | null): string {
  const d = iso ? parse(iso) : null;
  return d
    ? `${dos(d.getDate())}/${dos(d.getMonth() + 1)}/${d.getFullYear()} ${dos(d.getHours())}:${dos(d.getMinutes())}`
    : "—";
}

/** "17/10/2026". */
export function fechaLarga(iso: string | null): string {
  const d = iso ? parse(iso) : null;
  return d ? `${dos(d.getDate())}/${dos(d.getMonth() + 1)}/${d.getFullYear()}` : "—";
}

/** 112 → "1:52". */
export function duracion(segundos: number | null): string {
  const s = segundos ?? 0;
  return `${Math.floor(s / 60)}:${dos(s % 60)}`;
}

/** "Notebooks, sillas, resmas" o, si es uno solo, "Resma papel A4 75 g · 100 u.". */
export function textoProductos(
  productos: { nombre: string; nombre_corto: string; cantidad: number; unidad: string }[],
): string {
  if (productos.length === 1) {
    const p = productos[0]!;
    return `${p.nombre} · ${cantidadConUnidad(p.cantidad, p.unidad)}`;
  }
  const cortos = productos.map((p) => p.nombre_corto);
  const texto = cortos.join(", ");
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function cantidadConUnidad(cantidad: number, unidad: string): string {
  const n = Number.isInteger(cantidad)
    ? String(cantidad).replace(/\B(?=(\d{3})+(?!\d))/g, ".")
    : String(cantidad).replace(".", ",");
  return unidad === "l" ? `${n} L` : unidad === "kg" ? `${n} kg` : `${n} u.`;
}
