// RF-16 (§11.5): cada estrategia ensayada contra el resto de los proveedores en precio, entrega,
// pago y garantía, con el riesgo de la regla de los 15 días. Reutilizable:
// <EvaluacionNegociacion negociacionId="neg_…" />
import { useCallback, useEffect, useState } from "react";
import { ScaleIcon } from "lucide-react";
import { mensajeError } from "@/lib/errores";
import { formatNumero, pesos, precioUnitario } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ErrorBanner, Etiqueta, type Tono } from "@/components/comunes";
import * as api from "./api";
import { DatosEjemplo, dias, garantia, pago } from "./comunes";
import type { Dimension, Evaluacion, EvaluacionEstrategia, ResultadoDim } from "./types";

const TITULO: Record<string, string> = { competencia: "Competencia", volumen: "Volumen", plazo: "Plazo de pago" };
const DIMENSIONES: [Dimension, string][] = [
  ["precio", "Precio o bonificación"],
  ["entrega", "Entrega"],
  ["pago", "Pago"],
  ["garantia", "Garantía"],
];
const TONO_RIESGO: Record<string, Tono> = { bajo: "verde", medio: "ambar", alto: "rojo" };
const RESULTADO: Record<ResultadoDim, { texto: string; clase: string }> = {
  mejora: { texto: "mejora", clase: "text-emerald-700 dark:text-emerald-400" },
  iguala: { texto: "iguala", clase: "text-muted-foreground" },
  peor: { texto: "peor", clase: "text-amber-700 dark:text-amber-400" },
  sin_dato: { texto: "s/d", clase: "text-muted-foreground/70" },
};

export default function EvaluacionNegociacion({ negociacionId }: { negociacionId: string }) {
  const [ev, setEv] = useState<Evaluacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setError(null);
      setEv(await api.obtenerEvaluacion(negociacionId));
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [negociacionId]);

  useEffect(() => {
    setEv(null);
    cargar();
  }, [cargar]);

  if (error) return <ErrorBanner mensaje={`No se pudo evaluar la negociación: ${error}`} onReintentar={cargar} />;
  if (!ev) return <Skeleton className="h-72 rounded-xl" />;

  return (
    <Card aria-label="Evaluación contra el resto de los proveedores">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScaleIcon className="size-4" aria-hidden /> Ganancia y riesgo contra el resto de los proveedores
        </CardTitle>
        <CardDescription>
          La oferta resultante de cada estrategia contra las demás cotizaciones elegibles, en precio, entrega, pago y garantía.
        </CardDescription>
        <CardAction>
          <Etiqueta>Riesgo aceptable: entrega hasta +{ev.margen_riesgo_dias} días sobre un proveedor regular</Etiqueta>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 lg:grid-cols-3">
          {ev.estrategias.map((e) => (
            <TarjetaEstrategia key={e.nombre} e={e} ev={ev} />
          ))}
        </div>
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">Ver contra cada proveedor</summary>
          <Comparaciones ev={ev} />
        </details>
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-muted-foreground">
            {ev.regla}
            {ev.referencia_regular && ` Proveedor regular: ${ev.referencia_regular.nombre} (${ev.referencia_regular.criterio}).`}
          </p>
          <DatosEjemplo>La garantía de cada proveedor es ilustrativa en la demo.</DatosEjemplo>
        </div>
      </CardContent>
    </Card>
  );
}

function valor(dim: Dimension, v: number | null): string {
  if (v === null) return "s/d";
  if (dim === "precio") return precioUnitario(v);
  if (dim === "entrega") return dias(v);
  if (dim === "pago") return pago(v);
  return garantia(v);
}

function TarjetaEstrategia({ e, ev }: { e: EvaluacionEstrategia; ev: Evaluacion }) {
  const principal = ev.items[0];
  const pct = e.concesion_obtenida_pct;
  return (
    <div className={cn("flex flex-col gap-3 rounded-xl border p-4", e.recomendada && "border-2 border-primary", !e.ensayada && "opacity-70")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">{TITULO[e.nombre] ?? e.nombre}</h3>
        <div className="flex flex-wrap gap-1">
          {e.recomendada && <Etiqueta className="border-primary bg-primary text-primary-foreground">Recomendada</Etiqueta>}
          <Etiqueta tono={TONO_RIESGO[e.riesgo]}>Riesgo {e.riesgo}</Etiqueta>
        </div>
      </div>
      <div>
        <div className="text-2xl font-semibold tracking-tight tabular-nums">{formatNumero(pct, Number.isInteger(pct) ? 0 : 1)} %</div>
        <div className="text-xs text-muted-foreground">
          concesión · {pesos(e.ganancia_esperada_uyu)}
          {principal && ` en ${formatNumero(principal.cantidad)} u.`}
        </div>
      </div>
      <dl className="flex flex-col text-sm">
        {DIMENSIONES.map(([dim, etiqueta]) => {
          const fila = e.dimensiones[dim];
          const r = RESULTADO[fila.resultado];
          const propio =
            dim === "precio" && fila.propio !== null && pct > 0 ? `${valor(dim, fila.propio)} (−${formatNumero(pct, Number.isInteger(pct) ? 0 : 1)} %)` : valor(dim, fila.propio);
          return (
            <div key={dim} className="flex justify-between gap-3 border-b py-1.5 last:border-0">
              <dt className="text-muted-foreground">{etiqueta}</dt>
              <dd className="flex flex-col items-end text-right">
                <span className="tabular-nums">{propio}</span>
                <span
                  className={cn("text-xs font-medium", r.clase)}
                  title={fila.proveedor ? `Mejor del resto: ${fila.proveedor}` : undefined}
                >
                  {r.texto}
                  {fila.proveedor && fila.resultado !== "sin_dato" && ` · resto ${valor(dim, fila.mejor_del_resto)}`}
                </span>
              </dd>
            </div>
          );
        })}
      </dl>
      <div className="flex flex-col gap-1 text-sm">
        <div className="flex flex-wrap items-center gap-1.5">
          <Etiqueta tono={e.gana ? "verde" : "neutro"}>
            {e.gana ? "Gana" : "No supera a todos"} · {e.supera_a}/{e.elegibles}
          </Etiqueta>
          <Etiqueta tono={e.riesgo_plazo.nivel === "alto" ? "rojo" : e.riesgo_plazo.nivel === "aceptable" ? "ambar" : "neutro"}>
            Plazo {e.riesgo_plazo.nivel === "sin_dato" ? "s/d" : e.riesgo_plazo.nivel}
          </Etiqueta>
        </div>
        <p className="text-muted-foreground">{e.conclusion}</p>
        <p className="text-xs text-muted-foreground">{e.riesgo_plazo.texto}</p>
      </div>
    </div>
  );
}

function Comparaciones({ ev }: { ev: Evaluacion }) {
  const competidores = ev.estrategias[0]?.comparaciones ?? [];
  if (competidores.length === 0)
    return <p className="mt-2 text-muted-foreground">Ningún otro proveedor cotiza estos productos.</p>;
  return (
    <div className="mt-3 overflow-hidden rounded-lg border">
      <Table className="min-w-[720px]">
        <TableHeader>
          <TableRow className="[&>th]:px-3">
            <TableHead>Proveedor</TableHead>
            <TableHead className="text-right">Su total</TableHead>
            <TableHead>Entrega · pago · garantía</TableHead>
            {ev.estrategias.map((e) => (
              <TableHead key={e.nombre}>{TITULO[e.nombre]}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {competidores.map((c) => (
            <TableRow key={c.proveedor_id} className={cn("align-top [&>td]:px-3", !c.elegible && "text-muted-foreground")}>
              <TableCell className="whitespace-normal">
                <div className="font-medium">{c.nombre}</div>
                {!c.elegible && <div className="text-xs">{c.motivo_no_elegible}</div>}
              </TableCell>
              <TableCell className="text-right tabular-nums">{pesos(c.otro_total)}</TableCell>
              <TableCell>
                {dias(c.otro_entrega_dias)} · {pago(c.otro_pago_dias)} · {garantia(c.otro_garantia_meses)}
              </TableCell>
              {ev.estrategias.map((e) => {
                const comp = e.comparaciones.find((x) => x.proveedor_id === c.proveedor_id);
                if (!comp) return <TableCell key={e.nombre}>—</TableCell>;
                return (
                  <TableCell key={e.nombre} className="whitespace-normal">
                    <div className="flex flex-wrap gap-x-2 text-xs">
                      {DIMENSIONES.map(([dim, etiqueta]) => (
                        <span key={dim} className={RESULTADO[comp.resultado[dim]].clase}>
                          {etiqueta.split(" ")[0]}: {RESULTADO[comp.resultado[dim]].texto}
                        </span>
                      ))}
                    </div>
                    {comp.elegible && (
                      <div className={cn("mt-0.5 text-xs font-medium", comp.supera ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground")}>
                        {comp.supera ? "la supera" : "no la supera"}
                      </div>
                    )}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
