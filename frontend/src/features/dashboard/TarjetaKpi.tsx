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

// Bloques con significado (docs/DISENO.md): un solo KPI en celeste (el que importa), uno en grafito y los de IA en azul.
type Variante = "destacado" | "oscuro" | "ia" | "normal";
const VARIANTE: Record<string, Variante> = {
  ahorro_cotizacion_inicial: "destacado",
  tiempo_pedido_a_orden: "oscuro",
  precision_gemelo: "ia",
  cotizaciones_sin_correccion: "ia",
};
const FAMILIA: Record<string, string> = {
  ahorro_cotizacion_inicial: "Ahorro",
  efectividad_negociacion: "Ahorro",
  tiempo_pedido_a_orden: "Tiempo",
  tiempo_respuesta_pedidos_internos: "Tiempo",
  precision_gemelo: "IA",
  cotizaciones_sin_correccion: "IA",
  tasa_respuesta_proveedores: "Proveedores",
  tasa_compras_automaticas: "Automatización",
};
const ESTILO: Record<Variante, { card: string; sub: string; valor: string; mejora: string; empeora: string; borde: string }> = {
  destacado: {
    card: "border-celeste bg-celeste text-grafito",
    sub: "text-grafito/80",
    valor: "",
    mejora: "text-grafito",
    empeora: "text-grafito",
    borde: "border-grafito/20",
  },
  oscuro: {
    card: "border-grafito bg-grafito text-white",
    sub: "text-gris-oscuro",
    valor: "",
    mejora: "text-celeste",
    empeora: "text-[#ff9b9b]",
    borde: "border-white/15",
  },
  ia: {
    card: "border-ia-borde bg-[#f2fafd]",
    sub: "text-muted-foreground",
    valor: "text-azul-profundo",
    mejora: "text-celeste-ink",
    empeora: "text-alerta",
    borde: "",
  },
  normal: { card: "", sub: "text-muted-foreground", valor: "", mejora: "text-celeste-ink", empeora: "text-alerta", borde: "" },
};

export function TarjetaKpi({ k }: { k: Kpi }) {
  const delta = variacion(k);
  const v = VARIANTE[k.id] ?? "normal";
  const e = ESTILO[v];
  return (
    <Card size="sm" className={cn("gap-0", e.card)} data-testid={`kpi-${k.id}`}>
      <CardContent className="flex-1 gap-0">
        {FAMILIA[k.id] && (
          <div
            className={cn(
              "mb-1.5 text-[10px] font-bold tracking-[0.14em] uppercase",
              v === "ia" ? "text-azul-profundo" : e.sub,
            )}
          >
            {FAMILIA[k.id]}
          </div>
        )}
        <div className="flex items-start justify-between gap-2">
          <h3 className={cn("font-sans text-sm leading-snug", e.sub)}>{k.nombre}</h3>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className={cn("-m-1 rounded-md p-1 opacity-70 hover:opacity-100", e.sub)}
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
        <div className={cn("mt-2 font-heading text-3xl font-bold tracking-tight tabular-nums", e.valor)}>
          {k.valor === null ? <span className={e.sub}>—</span> : valorKpi(k.valor, k.unidad, k.id)}
        </div>
        <p className={cn("mt-1 mb-3 min-h-5 text-[13px]", e.sub)}>
          {k.valor === null ? "Sin datos en el período" : k.detalle}
        </p>
        {delta && (
          <p
            className={cn(
              "-mt-3 mb-3 text-[13px] font-medium",
              delta.mejora === true && e.mejora,
              delta.mejora === false && e.empeora,
              delta.mejora === null && e.sub,
            )}
          >
            {delta.texto}
          </p>
        )}
        <div className={cn("mt-auto flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5 border-t pt-3 text-xs", e.sub, e.borde)}>
          {k.meta ? (
            <span className={cn(k.meta.cumple === true && cn("font-medium", e.mejora), k.meta.cumple === false && e.empeora)}>
              Meta {k.meta.texto}
              {k.meta.cumple === true && " · cumple"}
              {k.meta.cumple === false && " · no cumple"}
            </span>
          ) : (
            <span>Meta a definir</span>
          )}
          {k.ejemplo && (
            <Etiqueta tono="ejemplo" title="Incluye datos del histórico de ejemplo">
              Datos de ejemplo
            </Etiqueta>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
