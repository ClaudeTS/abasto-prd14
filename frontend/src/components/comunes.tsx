import type { ReactNode } from "react";
import { AlertCircleIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { iniciales, nombreProveedor } from "@/lib/proveedores";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// Piezas propias de Abasto armadas sobre los componentes de shadcn/ui.

const TONOS = {
  neutro: "",
  verde: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300",
  ambar: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  rojo: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  azul: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
} as const;

export type Tono = keyof typeof TONOS;

/** Badge outline de shadcn con un tono semántico suave (estado, no decoración). */
export function Etiqueta({
  tono = "neutro",
  className,
  children,
  title,
}: {
  tono?: Tono;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <Badge variant="outline" title={title} className={cn(TONOS[tono], className)}>
      {children}
    </Badge>
  );
}

export function Avatar({ proveedorId, className }: { proveedorId: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground ring-1 ring-foreground/10",
        className,
      )}
    >
      {iniciales(nombreProveedor(proveedorId))}
    </span>
  );
}

export function Encabezado({ titulo, bajada, children }: { titulo: string; bajada?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1.5">
        <h1 className="text-3xl font-semibold tracking-tight">{titulo}</h1>
        {bajada && <p className="max-w-3xl text-base text-muted-foreground">{bajada}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function ErrorBanner({ mensaje, onReintentar }: { mensaje: string | null; onReintentar?: () => void }) {
  if (!mensaje) return null;
  return (
    <Alert variant="destructive">
      <AlertCircleIcon />
      <AlertTitle>Algo salió mal</AlertTitle>
      <AlertDescription>{mensaje}</AlertDescription>
      {onReintentar && (
        <AlertAction>
          <Button size="xs" variant="outline" onClick={onReintentar}>
            Reintentar
          </Button>
        </AlertAction>
      )}
    </Alert>
  );
}

/** Tres puntitos de "escribiendo…". */
export function Puntos() {
  return (
    <span className="inline-flex gap-0.5 align-middle" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span key={i} className="size-1 animate-punto rounded-full bg-current" style={{ animationDelay: `${i * 0.18}s` }} />
      ))}
    </span>
  );
}

/** Resalta las frases (evidencias) dentro de un texto, sin distinguir mayúsculas. */
export function TextoResaltado({ texto, frases }: { texto: string; frases: string[] }) {
  const rangos: [number, number][] = [];
  const bajo = texto.toLowerCase();
  for (const frase of frases) {
    const f = frase.trim().toLowerCase();
    if (!f) continue;
    const i = bajo.indexOf(f);
    if (i >= 0) rangos.push([i, i + f.length]);
  }
  rangos.sort((a, b) => a[0] - b[0]);
  const partes: ReactNode[] = [];
  let cursor = 0;
  rangos.forEach(([ini, fin], k) => {
    if (ini < cursor) return;
    partes.push(texto.slice(cursor, ini));
    partes.push(
      <mark key={k} className="rounded-sm bg-yellow-200/80 px-0.5 text-foreground dark:bg-yellow-500/30">
        {texto.slice(ini, fin)}
      </mark>,
    );
    cursor = fin;
  });
  partes.push(texto.slice(cursor));
  return <>{partes}</>;
}

/** Bloque de cita con la evidencia literal de un precio. */
export function Evidencia({ texto, className }: { texto: string; className?: string }) {
  return (
    <blockquote className={cn("border-l-2 border-yellow-400 pl-3 text-sm text-muted-foreground italic", className)}>
      “{texto}”
    </blockquote>
  );
}
