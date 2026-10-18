// Columna derecha del detalle: exportar el informe PDF (RF-18), órdenes de compra y productos.
import { useState } from "react";
import { CheckIcon, DownloadIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { mensajeError } from "@/lib/errores";
import { pesos, precioUnitario } from "@/lib/format";
import { aprobarOrden, descargarInforme, rechazarOrden } from "./api";
import { Marca, cantidadConUnidad, diaHora, type TonoPedido } from "./presentacion";
import type { DetallePedido, OrdenDetalle, ParteInforme } from "./types";
import { Casilla } from "./ui";

export function TarjetaInforme({ pedido }: { pedido: DetallePedido }) {
  const [partes, setPartes] = useState<Record<ParteInforme, boolean>>({ pedido: true, dialogo: true });
  const [bajando, setBajando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const elegidas = (Object.keys(partes) as ParteInforme[]).filter((p) => partes[p]);

  const bajar = async () => {
    setBajando(true);
    setError(null);
    try {
      await descargarInforme(pedido.id, pedido.numero, elegidas);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setBajando(false);
    }
  };

  const opciones: { clave: ParteInforme; texto: string }[] = [
    { clave: "pedido", texto: "Datos del pedido, cotizaciones y órdenes" },
    { clave: "dialogo", texto: "Diálogo del agente (mensajes y transcripciones)" },
  ];
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Exportar informe PDF</CardTitle>
        <CardDescription>Elegí qué incluir en el informe</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2.5">
          {opciones.map((o) => (
            <label key={o.clave} className="flex cursor-pointer items-start gap-2.5 text-sm">
              <Casilla
                className="mt-0.5"
                checked={partes[o.clave]}
                onCheckedChange={(v) => setPartes((p) => ({ ...p, [o.clave]: v === true }))}
              />
              {o.texto}
            </label>
          ))}
        </div>
        <Button className="w-full" onClick={bajar} disabled={bajando || elegidas.length === 0}>
          {bajando ? <Spinner /> : <DownloadIcon />}
          Descargar PDF
        </Button>
        {elegidas.length === 0 && <p className="text-xs text-muted-foreground">Elegí al menos una parte.</p>}
        {error && <p className="text-xs text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

const ESTADO_ORDEN: Record<OrdenDetalle["estado"], { etiqueta: string; tono: TonoPedido }> = {
  pendiente_aprobacion: { etiqueta: "Espera tu OK", tono: "ambar" },
  emitida: { etiqueta: "Emitida", tono: "verde" },
  pendiente_entrega: { etiqueta: "Pendiente de entrega", tono: "neutro" },
  recibida: { etiqueta: "Recibida", tono: "verde" },
  cancelada: { etiqueta: "Rechazada", tono: "rojo" },
};

function Orden({ orden, ejemplo, onCambio }: { orden: OrdenDetalle; ejemplo: boolean; onCambio: () => Promise<void> }) {
  const [enCurso, setEnCurso] = useState<"aprobar" | "rechazar" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esperando = orden.estado_agente === "esperando_aprobacion" && !!orden.corrida_id && !ejemplo;
  const estado = ESTADO_ORDEN[orden.estado];

  const resolver = async (accion: "aprobar" | "rechazar") => {
    if (!orden.corrida_id) return;
    setEnCurso(accion);
    setError(null);
    try {
      await (accion === "aprobar" ? aprobarOrden : rechazarOrden)(orden.corrida_id, orden.id);
      await onCambio();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setEnCurso(null);
    }
  };

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">
            {orden.numero} · {orden.proveedor_nombre}
          </div>
          <div className="text-xs text-muted-foreground tabular-nums">
            {pesos(orden.total_sin_iva)} + IVA · {pesos(orden.total_con_iva)} con IVA
          </div>
        </div>
        <Marca tono={estado.tono}>{estado.etiqueta}</Marca>
      </div>
      <ul className="space-y-0.5 text-xs text-muted-foreground">
        {orden.lineas.map((l) => (
          <li key={l.producto_id} className="flex justify-between gap-2">
            <span className="truncate">
              {l.nombre} · {cantidadConUnidad(l.cantidad, l.unidad)}
            </span>
            <span className="shrink-0 tabular-nums">{precioUnitario(l.precio_unitario_sin_iva)}</span>
          </li>
        ))}
        {orden.envio > 0 && (
          <li className="flex justify-between gap-2">
            <span>Envío</span>
            <span className="tabular-nums">{pesos(orden.envio)}</span>
          </li>
        )}
      </ul>
      {orden.estado === "pendiente_aprobacion" && orden.motivos.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-amber-800 dark:text-amber-300">
          {orden.motivos.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
      {orden.aprobada_por && orden.estado !== "cancelada" && (
        <p className="text-xs text-muted-foreground">
          {orden.aprobada_por === "agente"
            ? "La mandó el agente (compra automática dentro del tope)"
            : "La aprobó Lucía"}
          {orden.emitida_en ? ` · ${diaHora(orden.emitida_en)}` : ""}
          {orden.negociada ? " · precio negociado" : ""}
        </p>
      )}
      {esperando && (
        <div className="flex gap-2 pt-1">
          <Button size="sm" onClick={() => resolver("aprobar")} disabled={!!enCurso}>
            {enCurso === "aprobar" ? <Spinner /> : <CheckIcon />}
            Aprobar
          </Button>
          <Button size="sm" variant="outline" onClick={() => resolver("rechazar")} disabled={!!enCurso}>
            {enCurso === "rechazar" ? <Spinner /> : <XIcon />}
            Rechazar
          </Button>
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function TarjetaOrdenes({ pedido, onCambio }: { pedido: DetallePedido; onCambio: () => Promise<void> }) {
  const pendientes = pedido.ordenes.filter((o) => o.estado === "pendiente_aprobacion").length;
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Órdenes de compra</CardTitle>
        <CardDescription>
          {pedido.ordenes.length === 0
            ? "Todavía no hay órdenes de compra."
            : pendientes
              ? `${pendientes} ${pendientes === 1 ? "espera" : "esperan"} tu aprobación`
              : `${pedido.ordenes.length} ${pedido.ordenes.length === 1 ? "orden" : "órdenes"}`}
        </CardDescription>
      </CardHeader>
      {pedido.ordenes.length > 0 && (
        <CardContent>
          {pedido.ordenes.map((o) => (
            <Orden key={o.id} orden={o} ejemplo={pedido.ejemplo} onCambio={onCambio} />
          ))}
        </CardContent>
      )}
    </Card>
  );
}

export function TarjetaProductos({ pedido }: { pedido: DetallePedido }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Productos</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2.5">
          {pedido.lineas.map((l) => (
            <li key={l.producto_id} className="flex items-center justify-between gap-2 text-sm">
              <span className="min-w-0">
                {l.nombre} · <span className="tabular-nums">{cantidadConUnidad(l.cantidad, l.unidad)}</span>
              </span>
              {l.proveedor_nombre ? (
                <Marca tono="verde" className="max-w-36 truncate">
                  {l.proveedor_nombre}
                </Marca>
              ) : (
                <Marca tono="gris">Sin proveedor</Marca>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
