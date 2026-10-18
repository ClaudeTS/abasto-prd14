// Piezas chicas del bloque 4: etiquetas de confianza, canales, formatos y campos de formulario.
import type { ComponentProps, ReactNode } from "react";
import { FlaskConicalIcon } from "lucide-react";
import { Etiqueta, type Tono } from "@/components/comunes";
import { formatNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Confianza, NivelConfianza } from "./types";

export const TONO_CONFIANZA: Record<NivelConfianza, Tono> = {
  alta: "verde",
  media: "ambar",
  baja: "rojo",
  sin_datos: "neutro",
};

const NOMBRE_CONFIANZA: Record<NivelConfianza, string> = {
  alta: "Alta",
  media: "Media",
  baja: "Baja",
  sin_datos: "Sin datos",
};

export function pp(v: number): string {
  return `±${formatNumero(Math.abs(v), 1)} pp`;
}

export function textoConfianza(c: Confianza): string {
  if (c.nivel === "sin_datos") return "Sin datos";
  if (c.nivel === "baja" && c.negociaciones < 3)
    return c.negociaciones === 0
      ? "Baja · sin negociaciones"
      : `Baja · ${c.negociaciones} negociación${c.negociaciones === 1 ? "" : "es"}`;
  return `${NOMBRE_CONFIANZA[c.nivel]}${c.desvio_promedio_pp !== null ? ` · ${pp(c.desvio_promedio_pp)}` : ""}`;
}

export function BadgeConfianza({ c, corta = false }: { c: Confianza; corta?: boolean }) {
  return (
    <Etiqueta tono={TONO_CONFIANZA[c.nivel]} title={c.motivo}>
      {corta ? `Confianza ${NOMBRE_CONFIANZA[c.nivel].toLowerCase()}` : textoConfianza(c)}
    </Etiqueta>
  );
}

const CANAL: Record<string, string> = {
  whatsapp_texto: "WhatsApp",
  whatsapp_audio: "Audio de WhatsApp",
  pdf: "Email (PDF)",
  foto: "Foto por WhatsApp",
  llamada: "Llamada",
  whatsapp: "WhatsApp",
  email: "Email",
};

export function nombreCanal(c: string): string {
  return CANAL[c] ?? c;
}

export const dias = (n: number) => (n === 1 ? "1 día" : `${formatNumero(n)} días`);
export const pago = (n: number) => (n === 0 ? "contado" : `${formatNumero(n)} días`);
export const garantia = (m: number | null) => (m ? `${m} meses` : "s/d");

export function duracion(segundos: number): string {
  if (segundos < 60) return `${Math.round(segundos)} s`;
  if (segundos < 3600) return `${Math.round(segundos / 60)} min`;
  const h = segundos / 3600;
  return `${formatNumero(h, h < 10 ? 1 : 0)} h`;
}

export function fecha(iso: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a.slice(2)}`;
}

/** Leyenda para lo que no sale de datos reales (AGENTS: lo de ejemplo dice "Datos de ejemplo"). */
export function DatosEjemplo({ children, className }: { children?: ReactNode; className?: string }) {
  return (
    <p className={cn("flex items-start gap-1.5 text-xs text-muted-foreground", className)}>
      <FlaskConicalIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>
        <span className="font-medium text-foreground/80">Datos de ejemplo.</span> {children}
      </span>
    </p>
  );
}

const CAMPO =
  "h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 text-sm shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30";

export function Entrada({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(CAMPO, className)} {...props} />;
}

export function Selector({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(CAMPO, "pr-8", className)} {...props} />;
}

export function Campo({ etiqueta, ayuda, children, className }: { etiqueta: string; ayuda?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-1.5 text-sm", className)}>
      <span className="font-medium">{etiqueta}</span>
      {children}
      {ayuda && <span className="text-xs text-muted-foreground">{ayuda}</span>}
    </label>
  );
}

/** Fila etiqueta / valor de las fichas (el .kv de los mockups). */
export function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b py-2.5 last:border-0 sm:flex-row sm:justify-between sm:gap-6">
      <span className="shrink-0 text-muted-foreground">{etiqueta}</span>
      <span className="sm:text-right">{children}</span>
    </div>
  );
}
