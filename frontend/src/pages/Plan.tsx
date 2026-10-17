import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { HandshakeIcon, RefreshCwIcon, SparklesIcon, TrendingDownIcon, TriangleAlertIcon } from "lucide-react";
import * as api from "@/api";
import type { EnCurso } from "@/App";
import { mensajeError } from "@/lib/errores";
import { aPorcentaje, diasEntre, formatNumero, pesos, porcentaje, precioUnitario, unidad } from "@/lib/format";
import { nombreProveedor } from "@/lib/proveedores";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Avatar, Encabezado, ErrorBanner, Etiqueta } from "@/components/comunes";
import { necesitaRevision } from "@/components/TarjetaCotizacion";
import type { Asignacion, Cotizacion, PedidoDemo, Plan } from "@/types";

export default function PlanPage({
  demo,
  plan,
  onPlan,
  iniciarNegociacion,
  negociando,
}: {
  demo: PedidoDemo;
  plan: Plan | null;
  onPlan: (p: Plan) => void;
  iniciarNegociacion: (proveedorId: string) => void;
  negociando: Record<string, EnCurso>;
}) {
  const navigate = useNavigate();
  const { pedido } = demo;
  const [cotizaciones, setCotizaciones] = useState<Cotizacion[] | null>(null);
  const [optimizando, setOptimizando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getCotizaciones(pedido.id)
      .then(setCotizaciones)
      .catch((e) => setError(mensajeError(e)));
  }, [pedido.id, plan]);

  const optimizar = async () => {
    setOptimizando(true);
    setError(null);
    try {
      onPlan(await api.optimizar(pedido.id));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setOptimizando(false);
    }
  };

  const negociar = (proveedorId: string) => {
    if (!negociando[proveedorId]) iniciarNegociacion(proveedorId);
    navigate(`/negociacion/${proveedorId}`);
  };

  const paraRevisar = (cotizaciones ?? []).filter(necesitaRevision);

  if (!plan || optimizando) {
    return (
      <div className="mx-auto max-w-2xl">
        <Encabezado
          titulo="Plan de compra"
          bajada="Un solver matemático (MILP) reparte el pedido entre proveedores: minimiza el costo total respetando mínimos de pedido, plazos de entrega, envío y riesgo. El modelo de lenguaje solo explica el resultado."
        />
        <div className="space-y-4">
          <ErrorBanner mensaje={error} onReintentar={optimizar} />
          <Card>
            {cotizaciones === null ? (
              <CardContent className="flex-row items-center gap-2 text-muted-foreground">
                <Spinner /> Cargando cotizaciones…
              </CardContent>
            ) : optimizando ? (
              <CardContent className="flex-row items-center gap-4 py-2">
                <Spinner className="size-6" />
                <div>
                  <p className="font-medium">El solver está repartiendo la compra…</p>
                  <p className="text-muted-foreground">
                    {cotizaciones.length} cotizaciones · {pedido.lineas.length} productos · mínimos, plazos y envíos
                  </p>
                </div>
              </CardContent>
            ) : (
              <>
                <CardHeader>
                  <CardTitle>
                    {cotizaciones.length} {cotizaciones.length === 1 ? "cotización lista" : "cotizaciones listas"}
                  </CardTitle>
                  <CardDescription>para {pedido.lineas.length} productos del pedido.</CardDescription>
                </CardHeader>
                {paraRevisar.length > 0 && (
                  <CardContent>
                    <Alert className="border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                      <TriangleAlertIcon />
                      <AlertTitle>Hay datos sin confirmar</AlertTitle>
                      <AlertDescription className="text-amber-800 dark:text-amber-300">
                        <p>
                          {paraRevisar.map((c) => nombreProveedor(c.proveedor_id)).join(", ")}: el solver va a usar la lectura tal
                          cual. <Link to={`/cotizaciones#${paraRevisar[0].id}`}>Revisar primero</Link>
                        </p>
                      </AlertDescription>
                    </Alert>
                  </CardContent>
                )}
                <CardFooter>
                  <Button size="lg" onClick={optimizar} disabled={cotizaciones.length === 0}>
                    Optimizar la compra
                  </Button>
                  {cotizaciones.length === 0 && (
                    <span className="ml-3 text-muted-foreground">Primero tienen que llegar cotizaciones.</span>
                  )}
                </CardFooter>
              </>
            )}
          </Card>
        </div>
      </div>
    );
  }

  const habitual = nombreProveedor(pedido.proveedor_habitual_id);
  const pctComparable = plan.ahorro_pct_comparable != null ? aPorcentaje(plan.ahorro_pct_comparable) : null;
  const usados = plan.proveedores_usados;
  const cots = cotizaciones ?? [];
  const envios = usados
    .map((id) => cots.find((c) => c.proveedor_id === id))
    .filter((c): c is Cotizacion => !!c && c.costo_envio > 0);
  const oportunidad = plan.oportunidad_negociacion;
  const brecha = oportunidad ? brechaProveedor(oportunidad, plan, cots) : 0;

  return (
    <div className="space-y-6">
      <Encabezado titulo="Plan de compra" bajada={`${pedido.negocio} · precios sin IVA, en pesos`}>
        <Button variant="outline" onClick={optimizar}>
          <RefreshCwIcon /> Recalcular
        </Button>
      </Encabezado>

      <ErrorBanner mensaje={error} />

      <div className="grid gap-4 md:grid-cols-4">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardDescription>Ahorro vs. comprarle todo a {habitual}</CardDescription>
            <CardTitle className="text-5xl font-semibold tracking-tight tabular-nums">{pesos(plan.ahorro)}</CardTitle>
            <CardAction>
              <Etiqueta tono="verde">
                <TrendingDownIcon /> {porcentaje(aPorcentaje(plan.ahorro_pct))}
              </Etiqueta>
            </CardAction>
          </CardHeader>
          <CardFooter className="text-muted-foreground">
            {pesos(plan.costo_total)} en vez de {pesos(plan.costo_baseline)}
          </CardFooter>
        </Card>
        {pctComparable !== null && (
          <Card>
            <CardHeader>
              <CardDescription>Sobre lo que {habitual} sí vende</CardDescription>
              <CardTitle className="text-4xl font-semibold tracking-tight tabular-nums">{porcentaje(pctComparable)}</CardTitle>
            </CardHeader>
            <CardFooter className="text-muted-foreground">
              de ahorro{plan.ahorro_comparable != null ? ` (${pesos(plan.ahorro_comparable)})` : ""}
            </CardFooter>
          </Card>
        )}
        <Card>
          <CardHeader>
            <CardDescription>Proveedores</CardDescription>
            <CardTitle className="text-4xl font-semibold tracking-tight">{usados.length}</CardTitle>
          </CardHeader>
          <CardFooter>
            <div className="flex -space-x-2">
              {usados.map((id) => (
                <span key={id} title={nombreProveedor(id)} className="rounded-full ring-2 ring-background">
                  <Avatar proveedorId={id} className="size-8 text-[10px]" />
                </span>
              ))}
            </div>
          </CardFooter>
        </Card>
      </div>

      <Alert>
        <SparklesIcon />
        <AlertTitle>Por qué este plan</AlertTitle>
        <AlertDescription className="text-base text-foreground">
          <p>{plan.explicacion}</p>
          <p className="text-sm text-muted-foreground">
            Los proveedores y los números los decide el solver; la IA solo redacta la explicación.
          </p>
        </AlertDescription>
      </Alert>

      <Card className="gap-0 py-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-11 pl-6">Producto</TableHead>
              <TableHead>Proveedor elegido</TableHead>
              <TableHead className="text-right">Cantidad</TableHead>
              <TableHead className="text-right">Precio unit.</TableHead>
              <TableHead className="pr-6 text-right">Subtotal</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {plan.asignaciones.map((a) => (
              <FilaAsignacion key={`${a.producto_id}-${a.proveedor_id}`} a={a} demo={demo} cotizaciones={cots} />
            ))}
            {envios.map((c) => (
              <TableRow key={`envio-${c.proveedor_id}`} className="text-muted-foreground">
                <TableCell className="pl-6">Envío</TableCell>
                <TableCell>
                  {nombreProveedor(c.proveedor_id)}{" "}
                  <Link to={`/cotizaciones#${c.id}`} className="text-xs underline-offset-4 hover:underline">
                    (según su cotización)
                  </Link>
                </TableCell>
                <TableCell />
                <TableCell />
                <TableCell className="pr-6 text-right tabular-nums">{pesos(c.costo_envio)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
          <TableFooter>
            <TableRow>
              <TableCell colSpan={4} className="py-4 pl-6 font-medium">
                Total sin IVA
              </TableCell>
              <TableCell className="pr-6 text-right text-base font-semibold tabular-nums">{pesos(plan.costo_total)}</TableCell>
            </TableRow>
          </TableFooter>
        </Table>
      </Card>

      {(plan.restricciones_activas.length > 0 || plan.relajaciones.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          {plan.restricciones_activas.length > 0 && (
            <Card size="sm">
              <CardHeader>
                <CardTitle>Restricciones que pesaron</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
                  {plan.restricciones_activas.map((r, k) => (
                    <li key={k}>{r}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
          {plan.relajaciones.length > 0 && (
            <Card size="sm" className="ring-amber-300">
              <CardHeader>
                <CardTitle>Restricciones relajadas</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
                  {plan.relajaciones.map((r, k) => (
                    <li key={k}>{r}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {oportunidad && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <Avatar proveedorId={oportunidad} className="size-10" />
              <div className="space-y-1">
                <CardDescription>Oportunidad de negociación</CardDescription>
                <CardTitle className="text-lg">
                  Con {nombreProveedor(oportunidad)}
                  {brecha > 0 ? ` pagás ${pesos(brecha)} más que el mejor precio cotizado` : " hay margen para mejorar"}
                </CardTitle>
              </div>
            </div>
            <CardAction>
              <Button size="lg" onClick={() => negociar(oportunidad)}>
                <HandshakeIcon /> Negociar con {nombreProveedor(oportunidad)}
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="text-muted-foreground">
            Antes de escribirle, Abasto ensaya la negociación contra un gemelo digital del proveedor y te propone el mensaje.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FilaAsignacion({ a, demo, cotizaciones }: { a: Asignacion; demo: PedidoDemo; cotizaciones: Cotizacion[] }) {
  const producto = demo.catalogo.find((p) => p.id === a.producto_id);
  const cot = cotizaciones.find((c) => c.proveedor_id === a.proveedor_id);
  const item = cot?.items.find((i) => i.producto_id === a.producto_id);
  const motivo = porQueNoElMasBarato(a, demo, cotizaciones);
  return (
    <TableRow className={motivo ? "bg-amber-50/60 hover:bg-amber-50 dark:bg-amber-950/30" : undefined}>
      <TableCell className="py-4 pl-6 align-top whitespace-normal">
        <p className="font-medium">{producto?.nombre ?? a.producto_id}</p>
        {motivo && (
          <div className="mt-1.5 max-w-sm space-y-1">
            <Etiqueta tono="ambar">
              <TriangleAlertIcon /> No es el más barato
            </Etiqueta>
            <p className="text-amber-900 dark:text-amber-200">{motivo}</p>
          </div>
        )}
      </TableCell>
      <TableCell className="py-4 align-top whitespace-normal">
        <div className="flex items-center gap-2">
          <Avatar proveedorId={a.proveedor_id} className="size-6 text-[9px]" />
          <span className="font-medium">{nombreProveedor(a.proveedor_id)}</span>
        </div>
        {item && cot && (
          <Link
            to={`/cotizaciones#${cot.id}`}
            title={item.conversion_aplicada ?? undefined}
            className="mt-1 block max-w-xs truncate text-xs text-muted-foreground italic hover:text-foreground"
          >
            “{item.evidencia}”
          </Link>
        )}
      </TableCell>
      <TableCell className="py-4 text-right align-top tabular-nums">
        {formatNumero(a.cantidad)} {unidad(producto?.unidad_canonica ?? "unidad", a.cantidad)}
      </TableCell>
      <TableCell className="py-4 text-right align-top tabular-nums">{precioUnitario(a.precio_unitario_sin_iva)}</TableCell>
      <TableCell className="py-4 pr-6 text-right align-top font-medium tabular-nums">{pesos(a.subtotal)}</TableCell>
    </TableRow>
  );
}

/** Si había un precio más barato que no se eligió, explica por qué con los datos de las cotizaciones. */
function porQueNoElMasBarato(a: Asignacion, demo: PedidoDemo, cotizaciones: Cotizacion[]): string | null {
  const linea = demo.pedido.lineas.find((l) => l.producto_id === a.producto_id);
  const candidatos = cotizaciones.flatMap((c) =>
    c.items.filter((i) => i.producto_id === a.producto_id).map((i) => ({ c, i })),
  );
  const barato = candidatos.sort((x, y) => x.i.precio_unitario_sin_iva - y.i.precio_unitario_sin_iva)[0];
  if (!linea || !barato || barato.c.proveedor_id === a.proveedor_id) return null;
  if (barato.i.precio_unitario_sin_iva >= a.precio_unitario_sin_iva - 0.5) return null;

  const nombre = nombreProveedor(barato.c.proveedor_id);
  const precio = precioUnitario(barato.i.precio_unitario_sin_iva);
  const dias = diasEntre(demo.pedido.fecha ?? new Date().toISOString().slice(0, 10), linea.necesario_para);
  if ((barato.i.cantidad_minima ?? 0) > linea.cantidad)
    return `${nombre} cotiza ${precio}, pero exige un mínimo de ${barato.i.cantidad_minima} y se necesitan ${linea.cantidad}.`;
  if (barato.c.lead_time_dias > dias)
    return `${nombre} cotiza ${precio}, pero entrega en ${barato.c.lead_time_dias} días y se necesita en ${dias}.`;
  if (barato.c.pedido_minimo_total)
    return `${nombre} cotiza ${precio}, pero tiene un pedido mínimo de ${pesos(barato.c.pedido_minimo_total)}.`;
  return `${nombre} cotiza ${precio}; sumando envío, confiabilidad y plazo de pago conviene ${nombreProveedor(a.proveedor_id)}.`;
}

/** Lo que se paga de más a un proveedor frente al mejor precio cotizado de cada ítem. */
function brechaProveedor(proveedorId: string, plan: Plan, cotizaciones: Cotizacion[]): number {
  return plan.asignaciones
    .filter((a) => a.proveedor_id === proveedorId)
    .reduce((total, a) => {
      const precios = cotizaciones.flatMap((c) =>
        c.items.filter((i) => i.producto_id === a.producto_id).map((i) => i.precio_unitario_sin_iva),
      );
      const mejor = precios.length ? Math.min(...precios) : a.precio_unitario_sin_iva;
      return total + Math.max(0, a.precio_unitario_sin_iva - mejor) * a.cantidad;
    }, 0);
}
