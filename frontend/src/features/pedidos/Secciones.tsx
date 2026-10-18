// Pestañas Resumen, Cotizaciones y Negociación del detalle del pedido (RF-10).
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRightIcon, HandshakeIcon, InboxIcon } from "lucide-react";
import { Evidencia } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatNumero, monedaOriginal, pesos, plazoPago, porcentaje, precioUnitario } from "@/lib/format";
import {
  BadgeEstado,
  CANAL,
  CLIENTE,
  ORIGEN,
  Marca,
  cantidadConUnidad,
  diaHora,
  fechaHoraLarga,
  fechaLarga,
} from "./presentacion";
import type { CotizacionDetalle, DetallePedido, ItemCotizacionDetalle } from "./types";

function Vacio({ icono, titulo, texto }: { icono: ReactNode; titulo: string; texto: string }) {
  return (
    <Empty className="border bg-background">
      <EmptyHeader>
        <EmptyMedia variant="icon">{icono}</EmptyMedia>
        <EmptyTitle>{titulo}</EmptyTitle>
        <EmptyDescription>{texto}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{etiqueta}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

// ─────────── Resumen ───────────
export function Resumen({ pedido }: { pedido: DetallePedido }) {
  const plan = pedido.plan;
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Datos del pedido</CardTitle>
          {pedido.descripcion && <CardDescription>{pedido.descripcion}</CardDescription>}
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-x-6 gap-y-4">
            <Dato etiqueta="Cliente interno">{CLIENTE[pedido.cliente_interno]}</Dato>
            <Dato etiqueta="Origen">{ORIGEN[pedido.origen].etiqueta}</Dato>
            <Dato etiqueta="Solicitante">{pedido.solicitante ?? "—"}</Dato>
            <Dato etiqueta="Creado">{fechaHoraLarga(pedido.creado_en)}</Dato>
            <Dato etiqueta="Última actualización">{fechaHoraLarga(pedido.actualizado_en)}</Dato>
            <Dato etiqueta="Se necesita">
              {pedido.necesario_desde
                ? pedido.necesario_hasta && pedido.necesario_hasta !== pedido.necesario_desde
                  ? `Del ${fechaLarga(pedido.necesario_desde)} al ${fechaLarga(pedido.necesario_hasta)}`
                  : fechaLarga(pedido.necesario_desde)
                : "—"}
            </Dato>
          </dl>
          {pedido.motivo_cancelacion && (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
              Motivo de la cancelación: {pedido.motivo_cancelacion}
            </p>
          )}
        </CardContent>
      </Card>

      {plan && (
        <Card>
          <CardHeader>
            <CardTitle>Plan de compra</CardTitle>
            <CardDescription>
              {pesos(plan.costo_total)} + IVA, comprando a {plan.proveedores_usados.join(", ")}
              {plan.ahorro != null && plan.ahorro > 0 && plan.ahorro_pct != null
                ? ` · ahorro de ${pesos(plan.ahorro)} (${porcentaje(plan.ahorro_pct)}) contra comprarle todo al proveedor habitual`
                : ""}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {plan.explicacion && <p className="text-sm">{plan.explicacion}</p>}
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Producto</TableHead>
                  <TableHead>Proveedor</TableHead>
                  <TableHead className="text-right">Cantidad</TableHead>
                  <TableHead className="text-right">Precio sin IVA</TableHead>
                  <TableHead className="text-right">Subtotal</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {plan.asignaciones.map((a) => (
                  <TableRow key={`${a.producto_id}-${a.proveedor_id}`}>
                    <TableCell className="whitespace-normal">{a.nombre}</TableCell>
                    <TableCell>{a.proveedor_nombre}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatNumero(a.cantidad)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {precioUnitario(a.precio_unitario_sin_iva)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{pesos(a.subtotal)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Historial de estados</CardTitle>
          <CardDescription>Por dónde pasó el pedido, con fecha y hora</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="relative ml-1.5 space-y-4 border-l pl-5">
            {pedido.historial_estados.map((e, i) => (
              <li key={`${e.estado}-${i}`} className="relative">
                <span
                  className={cn(
                    "absolute top-1.5 -left-[25px] size-2.5 rounded-full ring-4 ring-card",
                    i === pedido.historial_estados.length - 1 ? "bg-foreground" : "bg-muted-foreground/40",
                  )}
                  aria-hidden
                />
                <div className="flex flex-wrap items-center gap-2">
                  <BadgeEstado estado={e.estado} />
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {e.en ? fechaHoraLarga(e.en) : "sin hora registrada"}
                  </span>
                </div>
                {e.detalle && <p className="mt-1 text-sm text-muted-foreground">{e.detalle}</p>}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </>
  );
}

// ─────────── Cotizaciones ───────────
type Fila = { cot: CotizacionDetalle; item: ItemCotizacionDetalle };

export function Cotizaciones({ pedido }: { pedido: DetallePedido }) {
  if (!pedido.cotizaciones.length) {
    return (
      <Vacio
        icono={<InboxIcon />}
        titulo="Todavía no hay cotizaciones"
        texto="Cuando los proveedores respondan, cada cotización aparece acá normalizada a costo comparable."
      />
    );
  }
  const enPlan = new Set((pedido.plan?.asignaciones ?? []).map((a) => `${a.producto_id}:${a.proveedor_id}`));
  const productos = pedido.lineas.map((l) => ({
    linea: l,
    filas: pedido.cotizaciones
      .flatMap((cot) => cot.items.filter((i) => i.producto_id === l.producto_id).map((item): Fila => ({ cot, item })))
      .sort((a, b) => a.item.precio_unitario_sin_iva - b.item.precio_unitario_sin_iva),
  }));
  return (
    <>
      {productos.map(({ linea, filas }) => (
        <Card key={linea.producto_id}>
          <CardHeader>
            <CardTitle>
              {linea.nombre} · {cantidadConUnidad(linea.cantidad, linea.unidad)}
            </CardTitle>
            <CardDescription>
              Costo comparable: sin IVA, en pesos y por {linea.unidad === "l" ? "litro" : "unidad"}. Ordenado de menor a
              mayor. * Vigencia por defecto (30 días): el proveedor no la indicó.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {filas.length === 0 ? (
              <p className="text-sm text-muted-foreground">Ningún proveedor cotizó este producto todavía.</p>
            ) : (
              <Table className="min-w-[640px]">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Proveedor</TableHead>
                    <TableHead>Cotizó</TableHead>
                    <TableHead className="text-right">Costo comparable</TableHead>
                    <TableHead>Condiciones</TableHead>
                    <TableHead>Vigencia</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filas.map(({ cot, item }) => {
                    const Icono = cot.canal ? CANAL[cot.canal].icono : null;
                    const elegido = enPlan.has(`${item.producto_id}:${cot.proveedor_id}`);
                    return (
                      <TableRow key={cot.id}>
                        <TableCell className="min-w-32 align-top whitespace-normal">
                          <div className="flex items-start gap-1.5 font-medium">
                            {Icono && (
                              <Icono
                                className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
                                aria-label={CANAL[cot.canal!].etiqueta}
                              />
                            )}
                            {cot.proveedor_nombre}
                          </div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {elegido && <Marca tono="verde">En el plan</Marca>}
                            {cot.estado === "revisar" && <Marca tono="ambar">Para revisar</Marca>}
                            {item.cantidad_minima ? (
                              <Marca tono={item.cantidad_minima > linea.cantidad ? "rojo" : "gris"}>
                                Mínimo {formatNumero(item.cantidad_minima)}
                              </Marca>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell className="min-w-48 align-top whitespace-normal">
                          <div className="tabular-nums">
                            {monedaOriginal(item.precio_original, item.moneda_original)}{" "}
                            {item.incluye_iva_original ? "con IVA" : "+ IVA"} · {item.unidad_original}
                          </div>
                          <Evidencia texto={item.evidencia} className="mt-1 text-xs" />
                        </TableCell>
                        <TableCell className="text-right align-top">
                          <div className="font-medium tabular-nums">{precioUnitario(item.precio_unitario_sin_iva)}</div>
                          {item.conversion_aplicada && (
                            <div className="mt-0.5 max-w-56 text-xs whitespace-normal text-muted-foreground">
                              {item.conversion_aplicada}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="min-w-28 align-top whitespace-normal">
                          <div>
                            Entrega{" "}
                            {cot.lead_time_dias != null
                              ? `${cot.lead_time_dias} ${cot.lead_time_dias === 1 ? "día" : "días"}`
                              : "—"}
                          </div>
                          <div className="text-xs text-muted-foreground">{plazoPago(cot.plazo_pago_dias)}</div>
                          {cot.costo_envio > 0 && (
                            <div className="text-xs text-muted-foreground">Envío {pesos(cot.costo_envio)}</div>
                          )}
                        </TableCell>
                        <TableCell
                          className="align-top"
                          title={
                            cot.validez_dias
                              ? "Vigencia que indicó el proveedor"
                              : "El proveedor no la indicó: 30 días por defecto"
                          }
                        >
                          {cot.vigencia_dias} días{cot.validez_dias ? "" : "*"}
                          {cot.vence_el && (
                            <div className="text-xs text-muted-foreground">
                              vence {fechaLarga(cot.vence_el).slice(0, 5)}
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      ))}
      <p className="text-xs text-muted-foreground">
        {pedido.cotizaciones.length}{" "}
        {pedido.cotizaciones.length === 1 ? "cotización recibida" : "cotizaciones recibidas"}
        {pedido.cotizaciones.some((c) => c.recibida_en)
          ? ` · la última, ${diaHora(
              pedido.cotizaciones
                .map((c) => c.recibida_en)
                .filter((f): f is string => !!f)
                .sort()
                .reverse()[0] ?? null,
            )}`
          : ""}
      </p>
    </>
  );
}

// ─────────── Negociación ───────────
const RIESGO = { bajo: "verde", medio: "ambar", alto: "rojo" } as const;
const ESTADO_NEGOCIACION: Record<string, string> = {
  simulada: "Ensayada, espera tu aprobación",
  aprobada: "Aprobada para llamar",
  enviada_simulada: "Aprobada y enviada (simulado)",
};

export function Negociacion({ pedido }: { pedido: DetallePedido }) {
  if (!pedido.negociaciones.length) {
    return (
      <Vacio
        icono={<HandshakeIcon />}
        titulo="Sin negociación"
        texto={
          pedido.plan
            ? "En este pedido no hizo falta negociar: el plan ya tenía el mejor precio disponible."
            : "La negociación se ensaya contra el gemelo del proveedor cuando el plan de compra está listo."
        }
      />
    );
  }
  return (
    <>
      {pedido.negociaciones.map((n) => (
        <Card key={n.id}>
          <CardHeader>
            <CardTitle>Negociación con {n.proveedor_nombre}</CardTitle>
            <CardDescription>
              Ensayo contra el gemelo digital: 3 estrategias. Elegida: «{n.elegida}» ·{" "}
              {ESTADO_NEGOCIACION[n.estado] ?? n.estado}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Estrategia</TableHead>
                  <TableHead className="text-right">Concesión</TableHead>
                  <TableHead className="text-right">Ganancia esperada</TableHead>
                  <TableHead>Riesgo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {n.estrategias.map((e) => (
                  <TableRow key={e.nombre} className={cn(e.nombre === n.elegida && "bg-muted/50")}>
                    <TableCell className="whitespace-normal">
                      <span className="font-medium capitalize">{e.nombre}</span>
                      {e.nombre === n.elegida && (
                        <Marca tono="oscuro" className="ml-2">
                          Elegida
                        </Marca>
                      )}
                      <div className="text-xs text-muted-foreground">{e.descripcion}</div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{porcentaje(e.concesion_obtenida_pct)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {e.ganancia_esperada_uyu != null ? pesos(e.ganancia_esperada_uyu) : "—"}
                    </TableCell>
                    <TableCell>
                      <Marca tono={RIESGO[e.riesgo as keyof typeof RIESGO] ?? "neutro"}>{e.riesgo}</Marca>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">Mensaje propuesto</div>
              <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm whitespace-pre-line">
                {n.mensaje_propuesto}
              </p>
            </div>
            {n.resultado && (
              <p className="text-sm">
                <span className="font-medium">Resultado: </span>
                {n.resultado}
              </p>
            )}
            {pedido.demo && (
              <Button variant="outline" size="sm" asChild className="w-fit">
                <Link to={`/negociacion/${n.proveedor_id}`}>
                  Abrir en la demo guiada
                  <ArrowRightIcon />
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </>
  );
}
