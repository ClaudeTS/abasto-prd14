// Barra con los estados del pedido (§6.2): los que pasó, el actual y los que faltan.
import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { CAMINO, ETIQUETA_ESTADO, fechaHoraLarga } from "./presentacion";
import type { EstadoPedido, EventoEstado } from "./types";

type Paso = {
  estado: EstadoPedido;
  tipo: "hecho" | "actual" | "salteado" | "pendiente" | "cancelado";
  evento?: EventoEstado;
};

function pasos(estado: EstadoPedido, historial: EventoEstado[]): Paso[] {
  const evento = (e: EstadoPedido) => [...historial].reverse().find((h) => h.estado === e);
  if (estado === "cancelado") {
    const pasados = CAMINO.filter((e) => evento(e)).map((e): Paso => ({ estado: e, tipo: "hecho", evento: evento(e) }));
    return [...pasados, { estado: "cancelado", tipo: "cancelado", evento: evento("cancelado") }];
  }
  const actual = CAMINO.indexOf(estado);
  return CAMINO.map((e, i): Paso => {
    const ev = evento(e);
    if (i === actual) return { estado: e, tipo: "actual", evento: ev };
    if (i < actual) return { estado: e, tipo: ev ? "hecho" : "salteado", evento: ev };
    return { estado: e, tipo: "pendiente" };
  });
}

export default function BarraEstados({ estado, historial }: { estado: EstadoPedido; historial: EventoEstado[] }) {
  const lista = pasos(estado, historial);
  const ultimo = [...historial].reverse().find((h) => h.estado === estado);
  return (
    <div className="space-y-2">
      <ol className="flex flex-wrap items-center gap-1.5" aria-label="Estados del pedido">
        {lista.map((p) => (
          <li
            key={p.estado}
            aria-current={p.tipo === "actual" || p.tipo === "cancelado" ? "step" : undefined}
            title={
              p.tipo === "salteado"
                ? `${ETIQUETA_ESTADO[p.estado]}: no hizo falta`
                : p.evento
                  ? `${ETIQUETA_ESTADO[p.estado]}${p.evento.en ? ` · ${fechaHoraLarga(p.evento.en)}` : ""}${p.evento.detalle ? `\n${p.evento.detalle}` : ""}`
                  : ETIQUETA_ESTADO[p.estado]
            }
            className={cn(
              "inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-xs font-medium whitespace-nowrap",
              p.tipo === "hecho" && "bg-primary text-primary-foreground",
              p.tipo === "actual" && "bg-background text-foreground ring-[1.5px] ring-foreground",
              p.tipo === "salteado" &&
                "bg-muted/60 text-muted-foreground/70 line-through decoration-muted-foreground/50",
              p.tipo === "pendiente" && "bg-muted text-muted-foreground",
              p.tipo === "cancelado" &&
                "bg-red-50 text-red-800 ring-1 ring-red-200 dark:bg-red-950 dark:text-red-300 dark:ring-red-900",
            )}
          >
            {p.tipo === "hecho" && <CheckIcon className="size-3" aria-hidden />}
            {ETIQUETA_ESTADO[p.estado]}
          </li>
        ))}
      </ol>
      {ultimo?.detalle && (
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{ETIQUETA_ESTADO[estado]}</span>
          {ultimo.en ? ` · ${fechaHoraLarga(ultimo.en)}` : ""} · {ultimo.detalle}
        </p>
      )}
    </div>
  );
}
