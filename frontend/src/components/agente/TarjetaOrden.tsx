import { useState } from "react";
import { BotIcon, CheckIcon, ChevronDownIcon, CircleAlertIcon, UserIcon, XIcon } from "lucide-react";
import { formatNumero, pesos, precioUnitario, unidad } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Avatar, Etiqueta } from "@/components/comunes";
import type { OrdenCompra } from "@/types";

/** Una orden de compra emitida por el agente: qué lleva, quién la aprobó y el mensaje que salió. */
export default function TarjetaOrden({
  orden,
  onAprobar,
  onRechazar,
}: {
  orden: OrdenCompra;
  onAprobar?: () => Promise<void>;
  onRechazar?: () => Promise<void>;
}) {
  const [verMensaje, setVerMensaje] = useState(false);
  const [accion, setAccion] = useState<"aprobar" | "rechazar" | null>(null);
  const espera = orden.estado === "esperando_aprobacion";

  const correr = async (cual: "aprobar" | "rechazar", fn?: () => Promise<void>) => {
    if (!fn) return;
    setAccion(cual);
    try {
      await fn();
    } finally {
      setAccion(null);
    }
  };

  return (
    <div
      className={cn(
        "rounded-xl border bg-background",
        espera && "border-amber-300 dark:border-amber-800",
        orden.estado === "rechazada" && "opacity-60",
      )}
    >
      <div className="flex flex-wrap items-center gap-3 p-3">
        <Avatar proveedorId={orden.proveedor_id} className="size-8 text-[10px]" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {orden.numero} · {orden.proveedor_nombre}
          </p>
          <p className="text-xs text-muted-foreground tabular-nums">
            {pesos(orden.total_sin_iva)} + IVA{orden.envio ? ` (con ${pesos(orden.envio)} de envío)` : ""}
          </p>
        </div>
        <EstadoOrden orden={orden} />
      </div>

      <ul className="space-y-1.5 border-t px-3 py-2.5 text-sm">
        {orden.lineas.map((l) => (
          <li key={l.producto_id} className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">
              {formatNumero(l.cantidad)} {l.unidad === "unidad" ? "" : unidad(l.unidad) + " de "}
              {l.nombre_corto}
            </span>
            <span className="text-muted-foreground tabular-nums">
              a {precioUnitario(l.precio_unitario_sin_iva)} · {pesos(l.subtotal)}
            </span>
            <span
              className={cn(
                "basis-full text-xs",
                l.aprobacion === "automatica" ? "text-muted-foreground" : "text-amber-800 dark:text-amber-300",
              )}
            >
              {l.motivo}
            </span>
            {l.evidencia && (
              <span className="basis-full truncate text-xs text-muted-foreground italic" title={l.evidencia}>
                Precio de: “{l.evidencia}”
              </span>
            )}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2">
        <Button variant="ghost" size="xs" onClick={() => setVerMensaje(!verMensaje)}>
          <ChevronDownIcon className={cn("transition-transform", verMensaje && "rotate-180")} />
          {verMensaje ? "Ocultar el mensaje" : "Ver el mensaje"}
        </Button>
        {espera && onAprobar && onRechazar && (
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="outline" disabled={accion !== null} onClick={() => correr("rechazar", onRechazar)}>
              {accion === "rechazar" ? <Spinner /> : <XIcon />} Rechazar
            </Button>
            <Button size="sm" disabled={accion !== null} onClick={() => correr("aprobar", onAprobar)}>
              {accion === "aprobar" ? <Spinner /> : <CheckIcon />} Aprobar
            </Button>
          </div>
        )}
      </div>
      {verMensaje && (
        <p className="mx-3 mb-3 rounded-lg bg-muted p-3 text-sm whitespace-pre-wrap">{orden.mensaje}</p>
      )}
    </div>
  );
}

function EstadoOrden({ orden }: { orden: OrdenCompra }) {
  if (orden.estado === "rechazada") return <Etiqueta tono="rojo">Rechazada</Etiqueta>;
  if (orden.estado === "esperando_aprobacion")
    return (
      <Etiqueta tono="ambar">
        <CircleAlertIcon /> Espera tu OK
      </Etiqueta>
    );
  return orden.aprobada_por === "agente" ? (
    <Etiqueta tono="verde">
      <BotIcon /> La mandó el agente
    </Etiqueta>
  ) : (
    <Etiqueta tono="verde">
      <UserIcon /> La aprobaste vos
    </Etiqueta>
  );
}
