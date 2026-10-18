// Órdenes de compra del agente (RF-03): cuáles salieron solas, con el motivo de cada línea, y cuáles
// esperan el OK de quien compra, con sus motivos y Aprobar / Rechazar.
import { useEffect, useState, type ReactNode } from "react";
import {
  BotIcon,
  CheckIcon,
  ChevronDownIcon,
  CircleAlertIcon,
  HandshakeIcon,
  MessageSquareIcon,
  UserCheckIcon,
  XIcon,
} from "lucide-react";
import * as api from "@/api";
import { cn } from "@/lib/utils";
import { hora, pesos, porcentaje, precioUnitario } from "@/lib/format";
import { mensajeError } from "@/lib/errores";
import { Avatar, Etiqueta, Evidencia } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import type { Negociacion, NombreEstrategia } from "@/types";
import * as agenteApi from "./api";
import { cantidadConUnidad } from "./comunes";
import type { LineaOrden, OrdenCompra } from "./types";

const ESTRATEGIAS: Record<NombreEstrategia, string> = {
  competencia: "Competencia",
  volumen: "Volumen",
  plazo: "Plazo",
};

function EstadoOrden({ o }: { o: OrdenCompra }) {
  if (o.estado === "esperando_aprobacion") return <Etiqueta tono="ambar">Espera tu OK</Etiqueta>;
  if (o.estado === "rechazada") return <Etiqueta tono="rojo">Rechazada</Etiqueta>;
  if (o.aprobada_por === "agente")
    return (
      <Etiqueta tono="verde">
        <BotIcon /> La mandó el agente
      </Etiqueta>
    );
  return (
    <Etiqueta tono="azul">
      <UserCheckIcon /> La aprobaste
    </Etiqueta>
  );
}

function MotivoLinea({ l }: { l: LineaOrden }) {
  const tono =
    l.aprobacion === "automatica"
      ? "text-emerald-700 dark:text-emerald-400"
      : l.aprobacion === "supera_tope"
        ? "text-amber-700 dark:text-amber-400"
        : "text-muted-foreground";
  const Icono = l.aprobacion === "automatica" ? BotIcon : l.aprobacion === "supera_tope" ? CircleAlertIcon : UserCheckIcon;
  return (
    <p className={cn("flex items-start gap-1.5 text-xs leading-snug", tono)}>
      <Icono className="mt-px size-3.5 shrink-0" aria-hidden />
      {l.motivo}
    </p>
  );
}

function Plegable({ titulo, icono, children }: { titulo: string; icono: ReactNode; children: ReactNode }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setAbierto(!abierto)}
        aria-expanded={abierto}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        {icono}
        {titulo}
        <ChevronDownIcon className={cn("size-3.5 transition-transform", abierto && "rotate-180")} />
      </button>
      {abierto && <div className="mt-2">{children}</div>}
    </div>
  );
}

function PanelNegociacion({ negociacionId }: { negociacionId: string }) {
  const [neg, setNeg] = useState<Negociacion | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [aprobando, setAprobando] = useState(false);

  useEffect(() => {
    let vivo = true;
    agenteApi
      .getNegociacion(negociacionId)
      .then((n) => {
        if (!vivo) return;
        setNeg(n);
        setMensaje(n.mensaje_propuesto);
      })
      .catch((e) => vivo && setError(mensajeError(e)));
    return () => {
      vivo = false;
    };
  }, [negociacionId]);

  if (error && !neg) return <p className="text-sm text-muted-foreground">No pude traer la negociación ({error}).</p>;
  if (!neg)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner /> Cargando la negociación…
      </p>
    );

  const elegida = neg.estrategias.find((s) => s.nombre === neg.elegida);
  const aprobada = neg.estado !== "simulada";

  const aprobar = async () => {
    setAprobando(true);
    setError(null);
    try {
      const n = await api.aprobar(neg.id, mensaje);
      setNeg(n);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setAprobando(false);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <HandshakeIcon className="size-4 text-muted-foreground" aria-hidden />
        <span className="text-sm font-medium">Negociación ensayada con el gemelo</span>
        {aprobada ? <Etiqueta tono="verde">Mensaje aprobado</Etiqueta> : <Etiqueta tono="ambar">Para aprobar</Etiqueta>}
      </div>
      {elegida && (
        <p className="text-sm text-muted-foreground">
          Conviene <span className="font-medium text-foreground">«{ESTRATEGIAS[elegida.nombre]}»</span>:{" "}
          {porcentaje(-elegida.concesion_obtenida_pct)}, unos {pesos(elegida.ganancia_esperada_uyu)} (riesgo{" "}
          {elegida.riesgo}). Es independiente de aprobar la orden.
        </p>
      )}
      <Plegable titulo="Ver las estrategias que probé" icono={null}>
        <ul className="space-y-1.5 text-sm">
          {neg.estrategias.map((s) => (
            <li key={s.nombre} className="flex flex-wrap items-baseline gap-x-2">
              <span className={cn("font-medium", s.nombre === neg.elegida && "underline underline-offset-4")}>
                {ESTRATEGIAS[s.nombre]}
              </span>
              <span className="text-muted-foreground tabular-nums">
                {porcentaje(-s.concesion_obtenida_pct)} · {pesos(s.ganancia_esperada_uyu)} · riesgo {s.riesgo}
              </span>
              {s.descripcion && <span className="w-full text-xs text-muted-foreground">{s.descripcion}</span>}
            </li>
          ))}
        </ul>
      </Plegable>
      <label className="block space-y-1.5">
        <span className="text-xs font-medium text-muted-foreground">Mensaje propuesto al proveedor</span>
        <Textarea
          value={mensaje}
          onChange={(e) => setMensaje(e.target.value)}
          disabled={aprobada || aprobando}
          className="min-h-20 bg-background"
        />
      </label>
      {!aprobada && (
        <Button size="sm" variant="outline" onClick={aprobar} disabled={aprobando || !mensaje.trim()}>
          {aprobando ? <Spinner /> : <MessageSquareIcon />} Aprobar mensaje
        </Button>
      )}
      {aprobada && <p className="text-xs text-muted-foreground">Enviado (simulado). Nada sale de verdad en la demo.</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

function TarjetaOrden({
  o,
  onAprobar,
  onRechazar,
}: {
  o: OrdenCompra;
  onAprobar: (o: OrdenCompra) => Promise<void>;
  onRechazar: (o: OrdenCompra) => Promise<void>;
}) {
  const [accion, setAccion] = useState<"aprobar" | "rechazar" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const espera = o.estado === "esperando_aprobacion";

  const correr = async (que: "aprobar" | "rechazar") => {
    if (que === "rechazar" && !window.confirm(`¿Rechazar la orden ${o.numero} a ${o.proveedor_nombre}?`)) return;
    setAccion(que);
    setError(null);
    try {
      await (que === "aprobar" ? onAprobar(o) : onRechazar(o));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setAccion(null);
    }
  };

  return (
    <Card
      className={cn(
        espera && "ring-amber-300 dark:ring-amber-800",
        o.estado === "rechazada" && "opacity-70",
      )}
    >
      <CardHeader className="border-b">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar proveedorId={o.proveedor_id} />
          <div className="min-w-0">
            <CardTitle className="truncate">{o.proveedor_nombre}</CardTitle>
            <CardDescription className="tabular-nums">
              {o.numero} · {pesos(o.total_sin_iva)} + IVA
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <EstadoOrden o={o} />
        </CardAction>
      </CardHeader>

      <CardContent className="gap-4">
        <ul className="divide-y">
          {o.lineas.map((l) => (
            <li key={l.producto_id} className="space-y-1.5 py-3 first:pt-0">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <span className="font-medium">
                  {cantidadConUnidad(l.cantidad, l.unidad)} · {l.nombre}
                </span>
                <span className="text-sm tabular-nums">
                  <span className="text-muted-foreground">
                    {precioUnitario(l.precio_unitario_sin_iva)} {l.unidad === "l" ? "el litro" : "c/u"} ={" "}
                  </span>
                  <span className="font-medium">{pesos(l.subtotal)}</span>
                </span>
              </div>
              <MotivoLinea l={l} />
              {l.evidencia && <Evidencia texto={l.evidencia} className="text-xs" />}
            </li>
          ))}
        </ul>

        <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-t pt-3 text-sm tabular-nums">
          {o.envio > 0 && (
            <>
              <dt className="text-muted-foreground">Envío</dt>
              <dd className="text-right">{pesos(o.envio)}</dd>
            </>
          )}
          <dt className="text-muted-foreground">Total sin IVA</dt>
          <dd className="text-right font-medium">{pesos(o.total_sin_iva)}</dd>
          <dt className="text-muted-foreground">Con IVA (22 %)</dt>
          <dd className="text-right">{pesos(o.total_con_iva)}</dd>
        </dl>

        {espera && o.motivos.length > 0 && (
          <div className="rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-950 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-100 dark:ring-amber-900">
            <p className="mb-1 font-medium">Por qué espera tu OK</p>
            <ul className="list-disc space-y-0.5 pl-4">
              {o.motivos.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        )}

        {o.negociacion_id && <PanelNegociacion negociacionId={o.negociacion_id} />}

        <Plegable
          titulo={
            espera
              ? "Ver el mensaje que le voy a mandar"
              : o.estado === "enviada_simulada"
                ? `Ver el mensaje enviado${o.enviada_en ? ` a las ${hora(o.enviada_en)}` : ""} (simulado)`
                : "Ver el mensaje"
          }
          icono={<MessageSquareIcon className="size-3.5" />}
        >
          <p className="max-w-prose rounded-xl rounded-tr-sm bg-emerald-50 px-3 py-2 text-sm whitespace-pre-line text-emerald-950 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-50 dark:ring-emerald-900">
            {o.mensaje}
          </p>
        </Plegable>

        {espera && (
          <div className="flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => correr("rechazar")} disabled={!!accion}>
              {accion === "rechazar" ? <Spinner /> : <XIcon />} Rechazar
            </Button>
            <Button onClick={() => correr("aprobar")} disabled={!!accion}>
              {accion === "aprobar" ? <Spinner /> : <CheckIcon />} Aprobar y mandar
            </Button>
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

export default function Ordenes({
  ordenes,
  onAprobar,
  onRechazar,
}: {
  ordenes: OrdenCompra[];
  onAprobar: (o: OrdenCompra) => Promise<void>;
  onRechazar: (o: OrdenCompra) => Promise<void>;
}) {
  const grupos: { clave: string; titulo: string; bajada: string; ordenes: OrdenCompra[] }[] = [
    {
      clave: "esperan",
      titulo: "Esperan tu OK",
      bajada: "Tienen algo en modo manual o superan el tope automático.",
      ordenes: ordenes.filter((o) => o.estado === "esperando_aprobacion"),
    },
    {
      clave: "solas",
      titulo: "Salieron solas",
      bajada: "Todo en modo automático y dentro del tope: el agente las mandó sin preguntarte.",
      ordenes: ordenes.filter((o) => o.estado === "enviada_simulada" && o.aprobada_por === "agente"),
    },
    {
      clave: "aprobadas",
      titulo: "Las aprobaste vos",
      bajada: "",
      ordenes: ordenes.filter((o) => o.estado === "enviada_simulada" && o.aprobada_por !== "agente"),
    },
    {
      clave: "rechazadas",
      titulo: "Rechazadas",
      bajada: "",
      ordenes: ordenes.filter((o) => o.estado === "rechazada"),
    },
  ];
  const solas = grupos[1].ordenes.length;
  const esperan = grupos[0].ordenes.length;

  return (
    <section className="space-y-6" aria-label="Órdenes de compra">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Órdenes de compra</h2>
        <Etiqueta tono="verde">
          <BotIcon /> {solas} {solas === 1 ? "salió sola" : "salieron solas"}
        </Etiqueta>
        {esperan > 0 && (
          <Etiqueta tono="ambar">
            {esperan} {esperan === 1 ? "espera" : "esperan"} tu OK
          </Etiqueta>
        )}
      </div>
      {grupos
        .filter((g) => g.ordenes.length > 0)
        .map((g) => (
          <div key={g.clave} className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold">{g.titulo}</h3>
              {g.bajada && <p className="text-sm text-muted-foreground">{g.bajada}</p>}
            </div>
            <div className="grid gap-4">
              {g.ordenes.map((o) => (
                <TarjetaOrden key={o.id} o={o} onAprobar={onAprobar} onRechazar={onRechazar} />
              ))}
            </div>
          </div>
        ))}
    </section>
  );
}
