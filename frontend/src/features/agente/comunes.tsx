// Piezas chicas de la pantalla del agente.
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { formatNumero } from "@/lib/format";
import type { Unidad } from "./types";

/** El agente le pregunta algo a quien pidió (RF-01: pide los datos que faltan). */
export function PreguntaAgente({
  children,
  acciones,
  resuelta = false,
  className,
}: {
  children: ReactNode;
  acciones?: ReactNode;
  resuelta?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start gap-2.5", className)}>
      <span
        aria-hidden
        className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-primary text-[11px] font-bold text-primary-foreground"
      >
        A
      </span>
      <div
        className={cn(
          "min-w-0 flex-1 rounded-xl rounded-tl-sm px-3 py-2 text-sm",
          resuelta
            ? "bg-muted/60 text-muted-foreground"
            : "bg-amber-50 text-amber-950 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-100 dark:ring-amber-900",
        )}
      >
        <span className="mb-0.5 block text-[10px] font-medium tracking-wide uppercase opacity-70">
          {resuelta ? "Abasto preguntó" : "Abasto pregunta"}
        </span>
        <span className={cn(resuelta && "line-through decoration-muted-foreground/40")}>{children}</span>
        {acciones && <div className="mt-2 flex flex-wrap items-center gap-2">{acciones}</div>}
      </div>
    </div>
  );
}

/** "150 resmas", "60 L". */
export function cantidadConUnidad(cantidad: number, unidad: Unidad, nombreCorto?: string): string {
  const n = formatNumero(cantidad, Number.isInteger(cantidad) ? 0 : 1);
  if (unidad === "l") return `${n} L`;
  if (unidad === "kg") return `${n} kg`;
  return nombreCorto ? `${n} ${nombreCorto}` : n;
}

export function sufijoUnidad(unidad: Unidad): string {
  return unidad === "l" ? "L" : unidad === "kg" ? "kg" : "u.";
}
