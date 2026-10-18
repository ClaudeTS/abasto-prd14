import { ConstructionIcon } from "lucide-react";

/** Página provisoria mientras se implementa su bloque del PRD 1.4. */
export default function EnConstruccion({ titulo, requisitos }: { titulo: string; requisitos: string }) {
  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-2xl font-semibold tracking-tight">{titulo}</h1>
      <div className="mt-6 flex items-center gap-3 rounded-xl border border-dashed bg-background p-6 text-muted-foreground">
        <ConstructionIcon className="size-5" aria-hidden />
        En construcción · {requisitos} (docs/PRD-1.4.md)
      </div>
    </div>
  );
}
