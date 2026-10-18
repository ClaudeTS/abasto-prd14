// Las llamadas que hizo el agente (`llamada_ids`), con el PanelLlamada de siempre (GET /llamadas/{id}).
import { useEffect, useState } from "react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import PanelLlamada, { ModoLlamadas, useConfigLlamadas, useLlamada } from "@/components/PanelLlamada";
import type { Llamada } from "@/types";

function UnaLlamada({ id, pedidoId }: { id: string; pedidoId: string }) {
  const [proveedorId, setProveedorId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Reintentar desde el panel vuelve a llamar al mismo proveedor (la llamada de cotización de siempre).
  const tel = useLlamada(`agente_llamada_${id}`, (simulada) =>
    api.llamarParaCotizar(pedidoId, proveedorId ?? "", simulada),
  );
  const { setLlamada } = tel;

  useEffect(() => {
    let vivo = true;
    api
      .getLlamada(id)
      .then((l: Llamada) => {
        if (!vivo) return;
        setProveedorId(l.proveedor_id);
        setLlamada(l); // desde acá, useLlamada la sigue mientras esté activa
      })
      .catch((e) => vivo && setError(mensajeError(e)));
    return () => {
      vivo = false;
    };
  }, [id, setLlamada]);

  if (error && !proveedorId) return <p className="text-sm text-muted-foreground">No pude traer la llamada ({error}).</p>;
  if (!proveedorId) return null;
  return <PanelLlamada proveedorId={proveedorId} tel={tel} compacto />;
}

export default function Llamadas({ ids, pedidoId }: { ids: string[]; pedidoId: string }) {
  const config = useConfigLlamadas();
  if (ids.length === 0) return null;
  return (
    <section className="space-y-3" aria-label="Llamadas del agente">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">
          {ids.length === 1 ? "Llamé al que no respondía" : "Llamé a los que no respondían"}
        </h2>
        <ModoLlamadas config={config} />
      </div>
      {ids.map((id) => (
        <UnaLlamada key={id} id={id} pedidoId={pedidoId} />
      ))}
    </section>
  );
}
