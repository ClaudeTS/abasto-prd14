import { InfoIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Etiqueta } from "@/components/comunes";
import { valorKpi, variacion } from "./formato";
import type { Kpi } from "./types";

function Fuentes({ k }: { k: Kpi }) {
  const { reales, ejemplo } = k.fuentes;
  if (!reales && !ejemplo) return <>Sin datos en el período.</>;
  const partes = [];
  if (reales) partes.push(`${reales} ${reales === 1 ? "dato real" : "datos reales"}`);
  if (ejemplo) partes.push(`${ejemplo} de ejemplo`);
  return <>Base: {partes.join(" + ")}.</>;
}

export function TarjetaKpi({ k }: { k: Kpi }) {
  const delta = variacion(k);
  return (
    <Card size="sm" className="gap-0" data-testid={`kpi-${k.id}`}>
      <CardContent className="flex-1 gap-0">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm leading-snug text-muted-foreground">{k.nombre}</h3>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="-m-1 rounded-md p-1 text-muted-foreground/70 hover:bg-muted hover:text-foreground"
                aria-label={`Cómo se calcula: ${k.nombre}`}
              >
                <InfoIcon className="size-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-72 text-pretty">
              {k.como_se_calcula} <Fuentes k={k} />
            </TooltipContent>
          </Tooltip>
        </div>
        <div className="mt-2 text-3xl font-semibold tracking-tight tabular-nums">
          {k.valor === null ? <span className="text-muted-foreground">—</span> : valorKpi(k.valor, k.unidad, k.id)}
        </div>
        <p className="mt-1 mb-3 min-h-5 text-[13px] text-muted-foreground">
          {k.valor === null ? "Sin datos en el período" : k.detalle}
        </p>
        {delta && (
          <p
            className={cn(
              "-mt-3 mb-3 text-[13px] font-medium",
              delta.mejora === true && "text-emerald-700 dark:text-emerald-400",
              delta.mejora === false && "text-red-700 dark:text-red-400",
              delta.mejora === null && "text-muted-foreground",
            )}
          >
            {delta.texto}
          </p>
        )}
        <div className="mt-auto flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5 border-t pt-3 text-xs text-muted-foreground">
          {k.meta ? (
            <span className={cn(k.meta.cumple === true && "text-emerald-700 dark:text-emerald-400", k.meta.cumple === false && "text-red-700 dark:text-red-400")}>
              Meta {k.meta.texto}
              {k.meta.cumple === true && " · cumple"}
              {k.meta.cumple === false && " · no cumple"}
            </span>
          ) : (
            <span>Meta a definir</span>
          )}
          {k.ejemplo && (
            <Etiqueta tono="ambar" title="Incluye datos del histórico de ejemplo">
              Datos de ejemplo
            </Etiqueta>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
