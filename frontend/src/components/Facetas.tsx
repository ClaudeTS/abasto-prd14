// Facetas celestes de la portada de la plantilla institucional, para los bloques oscuros (hero de Inicio,
// encabezado del pedido). Decorativo: aria-hidden y detrás del contenido.
import { cn } from "@/lib/utils";

export default function Facetas({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 400 220"
      preserveAspectRatio="xMaxYMid slice"
      className={cn("pointer-events-none absolute inset-y-0 right-0 h-full w-3/5", className)}
    >
      <polygon points="400,0 400,220 210,220" fill="#01adbd" opacity=".85" />
      <polygon points="400,0 250,220 120,220" fill="#01adbd" opacity=".35" />
      <polygon points="400,20 300,0 400,120" fill="#7fdde6" opacity=".55" />
      <polygon points="400,90 180,220 330,220" fill="#00a0df" opacity=".35" />
      <polygon points="400,0 330,0 160,220 230,220" fill="#01adbd" opacity=".18" />
    </svg>
  );
}
