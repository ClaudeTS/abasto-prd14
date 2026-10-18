import type { ReactNode } from "react";
import { AlertCircleIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { iniciales, nombreProveedor } from "@/lib/proveedores";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// Piezas propias de Abasto armadas sobre los componentes de shadcn/ui.

// Familias de la paleta institucional (docs/DISENO.md): verde = en marcha/ok (celeste), azul = la IA trabaja,
// ámbar = te necesita, rojo = cancelado o error.
const TONOS = {
  neutro: "",
  verde: "border-ok-borde bg-ok-bg text-celeste-ink",
  ambar: "border-accion-borde bg-accion-bg text-accion",
  rojo: "border-alerta-borde bg-alerta-bg text-alerta",
  azul: "border-ia-borde bg-ia-bg text-azul-profundo",
  // Datos de ejemplo: rayado neutro, no compite con ningún estado.
  ejemplo:
    "border-gris-claro bg-[repeating-linear-gradient(135deg,#f7f7f7_0_5px,#dde2e1_5px_10px)] text-[#4a5053]",
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
