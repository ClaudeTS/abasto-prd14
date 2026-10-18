// RF-07: ranking de proveedores por producto con la regla en cascada de §11.1 y el motivo de cada posición.
// Reutilizable: <RankingProveedores pedidoId="…" productoId="silla" /> (sin productoId, todo el pedido).
import { useCallback, useEffect, useState } from "react";
import {
  BotIcon,
  CircleSlashIcon,
  ListOrderedIcon,
  TrophyIcon,
} from "lucide-react";
import { ApiError, mensajeError } from "@/lib/errores";
import {
  fechaCorta,
  formatNumero,
  precioUnitario,
  unidad as textoUnidad,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ErrorBanner, Etiqueta } from "@/components/comunes";
import * as api from "./api";
import AltaProveedor, { type InicialAlta } from "./AltaProveedor";
import { DatosEjemplo, dias, garantia, pago } from "./comunes";
import type { Candidato, Ranking, RankingProducto } from "./types";

const CRITERIO: Record<string, string> = {
  precio: "precio",
  atributos: "atributos",
  antiguedad: "antigüedad",
};

export default function RankingProveedores({
  pedidoId,
  productoId,
}: {
  pedidoId: string;
  productoId?: string;
}) {
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alta, setAlta] = useState<InicialAlta | null>(null);

  const cargar = useCallback(async () => {
    try {
      setError(null);
      setRanking(await api.obtenerRanking(pedidoId, productoId));
    } catch (e) {
      setError(mensajeError(e));
      if (e instanceof ApiError) setRanking(null);
    }
  }, [pedidoId, productoId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (error) return <ErrorBanner mensaje={error} onReintentar={cargar} />;
  if (!ranking) return <Skeleton className="h-64 rounded-xl" />;

  const sinCotizaciones = ranking.productos.every(
    (p) => p.ranking.length === 0 && p.excluidos.length === 0,
  );
  if (sinCotizaciones)
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ListOrderedIcon />
          </EmptyMedia>
          <EmptyTitle>Todavía no hay ranking</EmptyTitle>
          <EmptyDescription>
            Aparece cuando lleguen las cotizaciones de los proveedores.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );

  return (
    <div className="flex flex-col gap-4">
      {ranking.productos.map((p) => (
        <TarjetaProducto
          key={p.producto_id}
          p={p}
          onAlta={() =>
            setAlta({
              productos: [p.producto_id],
              pedidoId,
              motivo: `Necesitamos más cotizaciones de ${p.nombre.toLowerCase()} para un pedido de ${formatNumero(p.cantidad)} ${textoUnidad(p.unidad, p.cantidad)}.`,
            })
          }
        />
      ))}
      <details className="rounded-xl border bg-background px-4 py-3 text-sm">
        <summary className="cursor-pointer font-medium">Cómo se ordena</summary>
        <ol className="mt-2 flex flex-col gap-1 text-muted-foreground">
          {ranking.regla.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ol>
      </details>
      <DatosEjemplo>
        Antigüedad, cumplimiento histórico y garantía son ilustrativos en la
        demo.
      </DatosEjemplo>
      <AltaProveedor
        open={alta !== null}
        onOpenChange={(v) => !v && setAlta(null)}
        inicial={alta ?? undefined}
      />
    </div>
  );
}

function TarjetaProducto({
  p,
  onAlta,
}: {
  p: RankingProducto;
  onAlta: () => void;
}) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>{p.nombre}</CardTitle>
        <CardDescription>
          {formatNumero(p.cantidad)} {textoUnidad(p.unidad, p.cantidad)} · para
          el {fechaCorta(p.necesario_para)} ({dias(p.dias_requeridos)}) ·{" "}
          {p.ranking.length} elegible{p.ranking.length === 1 ? "" : "s"}
        </CardDescription>
        {p.ranking[0] && (
          <CardAction>
            <Etiqueta tono="verde">
              <TrophyIcon /> {p.ranking[0].nombre}
            </Etiqueta>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="px-0">
        <Table className="min-w-[720px]">
          <TableHeader>
            <TableRow className="[&>th]:px-4">
              <TableHead className="w-10">#</TableHead>
              <TableHead>Proveedor</TableHead>
              <TableHead className="text-right">Costo comparable</TableHead>
              <TableHead>Entrega</TableHead>
              <TableHead>Pago</TableHead>
              <TableHead>Garantía</TableHead>
              <TableHead>Antigüedad</TableHead>
              <TableHead>Cumpl.</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {p.ranking.map((c) => (
              <FilaCandidato key={c.proveedor_id} c={c} unidad={p.unidad} />
            ))}
            {p.excluidos.map((c) => (
              <FilaCandidato
                key={c.proveedor_id}
                c={c}
                unidad={p.unidad}
                excluido
              />
            ))}
          </TableBody>
        </Table>
      </CardContent>
      {(p.sugerencia_alta || p.sin_cotizar.length > 0) && (
        <CardFooter className="flex-wrap justify-between gap-3 text-sm">
          <span className="text-muted-foreground">
            {p.sugerencia_alta ?? ""}
            {p.sin_cotizar.length > 0 && (
              <>
                {p.sugerencia_alta ? " " : ""}No cotizan este producto:{" "}
                {p.sin_cotizar.join(", ").replace(/\.$/, "")}.
              </>
            )}
          </span>
          {p.pocos_proveedores && (
            <Button size="sm" variant="outline" onClick={onAlta}>
              <BotIcon /> Que el agente busque uno
            </Button>
          )}
        </CardFooter>
      )}
    </Card>
  );
}

function FilaCandidato({
  c,
  unidad,
  excluido = false,
}: {
  c: Candidato;
  unidad: string;
  excluido?: boolean;
}) {
  // El motivo va en una segunda línea a todo el ancho: como columna, en el detalle del pedido (columna angosta)
  // estiraba cada fila.
  return (
    <>
      <TableRow
        className={cn(
          "border-b-0 align-top [&>td]:px-4 [&>td]:pt-2.5 [&>td]:pb-1",
          excluido && "text-muted-foreground",
        )}
      >
        <TableCell className="font-medium tabular-nums">
          {excluido ? (
            <CircleSlashIcon className="size-4" aria-label="Excluido" />
          ) : (
            `${c.posicion}.º`
          )}
        </TableCell>
        <TableCell className="whitespace-normal">
          <div className={cn(!excluido && "font-medium")}>{c.nombre}</div>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {c.en_plan && <Etiqueta tono="azul">en el plan</Etiqueta>}
            {!excluido && c.criterio && c.criterio !== "precio" && (
              <Etiqueta>desempate por {CRITERIO[c.criterio]}</Etiqueta>
            )}
            {excluido && <Etiqueta tono="rojo">excluido</Etiqueta>}
          </div>
        </TableCell>
        <TableCell className="text-right tabular-nums" title={c.evidencia}>
          {precioUnitario(c.costo_comparable)}
          <div className="text-xs text-muted-foreground">
            {unidad === "l" ? "por litro" : "por unidad"} sin IVA
          </div>
        </TableCell>
        <TableCell>{dias(c.entrega_dias)}</TableCell>
        <TableCell>{pago(c.pago_dias)}</TableCell>
        <TableCell>{garantia(c.garantia_meses)}</TableCell>
        <TableCell>{c.antiguedad}</TableCell>
        <TableCell className="tabular-nums">
          {c.cumplimiento_historico_pct !== null
            ? `${formatNumero(c.cumplimiento_historico_pct)} %`
            : "—"}
        </TableCell>
      </TableRow>
      <TableRow className="hover:bg-transparent">
        <TableCell />
        <TableCell
          colSpan={7}
          className="px-4 pt-0 pb-2.5 text-sm whitespace-normal text-muted-foreground"
        >
          {c.motivo}
        </TableCell>
      </TableRow>
    </>
  );
}
