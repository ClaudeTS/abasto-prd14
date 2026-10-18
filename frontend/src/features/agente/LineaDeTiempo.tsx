// Los 9 pasos del agente (docs/AGENTE.md §1) con el `detalle` de cada uno.
import { Link } from "react-router-dom";
import { ArrowUpRightIcon, CheckIcon, HandIcon, MinusIcon, XIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Etiqueta } from "@/components/comunes";
import { Spinner } from "@/components/ui/spinner";
import type { CorridaAgente, EstadoPaso, PasoAgente, PasoId } from "./types";

/** Vistas de detalle de siempre, desde el paso (docs/AGENTE.md §6). */
function enlace(paso: PasoAgente, pedidoId: string): { to: string; texto: string } | null {
  if (paso.estado === "pendiente" || paso.estado === "omitido") return null;
  const porPaso: Partial<Record<PasoId, { to: string; texto: string }>> = {
    cotizar: { to: "/feed", texto: "Ver las respuestas" },
    revisar: { to: "/cotizaciones", texto: "Ver las cotizaciones" },
    optimizar: { to: `/pedidos/${pedidoId}`, texto: "Ver en el pedido" },
  };
  if (paso.id === "optimizar" && paso.estado !== "hecho") return null;
  return porPaso[paso.id] ?? null;
}

function segundos(p: PasoAgente): number | null {
  if (!p.inicio || !p.fin) return null;
  const s = (Date.parse(p.fin) - Date.parse(p.inicio)) / 1000;
  return Number.isFinite(s) && s >= 1 ? Math.round(s) : null;
}

function Marca({ estado }: { estado: EstadoPaso }) {
  const base = "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full ring-4 ring-card";
  switch (estado) {
    case "hecho":
      return (
        <span className={cn(base, "bg-primary text-primary-foreground")}>
          <CheckIcon className="size-4" />
        </span>
      );
    case "en_curso":
      return (
        <span className={cn(base, "bg-background text-foreground ring-card")}>
          <span className="absolute inset-0 animate-ping rounded-full bg-foreground/15" aria-hidden />
          <span className="absolute inset-0 rounded-full border-2 border-foreground" aria-hidden />
          <Spinner className="size-3.5" />
        </span>
      );
    case "esperando":
      return (
        <span className={cn(base, "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300")}>
          <span className="absolute inset-0 animate-ping rounded-full bg-amber-400/30" aria-hidden />
          <HandIcon className="relative size-3.5" />
        </span>
      );
    case "error":
      return (
        <span className={cn(base, "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300")}>
          <XIcon className="size-4" />
        </span>
      );
    case "omitido":
      return (
        <span className={cn(base, "bg-muted text-muted-foreground")}>
          <MinusIcon className="size-3.5" />
        </span>
      );
    default:
      return <span className={cn(base, "border-2 border-dashed border-muted-foreground/30 bg-background")} />;
  }
}

export default function LineaDeTiempo({ corrida }: { corrida: CorridaAgente }) {
  const pasos = corrida.pasos;
  return (
    <ol className="relative" aria-label="Pasos del agente">
      {pasos.map((p, i) => {
        const ultimo = i === pasos.length - 1;
        const link = enlace(p, corrida.pedido_id);
        const s = segundos(p);
        const activo = p.estado === "en_curso" || p.estado === "esperando";
        // Al cancelar, el back pone el mismo detalle en todos los pasos que faltaban: se muestra una vez.
        const repetido = i > 0 && !!p.detalle && p.detalle === pasos[i - 1].detalle;
        return (
          <li key={p.id} className="relative flex gap-3 pb-5 last:pb-0" aria-current={activo ? "step" : undefined}>
            {!ultimo && (
              <span
                aria-hidden
                className={cn(
                  "absolute top-7 bottom-0 left-[13px] w-0.5",
                  p.estado === "hecho" || p.estado === "omitido" ? "bg-foreground/70" : "bg-border",
                )}
              />
            )}
            <Marca estado={p.estado} />
            <div className={cn("min-w-0 flex-1 pt-0.5", p.estado === "pendiente" && "opacity-55")}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className={cn("text-sm font-medium", activo && "font-semibold")}>{p.titulo}</span>
                {p.estado === "esperando" && <Etiqueta tono="ambar">Te espera</Etiqueta>}
                {p.estado === "error" && <Etiqueta tono="rojo">Falló</Etiqueta>}
                {p.estado === "omitido" && <span className="text-xs text-muted-foreground">Salteado</span>}
                {s !== null && <span className="text-xs text-muted-foreground tabular-nums">{s} s</span>}
              </div>
              {p.detalle && !repetido && (
                <p
                  className={cn(
                    "mt-0.5 text-sm leading-snug text-pretty",
                    p.estado === "error" ? "text-destructive" : "text-muted-foreground",
                    p.estado === "en_curso" && "text-foreground",
                  )}
                >
                  {p.detalle}
                </p>
              )}
              {link && (
                <Link
                  to={link.to}
                  className="mt-1 inline-flex items-center gap-0.5 text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                >
                  {link.texto} <ArrowUpRightIcon className="size-3" />
                </Link>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
