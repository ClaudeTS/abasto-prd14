// esperando_confirmacion: lo que el agente va a cotizar. Cantidad editable, dudas como preguntas (RF-01).
import { useState } from "react";
import { CheckIcon, PackageIcon, Trash2Icon, Undo2Icon, UserIcon, XIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { fechaCorta, pesos } from "@/lib/format";
import { mensajeError } from "@/lib/errores";
import { Etiqueta } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { PreguntaAgente, sufijoUnidad } from "./comunes";
import type { CorridaAgente, LineaPropuesta } from "./types";

interface Edicion {
  cantidad: string;
  sacada: boolean;
  /** Dudas que se respondieron con "Está bien así" (por texto). */
  ok: string[];
  /** Se tocó la cantidad: cuenta como respuesta a la duda de la línea. */
  editada: boolean;
}

const esFaltaCantidad = (d: string) => /^falta la cantidad/i.test(d);

function inicial(l: LineaPropuesta): Edicion {
  return { cantidad: l.cantidad > 0 ? String(l.cantidad) : "", sacada: false, ok: [], editada: false };
}

function leerCantidad(s: string): number {
  const n = Number(s.replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

/** Dudas de la línea que siguen sin respuesta. */
function pendientes(l: LineaPropuesta, e: Edicion): string[] {
  if (e.sacada) return [];
  const cantidad = leerCantidad(e.cantidad);
  const sinCantidad = cantidad <= 0 ? [`Falta la cantidad de ${l.nombre_corto}.`] : [];
  const resto = l.dudas.filter((d) => !esFaltaCantidad(d) && !e.editada && !e.ok.includes(d));
  return [...sinCantidad, ...resto];
}

export default function Propuesta({
  corrida,
  onConfirmar,
  onCancelar,
  cancelando,
}: {
  corrida: CorridaAgente;
  onConfirmar: (lineas?: { producto_id: string; cantidad: number }[]) => Promise<void>;
  onCancelar: () => void;
  cancelando: boolean;
}) {
  const [ed, setEd] = useState<Record<string, Edicion>>(() =>
    Object.fromEntries(corrida.propuesta.map((l) => [l.producto_id, inicial(l)])),
  );
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const edicion = (l: LineaPropuesta) => ed[l.producto_id] ?? inicial(l);
  const cambiar = (id: string, cambio: Partial<Edicion>) =>
    setEd((prev) => ({ ...prev, [id]: { ...(prev[id] ?? inicial(corrida.propuesta.find((l) => l.producto_id === id)!)), ...cambio } }));

  const faltan = corrida.propuesta.reduce((n, l) => n + pendientes(l, edicion(l)).length, 0);
  const quedan = corrida.propuesta.filter((l) => !edicion(l).sacada);
  const huboCambios = corrida.propuesta.some((l) => {
    const e = edicion(l);
    return e.sacada || leerCantidad(e.cantidad) !== l.cantidad;
  });
  const pedidas = corrida.propuesta.filter((l) => l.origen === "pedido").length;
  const repos = corrida.propuesta.length - pedidas;

  const confirmar = async () => {
    setEnviando(true);
    setError(null);
    try {
      await onConfirmar(
        huboCambios
          ? quedan.map((l) => ({ producto_id: l.producto_id, cantidad: leerCantidad(edicion(l).cantidad) }))
          : undefined,
      );
    } catch (e) {
      setError(mensajeError(e));
      setEnviando(false);
    }
  };

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle className="text-lg">Esto es lo que voy a cotizar</CardTitle>
        <CardDescription>
          {pedidas > 0 && `${pedidas} ${pedidas === 1 ? "producto lo pediste" : "productos los pediste"}`}
          {pedidas > 0 && repos > 0 && " y "}
          {repos > 0 &&
            `${repos} ${pedidas === 0 ? (repos === 1 ? "producto " : "productos ") : ""}${repos === 1 ? "es reposición" : "son reposición"} según el inventario`}
          . Cambiá cantidades o sacá lo que no va; las fechas salen del pedido y del plazo mínimo de entrega.
        </CardDescription>
        <CardAction>
          {faltan > 0 ? (
            <Etiqueta tono="ambar">Datos incompletos</Etiqueta>
          ) : (
            <Etiqueta tono="neutro">Lista para cotizar</Etiqueta>
          )}
        </CardAction>
      </CardHeader>

      <CardContent className="gap-0 px-0">
        <div
          className="hidden grid-cols-[minmax(0,1fr)_9rem_5.5rem_2.25rem] gap-4 border-b px-6 pb-2 text-xs font-medium text-muted-foreground md:grid"
          aria-hidden
        >
          <span>Producto y por qué</span>
          <span>Cantidad</span>
          <span>Para el</span>
          <span />
        </div>
        <ul>
          {corrida.propuesta.map((l) => {
            const e = edicion(l);
            const sinResponder = pendientes(l, e);
            const cantidad = leerCantidad(e.cantidad);
            return (
              <li
                key={l.producto_id}
                className={cn(
                  "border-b px-6 py-4 last:border-b-0",
                  e.sacada && "bg-muted/30",
                  sinResponder.length > 0 && "bg-amber-50/40 dark:bg-amber-950/10",
                )}
              >
                <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-3 md:grid-cols-[minmax(0,1fr)_9rem_5.5rem_2.25rem]">
                  <div className={cn("min-w-0 space-y-1.5", e.sacada && "opacity-50")}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={cn("font-medium", e.sacada && "line-through")}>{l.nombre}</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {l.origen === "pedido" ? (
                        <Etiqueta tono="azul">
                          <UserIcon /> Lo pediste
                        </Etiqueta>
                      ) : (
                        <Etiqueta>
                          <PackageIcon /> Reposición
                        </Etiqueta>
                      )}
                      <Etiqueta
                        tono={l.modo === "automatico" ? "verde" : "neutro"}
                        title="Según el modo del producto, la orden sale sola o espera tu OK"
                      >
                        {l.modo === "automatico"
                          ? l.tope_automatico_uyu !== null
                            ? `Automático hasta ${pesos(l.tope_automatico_uyu)}`
                            : "Automático sin tope"
                          : "Manual"}
                      </Etiqueta>
                    </div>
                    <p className="text-sm leading-snug text-pretty text-muted-foreground">{l.evidencia}</p>
                  </div>

                  <div className="row-span-1 flex items-start justify-end md:hidden">
                    <BotonSacar sacada={e.sacada} onClick={() => cambiar(l.producto_id, { sacada: !e.sacada })} />
                  </div>

                  <div className={cn("flex items-center gap-2 self-start", e.sacada && "opacity-50")}>
                    <label className="sr-only" htmlFor={`cant-${l.producto_id}`}>
                      Cantidad de {l.nombre_corto}
                    </label>
                    <input
                      id={`cant-${l.producto_id}`}
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="any"
                      value={e.cantidad}
                      disabled={e.sacada || enviando}
                      onChange={(ev) => cambiar(l.producto_id, { cantidad: ev.target.value, editada: true })}
                      aria-invalid={!e.sacada && cantidad <= 0}
                      placeholder="¿Cuántos?"
                      className="h-9 w-24 rounded-md border border-input bg-transparent px-2.5 text-right text-sm tabular-nums shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-amber-500 aria-invalid:ring-amber-500/20 disabled:opacity-60 dark:bg-input/30"
                    />
                    <span className="text-sm text-muted-foreground">{sufijoUnidad(l.unidad)}</span>
                  </div>

                  <div className={cn("flex items-center self-start text-sm tabular-nums md:h-9", e.sacada && "opacity-50")}>
                    <span className="mr-1 text-muted-foreground md:hidden">Para el</span>
                    {fechaCorta(l.necesario_para)}
                  </div>

                  <div className="hidden items-start justify-end md:flex">
                    <BotonSacar sacada={e.sacada} onClick={() => cambiar(l.producto_id, { sacada: !e.sacada })} />
                  </div>
                </div>

                {l.dudas.length > 0 && !e.sacada && (
                  <div className="mt-3 space-y-2">
                    {l.dudas.map((d) => {
                      const abierta = sinResponder.includes(d) || (esFaltaCantidad(d) && cantidad <= 0);
                      return (
                        <PreguntaAgente
                          key={d}
                          resuelta={!abierta}
                          acciones={
                            abierta &&
                            (esFaltaCantidad(d) ? (
                              <span className="text-xs">Cargá la cantidad o sacá la línea.</span>
                            ) : (
                              <>
                                <Button
                                  size="xs"
                                  variant="outline"
                                  onClick={() => cambiar(l.producto_id, { ok: [...e.ok, d] })}
                                >
                                  <CheckIcon /> Está bien así
                                </Button>
                                <span className="text-xs">o cambiá la cantidad.</span>
                              </>
                            ))
                          }
                        >
                          {d}
                        </PreguntaAgente>
                      );
                    })}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </CardContent>

      <div className="flex flex-col gap-3 border-t px-6 pt-4 sm:flex-row sm:items-center">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {quedan.length === 0
            ? "Sacaste todo: si confirmás, no hay nada que comprar."
            : faltan > 0
              ? `Me ${faltan === 1 ? "falta 1 dato" : `faltan ${faltan} datos`} para seguir.`
              : huboCambios
                ? `Cotizo ${quedan.length} ${quedan.length === 1 ? "producto" : "productos"} con tus cambios.`
                : `Cotizo ${quedan.length} ${quedan.length === 1 ? "producto" : "productos"} a los 6 proveedores.`}
        </p>
        <div className="flex flex-col-reverse gap-2 sm:ml-auto sm:flex-row">
          <Button variant="outline" onClick={onCancelar} disabled={enviando || cancelando}>
            {cancelando ? <Spinner /> : <XIcon />} Cancelar
          </Button>
          <Button size="lg" onClick={confirmar} disabled={enviando || cancelando || faltan > 0 || quedan.length === 0}>
            {enviando ? <Spinner /> : <CheckIcon />} Confirmar y pedir cotizaciones
          </Button>
        </div>
      </div>
      {error && <p className="px-6 text-sm text-destructive">{error}</p>}
    </Card>
  );
}

function BotonSacar({ sacada, onClick }: { sacada: boolean; onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={onClick}
      aria-label={sacada ? "Volver a agregar" : "Sacar de la compra"}
      title={sacada ? "Volver a agregar" : "Sacar de la compra"}
    >
      {sacada ? <Undo2Icon /> : <Trash2Icon />}
    </Button>
  );
}
