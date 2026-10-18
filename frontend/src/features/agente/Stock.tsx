// Stock en depósito: cada salida baja 1. Si un producto llega a su mínimo, el agente arranca solo la compra
// (PRD 1.4 RF-03) y la pantalla pasa a mostrarla.
import { useCallback, useEffect, useState } from "react";
import { MinusIcon, PackageIcon } from "lucide-react";
import { mensajeError } from "@/lib/errores";
import { cn } from "@/lib/utils";
import { ErrorBanner, Etiqueta } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import * as agenteApi from "./api";
import type { ItemStock } from "./api";
import type { CorridaAgente } from "./types";

const unidad = (i: ItemStock) => (i.unidad === "l" ? "L" : i.unidad === "kg" ? "kg" : "u.");

function Fila({ i, ocupado, onConsumir }: { i: ItemStock; ocupado: boolean; onConsumir: () => void }) {
  const bajo = i.stock_actual <= i.stock_minimo;
  const escala = Math.max(i.stock_minimo * 2, i.stock_actual, 1);
  const pct = (v: number) => `${Math.min(100, (v / escala) * 100)}%`;
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 py-3 first:pt-0 last:pb-0">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="truncate font-medium">{i.nombre}</span>
        <Etiqueta tono={i.modo === "automatico" ? "azul" : "neutro"}>{i.modo === "automatico" ? "Automático" : "Manual"}</Etiqueta>
        {bajo && <Etiqueta tono="ambar">En el mínimo</Etiqueta>}
      </div>
      <Button size="sm" variant="outline" onClick={onConsumir} disabled={ocupado} aria-label={`Sacar 1 de ${i.nombre}`}>
        {ocupado ? <Spinner /> : <MinusIcon />} 1
      </Button>
      <div className="col-span-2 flex items-center gap-3">
        {/* Barra del stock con la línea del mínimo */}
        <div className="relative h-2.5 flex-1 rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full transition-all", bajo ? "bg-amber-500" : "bg-celeste")}
            style={{ width: pct(i.stock_actual) }}
          />
          <div
            className="absolute -top-1 -bottom-1 w-0.5 bg-grafito"
            style={{ left: pct(i.stock_minimo) }}
            title={`Mínimo: ${i.stock_minimo}`}
          />
        </div>
        <span className="w-36 shrink-0 text-right text-sm text-muted-foreground tabular-nums">
          <span className="font-semibold text-foreground">{i.stock_actual}</span> {unidad(i)} · mín. {i.stock_minimo}
        </span>
      </div>
    </li>
  );
}

export default function Stock({ onArranco }: { onArranco: (c: CorridaAgente, aviso: string | null) => void }) {
  const [items, setItems] = useState<ItemStock[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setItems((await agenteApi.inventario()).filter((i) => i.tipo === "consumible"));
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const consumir = async (i: ItemStock) => {
    setOcupado(i.producto_id);
    setAviso(null);
    try {
      const r = await agenteApi.consumir(i.producto_id);
      setItems((prev) => prev?.map((p) => (p.producto_id === r.item.producto_id ? r.item : p)) ?? prev);
      if (r.corrida) onArranco(r.corrida, r.aviso);
      else setAviso(r.aviso);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setOcupado(null);
    }
  };

  return (
    <Card aria-label="Stock en depósito">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PackageIcon className="size-4" aria-hidden /> Stock en depósito
        </CardTitle>
        <CardDescription>
          Cada salida baja 1. Cuando un producto llega a su mínimo, el agente arranca solo la compra: calcula la
          reposición con el histórico y la estacionalidad, cotiza y llama al proveedor que no responde.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <ErrorBanner mensaje={error} onReintentar={cargar} />}
        {aviso && <p className="text-sm text-accion">{aviso}</p>}
        {!items ? (
          !error && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner /> Leyendo el inventario…
            </div>
          )
        ) : (
          <ul className="divide-y">
            {items.map((i) => (
              <Fila key={i.producto_id} i={i} ocupado={ocupado === i.producto_id} onConsumir={() => consumir(i)} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
