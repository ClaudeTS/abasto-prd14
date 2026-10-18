// Conversaciones del pedido (RF-10): cada mensaje con canal, sentido, participante, fecha y hora, y las
// llamadas con su transcripción completa (expandida).
import { useMemo, useState } from "react";
import { ExternalLinkIcon, MessagesSquareIcon } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { cn } from "@/lib/utils";
import { urlArchivo } from "./api";
import {
  CANAL,
  MOTIVO,
  Marca,
  PROPOSITO,
  RESULTADO_LLAMADA,
  diaHora,
  duracion,
  fechaLarga,
  tonoEtiquetaMensaje,
} from "./presentacion";
import type { CanalMensaje, Conversacion, MensajePedido } from "./types";

type Item = { m: MensajePedido; conv: Conversacion };

/** Los textos largos (presupuestos en PDF, solicitudes) se muestran recortados con "Ver todo". */
function TextoLargo({ texto }: { texto: string }) {
  const largo = texto.length > 260 || texto.split("\n").length > 5;
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <p className={cn("text-sm whitespace-pre-line", largo && !abierto && "line-clamp-4")}>{texto}</p>
      {largo && (
        <button
          type="button"
          onClick={() => setAbierto((a) => !a)}
          className="mt-0.5 text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          {abierto ? "Ver menos" : "Ver todo"}
        </button>
      )}
    </>
  );
}

function Llamada({ m }: { m: MensajePedido }) {
  const ll = m.llamada!;
  return (
    <div className="mt-1.5 space-y-2">
      {ll.resumen && <p className="text-sm">{ll.resumen}</p>}
      {m.transcripcion && m.transcripcion.length > 0 && (
        <div
          className="flex flex-col gap-2 rounded-lg border bg-muted/40 px-3.5 py-3"
          aria-label="Transcripción de la llamada"
        >
          {m.transcripcion.map((t, i) => (
            <div key={i}>
              <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                {t.quien}
                {t.segundo != null && (
                  <span className="ml-1.5 font-normal normal-case tabular-nums">{duracion(t.segundo)}</span>
                )}
              </div>
              <p className="text-sm">{t.texto}</p>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        {ll.resultado !== "atendida"
          ? ll.resultado === "en_curso"
            ? "La llamada está en curso: la transcripción se va completando."
            : "Sin conversación: sigue la secuencia de contacto."
          : ll.modo === "simulada"
            ? "Llamada simulada: no hay audio grabado. La transcripción se conserva."
            : ll.audio_disponible_hasta
              ? `Audio disponible hasta el ${fechaLarga(ll.audio_disponible_hasta)} · la transcripción se conserva.`
              : "La transcripción se conserva."}
      </p>
    </div>
  );
}

function Fila({ item, ultimo }: { item: Item; ultimo: boolean }) {
  const { m, conv } = item;
  const { icono: Icono, etiqueta } = CANAL[m.canal];
  const ll = m.llamada;
  const enviado = m.sentido === "enviado";
  return (
    <li className={cn("flex gap-3 py-3.5", !ultimo && "border-b")}>
      <span
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-foreground/70",
          ll?.tipo === "negociacion" && "bg-primary text-primary-foreground",
        )}
        aria-hidden
      >
        <Icono className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-medium">
            {m.de} {m.canal === "llamada" ? "↔" : "→"} {m.para}
          </span>
          <Marca tono="neutro">
            {ll?.intento && ll.intento > 1 ? `${etiqueta} · intento ${ll.intento}` : etiqueta}
          </Marca>
          <Marca tono={enviado ? "azul" : "gris"}>{enviado ? "Enviado" : "Recibido"}</Marca>
          {ll && (
            <Marca tono={RESULTADO_LLAMADA[ll.resultado].tono}>
              {RESULTADO_LLAMADA[ll.resultado].etiqueta}
              {ll.resultado === "atendida" && ll.duracion_segundos ? ` · ${duracion(ll.duracion_segundos)}` : ""}
            </Marca>
          )}
          {m.etiqueta && <Marca tono={tonoEtiquetaMensaje(m.etiqueta)}>{m.etiqueta}</Marca>}
          <span className="text-xs text-muted-foreground tabular-nums">
            {m.fecha ? diaHora(m.fecha) : "sin hora registrada"}
            {!ll && m.duracion_segundos ? ` · ${duracion(m.duracion_segundos)}` : ""}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          {PROPOSITO[conv.proposito]}
          {m.motivo && MOTIVO[m.motivo] && MOTIVO[m.motivo] !== PROPOSITO[conv.proposito]
            ? ` · ${MOTIVO[m.motivo]}`
            : ""}
        </div>
        {m.texto && (
          <div className="mt-1.5">
            {(m.canal === "audio" || m.canal === "nota_voz") && (
              <div className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
                Transcripción
              </div>
            )}
            <TextoLargo texto={m.texto} />
          </div>
        )}
        {m.archivo_url && (
          <a
            href={urlArchivo(m.archivo_url)}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-flex items-center gap-2 text-sm underline-offset-4 hover:underline"
          >
            {m.canal === "foto" ? (
              <img
                src={urlArchivo(m.archivo_url)}
                alt={`Foto enviada por ${m.de}`}
                className="h-20 w-auto rounded-md border object-cover"
              />
            ) : (
              <>
                <ExternalLinkIcon className="size-3.5" /> Abrir el {m.canal === "pdf" ? "PDF" : "archivo"}
              </>
            )}
          </a>
        )}
        {ll && <Llamada m={m} />}
        {m.nota && <p className="mt-1.5 text-xs text-muted-foreground italic">{m.nota}</p>}
      </div>
    </li>
  );
}

export default function Conversaciones({ conversaciones }: { conversaciones: Conversacion[] }) {
  const [canal, setCanal] = useState<CanalMensaje | "todos">("todos");
  const items = useMemo(() => {
    const todos = conversaciones.flatMap((conv) => conv.mensajes.map((m) => ({ m, conv })));
    return todos.sort((a, b) => {
      if (!a.m.fecha) return b.m.fecha ? 1 : 0;
      if (!b.m.fecha) return -1;
      return a.m.fecha.localeCompare(b.m.fecha);
    });
  }, [conversaciones]);
  const conteo = useMemo(() => {
    const c = new Map<CanalMensaje, number>();
    for (const { m } of items) c.set(m.canal, (c.get(m.canal) ?? 0) + 1);
    return c;
  }, [items]);
  const visibles = canal === "todos" ? items : items.filter((i) => i.m.canal === canal);

  if (!items.length) {
    return (
      <Empty className="border bg-background">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MessagesSquareIcon />
          </EmptyMedia>
          <EmptyTitle>Todavía no hay conversaciones</EmptyTitle>
          <EmptyDescription>
            Cuando el agente pida cotizaciones o lleguen respuestas, aparecen acá con su canal.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Conversaciones</CardTitle>
        <CardDescription>
          Cada mensaje con su canal, sentido y participante · {conversaciones.length}{" "}
          {conversaciones.length === 1 ? "conversación" : "conversaciones"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por canal">
          {(["todos", ...conteo.keys()] as const).map((c) => (
            <button
              key={c}
              type="button"
              aria-pressed={canal === c}
              onClick={() => setCanal(c)}
              className={cn(
                "inline-flex h-7 items-center rounded-full border px-2.5 text-xs font-medium transition-colors",
                canal === c ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-muted",
              )}
            >
              {c === "todos" ? `Todos los canales · ${items.length}` : `${CANAL[c].etiqueta} · ${conteo.get(c)}`}
            </button>
          ))}
        </div>
        <ol className="mt-1">
          {visibles.map((item, i) => (
            <Fila key={item.m.id} item={item} ultimo={i === visibles.length - 1} />
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
