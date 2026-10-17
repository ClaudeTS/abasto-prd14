import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowRightIcon, InboxIcon, TriangleAlertIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { formatNumero, precioUnitario } from "@/lib/format";
import { PROVEEDORES, nombreProveedor } from "@/lib/proveedores";
import { usePolling } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Encabezado, ErrorBanner, Etiqueta } from "@/components/comunes";
import ModalMensaje from "@/components/ModalMensaje";
import TarjetaCotizacion, { necesitaRevision } from "@/components/TarjetaCotizacion";
import type { Cotizacion, MensajeCrudo, PedidoDemo } from "@/types";

export default function Cotizaciones({ demo }: { demo: PedidoDemo }) {
  const navigate = useNavigate();
  const { hash } = useLocation();
  const { pedido, catalogo, config } = demo;
  const [mensajes, setMensajes] = useState<MensajeCrudo[]>([]);
  const [cotizaciones, setCotizaciones] = useState<Cotizacion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargado, setCargado] = useState(false);
  const [abierto, setAbierto] = useState<MensajeCrudo | null>(null);

  const enLectura = mensajes.some((m) => m.estado === "pendiente" || m.estado === "leyendo");
  const activo = !cargado || pedido.estado === "cotizando" || enLectura;

  usePolling(
    async () => {
      try {
        const [m, c] = await Promise.all([api.getMensajes(pedido.id), api.getCotizaciones(pedido.id)]);
        setMensajes(m);
        setCotizaciones(c);
        setError(null);
      } catch (e) {
        setError(mensajeError(e));
      } finally {
        setCargado(true);
      }
    },
    1500,
    activo,
  );

  const destacada = hash.slice(1);
  useEffect(() => {
    if (!destacada || !cotizaciones.length) return;
    document.getElementById(destacada)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [destacada, cotizaciones.length > 0]);

  const confirmar = async (cot: Cotizacion, campo: string | null, valor?: boolean) => {
    try {
      const nueva =
        campo === null ? await api.confirmarLectura(cot.id) : await api.confirmarCampo(cot.id, campo, valor ?? true);
      setCotizaciones((cs) => cs.map((c) => (c.id === nueva.id ? nueva : c)));
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  };

  const ordenadas = [...cotizaciones].sort(
    (a, b) =>
      PROVEEDORES.findIndex((p) => p.id === a.proveedor_id) - PROVEEDORES.findIndex((p) => p.id === b.proveedor_id),
  );
  const paraRevisar = cotizaciones.filter(necesitaRevision);

  if (!cargado) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Spinner /> Cargando cotizaciones…
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <Encabezado
        titulo="Cotizaciones"
        bajada="Cada respuesta convertida a precio sin IVA, en pesos y por unidad. Cada número tiene la evidencia del mensaje original."
      >
        <Etiqueta>USD 1 = $ {formatNumero(config.tipo_cambio_usd, 2)}</Etiqueta>
        <Etiqueta>IVA {Math.round(config.iva * 100)} %</Etiqueta>
        {paraRevisar.length > 0 && (
          <Etiqueta tono="ambar">
            <TriangleAlertIcon /> {paraRevisar.length} para revisar
          </Etiqueta>
        )}
      </Encabezado>

      <ErrorBanner mensaje={error} />

      {cotizaciones.length === 0 ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <InboxIcon />
            </EmptyMedia>
            <EmptyTitle>Todavía no hay cotizaciones</EmptyTitle>
            <EmptyDescription>
              {pedido.estado === "nuevo" ? "Pedí cotización desde el pedido." : "Están llegando las respuestas."}
            </EmptyDescription>
          </EmptyHeader>
          {pedido.estado === "nuevo" && (
            <EmptyContent>
              <Button onClick={() => navigate("/pedido")}>Ir al pedido</Button>
            </EmptyContent>
          )}
        </Empty>
      ) : (
        <>
          <Comparativo demo={demo} cotizaciones={ordenadas} />

          <div className="grid gap-6 lg:grid-cols-2">
            {ordenadas.map((c) => (
              <TarjetaCotizacion
                key={c.id}
                cotizacion={c}
                catalogo={catalogo}
                destacada={c.id === destacada}
                onVerOriginal={() => setAbierto(mensajes.find((m) => m.id === c.mensaje_id) ?? null)}
                canalMensaje={mensajes.find((m) => m.id === c.mensaje_id)?.canal}
                onConfirmar={(campo, valor) => confirmar(c, campo, valor)}
              />
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <Button size="lg" onClick={() => navigate("/plan")}>
              Armar el plan de compra <ArrowRightIcon />
            </Button>
            {paraRevisar.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Hay {paraRevisar.length} {paraRevisar.length === 1 ? "cotización" : "cotizaciones"} para revisar antes de
                optimizar ({paraRevisar.map((c) => nombreProveedor(c.proveedor_id)).join(", ")}).
              </p>
            )}
          </div>
        </>
      )}

      <ModalMensaje
        mensaje={abierto}
        evidencias={abierto ? (cotizaciones.find((c) => c.mensaje_id === abierto.id)?.items.map((i) => i.evidencia) ?? []) : []}
        onCerrar={() => setAbierto(null)}
      />
    </div>
  );
}

/** Tabla producto × proveedor con el precio normalizado; el más barato de cada fila resaltado. */
function Comparativo({ demo, cotizaciones }: { demo: PedidoDemo; cotizaciones: Cotizacion[] }) {
  const { pedido, catalogo } = demo;
  return (
    <Card className="gap-0 pb-0">
      <CardHeader className="pb-4">
        <CardTitle>Comparativo normalizado</CardTitle>
        <CardDescription>Precio sin IVA por unidad. Pasá el mouse por un precio para ver su evidencia.</CardDescription>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="pl-6">Producto</TableHead>
            {cotizaciones.map((c) => (
              <TableHead key={c.id} className="text-right last:pr-6">
                <a href={`#${c.id}`} className="hover:underline">
                  {nombreProveedor(c.proveedor_id)}
                </a>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {pedido.lineas.map((l) => {
            const items = cotizaciones.map((c) => c.items.find((i) => i.producto_id === l.producto_id) ?? null);
            const validos = items.filter((i) => i !== null).map((i) => i!.precio_unitario_sin_iva);
            const minimo = validos.length ? Math.min(...validos) : null;
            return (
              <TableRow key={l.producto_id}>
                <TableCell className="py-3 pl-6 font-medium">
                  {catalogo.find((p) => p.id === l.producto_id)?.nombre ?? l.producto_id}
                </TableCell>
                {items.map((item, k) => {
                  const dudoso = !!item && necesitaRevision(cotizaciones[k]) && cotizaciones[k].campos_dudosos.includes("iva");
                  return (
                    <TableCell
                      key={k}
                      title={item ? `“${item.evidencia}”${item.conversion_aplicada ? `\n${item.conversion_aplicada}` : ""}` : undefined}
                      className={cn(
                        "text-right tabular-nums last:pr-6",
                        !item && "text-muted-foreground/40",
                        dudoso && "text-amber-700 dark:text-amber-400",
                      )}
                    >
                      {item ? (
                        <>
                          <span
                            className={cn(
                              !dudoso && item.precio_unitario_sin_iva === minimo &&
                                "rounded-md bg-emerald-50 px-1.5 py-0.5 font-semibold text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
                            )}
                          >
                            {precioUnitario(item.precio_unitario_sin_iva)}
                          </span>
                          {dudoso && <TriangleAlertIcon className="ml-1 inline size-3.5" />}
                          {item.cantidad_minima ? (
                            <span className="block text-[11px] text-muted-foreground">mín. {item.cantidad_minima}</span>
                          ) : null}
                        </>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}
