import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRightIcon, SendIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { diasEntre, fechaCorta, formatNumero, unidad } from "@/lib/format";
import { CANALES, PROVEEDORES } from "@/lib/proveedores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Avatar, Encabezado, ErrorBanner, Etiqueta } from "@/components/comunes";
import type { PedidoDemo } from "@/types";

export default function PedidoPage({ demo, onCotizado }: { demo: PedidoDemo; onCotizado: () => Promise<void> }) {
  const navigate = useNavigate();
  const { pedido, catalogo } = demo;
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const yaCotizado = pedido.estado !== "nuevo";
  const hoy = pedido.fecha ?? new Date().toISOString().slice(0, 10);

  const cotizar = async () => {
    setCargando(true);
    setError(null);
    try {
      await api.cotizar(pedido.id);
      await onCotizado();
      navigate("/feed");
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="space-y-8">
      <Encabezado
        titulo={pedido.descripcion ?? "Pedido de compra"}
        bajada={
          <>
            {pedido.negocio}
            {pedido.comprador ? ` · ${pedido.comprador}` : ""}
            {pedido.fecha ? ` · ${fechaCorta(pedido.fecha)}/${pedido.fecha.slice(0, 4)}` : ""}
          </>
        }
      >
        <Etiqueta tono={yaCotizado ? "azul" : "neutro"}>Estado: {pedido.estado}</Etiqueta>
      </Encabezado>

      <Card className="py-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-11 pl-6">Producto</TableHead>
              <TableHead className="text-right">Cantidad</TableHead>
              <TableHead className="pr-6 text-right">Se necesita para</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pedido.lineas.map((l) => {
              const producto = catalogo.find((p) => p.id === l.producto_id);
              const dias = diasEntre(hoy, l.necesario_para);
              return (
                <TableRow key={l.producto_id}>
                  <TableCell className="py-4 pl-6 font-medium">{producto?.nombre ?? l.producto_id}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    <span className="text-base font-semibold">{formatNumero(l.cantidad)}</span>{" "}
                    <span className="text-muted-foreground">{unidad(producto?.unidad_canonica ?? "unidad", l.cantidad)}</span>
                  </TableCell>
                  <TableCell className="pr-6 text-right">
                    {fechaCorta(l.necesario_para)}{" "}
                    <span className={dias <= 3 ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground"}>
                      (en {dias} días)
                    </span>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Proveedores</CardTitle>
          <CardDescription>
            Abasto le pide cotización a {PROVEEDORES.length} proveedores por su canal habitual. Las respuestas llegan como
            lleguen: texto, PDF, foto o audio.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PROVEEDORES.map((p) => {
            const canal = CANALES[p.canal_preferido];
            return (
              <div key={p.id} className="flex items-center gap-3 rounded-lg border p-3">
                <Avatar proveedorId={p.id} />
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 font-medium">
                    <span className="truncate">{p.nombre}</span>
                    {p.id === pedido.proveedor_habitual_id && <Etiqueta>habitual</Etiqueta>}
                  </p>
                  <p className="truncate text-muted-foreground">{p.rubro}</p>
                </div>
                <canal.icono className="size-4 shrink-0 text-muted-foreground" aria-label={canal.etiqueta} />
              </div>
            );
          })}
        </CardContent>
      </Card>

      <ErrorBanner mensaje={error} onReintentar={cotizar} />

      <div className="flex flex-wrap items-center gap-4">
        {yaCotizado ? (
          <>
            <Button size="lg" onClick={() => navigate("/feed")}>
              Ver las respuestas <ArrowRightIcon />
            </Button>
            <p className="text-sm text-muted-foreground">Ya se pidió cotización. Para empezar de cero: “Reiniciar”.</p>
          </>
        ) : (
          <Button size="lg" onClick={cotizar} disabled={cargando}>
            {cargando ? <Spinner /> : <SendIcon />} Cotizar con {PROVEEDORES.length} proveedores
          </Button>
        )}
      </div>
    </div>
  );
}
