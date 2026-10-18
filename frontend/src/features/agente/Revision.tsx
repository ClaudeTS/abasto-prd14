// esperando_revision: una tarjeta por cotización dudosa. Se resuelve con el endpoint de siempre
// (POST /cotizaciones/{id}/confirmar); el agente lo ve en el próximo polling y sigue solo.
import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRightIcon, CheckIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { Avatar, Etiqueta } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { PreguntaAgente } from "./comunes";
import type { RevisionPendiente } from "./types";

type Respuesta = "con_iva" | "sin_iva" | "ok";

function TarjetaRevision({ r }: { r: RevisionPendiente }) {
  const [enviando, setEnviando] = useState<Respuesta | null>(null);
  const [lista, setLista] = useState<Respuesta | null>(null);
  const [error, setError] = useState<string | null>(null);

  const responder = async (resp: Respuesta) => {
    setEnviando(resp);
    setError(null);
    try {
      if (resp === "ok") await api.confirmarLectura(r.cotizacion_id);
      else await api.confirmarCampo(r.cotizacion_id, "iva", resp === "con_iva");
      setLista(resp);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setEnviando(null);
    }
  };

  const textoListo =
    lista === "con_iva" ? "Incluyen IVA" : lista === "sin_iva" ? "Son + IVA" : lista === "ok" ? "Está bien así" : "";

  return (
    <Card size="sm">
      <CardHeader>
        <div className="flex items-center gap-3">
          <Avatar proveedorId={r.proveedor_id} className="size-8 text-[10px]" />
          <div className="min-w-0">
            <CardTitle>{r.proveedor_nombre}</CardTitle>
            <CardDescription>
              Dudoso:{" "}
              {r.campos_dudosos.length
                ? r.campos_dudosos.map((c) => (c === "iva" ? "el IVA" : c.replace(/_/g, " "))).join(", ")
                : "la lectura"}
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Link
            to="/cotizaciones"
            className="inline-flex items-center gap-0.5 text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            Ver la cotización <ArrowUpRightIcon className="size-3" />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        <PreguntaAgente
          resuelta={!!lista}
          acciones={
            lista ? (
              <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <CheckIcon className="size-3.5" /> {textoListo}. Sigo con el plan
                <Spinner className="size-3" />
              </span>
            ) : r.pide_iva ? (
              <>
                <Button size="sm" onClick={() => responder("con_iva")} disabled={!!enviando}>
                  {enviando === "con_iva" && <Spinner />} Incluyen IVA
                </Button>
                <Button size="sm" variant="outline" onClick={() => responder("sin_iva")} disabled={!!enviando}>
                  {enviando === "sin_iva" && <Spinner />} Son + IVA
                </Button>
              </>
            ) : (
              <Button size="sm" onClick={() => responder("ok")} disabled={!!enviando}>
                {enviando === "ok" ? <Spinner /> : <CheckIcon />} Está bien así
              </Button>
            )
          }
        >
          {r.pregunta}
        </PreguntaAgente>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

export default function Revision({ revision }: { revision: RevisionPendiente[] }) {
  return (
    <section className="space-y-3" aria-label="Respuestas para revisar">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Necesito que me confirmes algo</h2>
        <Etiqueta tono="ambar">Te espera</Etiqueta>
      </div>
      <p className="text-sm text-muted-foreground">
        Antes de armar el plan: hay {revision.length === 1 ? "una respuesta" : `${revision.length} respuestas`} que no
        quedó clara. Con tu respuesta sigo solo.
      </p>
      {revision.map((r) => (
        <TarjetaRevision key={r.cotizacion_id} r={r} />
      ))}
    </section>
  );
}
