import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Etiqueta } from "@/components/comunes";
import { duracion, NOMBRE_CANAL } from "./formato";
import type { Pendiente, TiempoCanal } from "./types";

export function PanelPendientes({ pendientes }: { pendientes: Pendiente[] }) {
  return (
    <Card size="sm" aria-label="Pendientes de aprobación">
      <CardHeader>
        <CardTitle>Pendientes de aprobación</CardTitle>
        <CardDescription>Sin compra automática, por encima del tope o con una negociación para aprobar</CardDescription>
        <CardAction>
          <Etiqueta tono={pendientes.length ? "ambar" : "neutro"}>{pendientes.length}</Etiqueta>
        </CardAction>
      </CardHeader>
      <CardContent>
        {pendientes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay nada esperando tu aprobación.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {pendientes.map((p, i) => (
              <li key={p.id} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-medium text-pretty">{p.titulo}</div>
                  <p className="text-[13px] text-pretty text-muted-foreground">{p.detalle}</p>
                </div>
                <Button asChild size="sm" variant={i === 0 ? "default" : "outline"}>
                  <Link to={p.enlace}>Revisar</Link>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function PanelTiempoPorCanal({ canales, dias }: { canales: TiempoCanal[]; dias: number }) {
  const conDatos = canales.filter((c) => c.minutos !== null);
  const maximo = Math.max(...conDatos.map((c) => c.minutos ?? 0), 1);
  const ejemplo = canales.some((c) => c.ejemplo);
  return (
    <Card size="sm" aria-label="Tiempo de respuesta por canal">
      <CardHeader>
        <CardTitle>Tiempo de respuesta por canal</CardTitle>
        <CardDescription>Promedio de los proveedores, últimos {dias} días</CardDescription>
        {ejemplo && (
          <CardAction>
            <Etiqueta tono="ambar">Datos de ejemplo</Etiqueta>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="gap-4">
        {conDatos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin respuestas medidas en el período.</p>
        ) : (
          canales.map((c) => (
            <div key={c.canal}>
              <div className="flex items-center justify-between gap-2 text-sm">
                <span>{NOMBRE_CANAL[c.canal]}</span>
                <span className="text-muted-foreground tabular-nums">
                  {c.minutos === null ? "sin datos" : duracion(c.minutos)}
                  {c.muestras > 0 && (
                    <span className="ml-1 text-xs">
                      ({c.muestras} {c.muestras === 1 ? "respuesta" : "respuestas"})
                    </span>
                  )}
                </span>
              </div>
              <Progress
                className="mt-1.5"
                value={c.minutos === null ? 0 : Math.max(3, (c.minutos / maximo) * 100)}
                aria-label={`${NOMBRE_CANAL[c.canal]}: ${c.minutos === null ? "sin datos" : duracion(c.minutos)}`}
              />
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
