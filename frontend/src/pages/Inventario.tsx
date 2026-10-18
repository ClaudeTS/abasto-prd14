import { useCallback, useEffect, useState } from "react";
import { BotIcon, UserIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { fechaCorta, formatNumero, pesos, unidad } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Encabezado, ErrorBanner, Etiqueta } from "@/components/comunes";
import type { Inventario, ItemInventario } from "@/types";

// Lo que el agente mira para reponer, y donde la persona decide qué puede comprar solo (modo y tope).

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"];
const mesCorto = (m: string) => `${MESES[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`;

export default function InventarioPage() {
  const [horizonte, setHorizonte] = useState(1);
  const [inventario, setInventario] = useState<Inventario | null>(null);
  const [elegido, setElegido] = useState<string>("resma_a4");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setInventario(await api.getInventario(horizonte));
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [horizonte]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const cambiar = async (id: string, cambios: Parameters<typeof api.cambiarInventario>[1]) => {
    setGuardando(id);
    try {
      await api.cambiarInventario(id, cambios);
      await cargar();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setGuardando(null);
    }
  };

  const producto = inventario?.productos.find((p) => p.producto_id === elegido && p.historial.length > 0);

  return (
    <div className="space-y-6">
      <Encabezado
        titulo="Inventario"
        bajada="Lo que Abasto mira para reponer: stock, consumo y pronóstico. Acá decidís qué puede comprar solo y hasta qué monto."
      >
        <div className="flex items-center gap-1 rounded-lg border p-1">
          {[1, 2, 3, 6].map((h) => (
            <Button key={h} size="sm" variant={h === horizonte ? "secondary" : "ghost"} onClick={() => setHorizonte(h)}>
              {h} {h === 1 ? "mes" : "meses"}
            </Button>
          ))}
        </div>
      </Encabezado>

      <ErrorBanner mensaje={error} onReintentar={cargar} />

      {!inventario ? (
        !error && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Cargando el inventario…
          </div>
        )
      ) : (
        <>
          <Card className="gap-0 py-0">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-11 pl-6">Producto</TableHead>
                  <TableHead className="text-right">Stock</TableHead>
                  <TableHead className="text-right">Mínimo</TableHead>
                  <TableHead className="text-right">En camino</TableHead>
                  <TableHead>Reposición para {inventario.meses_pronostico.map(mesCorto).join(" y ")}</TableHead>
                  <TableHead className="pr-6">¿Lo compra solo?</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {inventario.productos.map((p) => (
                  <Fila
                    key={p.producto_id}
                    p={p}
                    elegido={p.producto_id === elegido}
                    guardando={guardando === p.producto_id}
                    onElegir={() => setElegido(p.producto_id)}
                    onCambiar={(c) => cambiar(p.producto_id, c)}
                  />
                ))}
              </TableBody>
            </Table>
          </Card>

          {producto && <GraficoConsumo producto={producto} />}

          <p className="text-sm text-muted-foreground">
            Con el piloto automático prendido, el agente aprueba todo igual; estos modos y topes valen cuando lo apagás.
            Hoy es {fechaCorta(inventario.fecha)}: lo antes que puede llegar algo es en {inventario.plazo_minimo_dias} días.
          </p>
        </>
      )}
    </div>
  );
}

function Fila({
  p,
  elegido,
  guardando,
  onElegir,
  onCambiar,
}: {
  p: ItemInventario;
  elegido: boolean;
  guardando: boolean;
  onElegir: () => void;
  onCambiar: (c: Parameters<typeof api.cambiarInventario>[1]) => void;
}) {
  const [tope, setTope] = useState(p.tope_automatico_uyu === null ? "" : String(p.tope_automatico_uyu));
  useEffect(() => setTope(p.tope_automatico_uyu === null ? "" : String(p.tope_automatico_uyu)), [p.tope_automatico_uyu]);
  const u = (n: number) => `${formatNumero(n)} ${unidad(p.unidad, n)}`;
  const guardarTope = () => {
    const valor = tope.trim() === "" ? null : Number(tope.replace(/\./g, ""));
    if (valor !== null && (Number.isNaN(valor) || valor < 0)) return;
    if (valor !== p.tope_automatico_uyu) onCambiar({ tope_automatico_uyu: valor });
  };

  return (
    <TableRow
      onClick={p.historial.length ? onElegir : undefined}
      className={cn(p.historial.length && "cursor-pointer", elegido && p.historial.length && "bg-muted/50")}
    >
      <TableCell className="py-3 pl-6 align-top whitespace-normal">
        <p className="font-medium">{p.nombre}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          <Etiqueta>{p.tipo === "consumible" ? "Consumible" : "Equipamiento"}</Etiqueta>
          {p.alerta === "bajo_minimo" && <Etiqueta tono="rojo">Bajo el mínimo</Etiqueta>}
          {p.alerta === "reponer" && <Etiqueta tono="ambar">Reponer</Etiqueta>}
        </div>
      </TableCell>
      <TableCell className="text-right align-top tabular-nums">{u(p.stock_actual)}</TableCell>
      <TableCell className="text-right align-top tabular-nums">{u(p.stock_minimo)}</TableCell>
      <TableCell className="text-right align-top tabular-nums">{p.en_camino ? u(p.en_camino) : "—"}</TableCell>
      <TableCell className="max-w-sm align-top whitespace-normal">
        {p.reposicion ? (
          <>
            <p className="font-medium tabular-nums">
              {p.reposicion.cantidad > 0 ? `${u(p.reposicion.cantidad)} para el ${fechaCorta(p.reposicion.necesario_para)}` : "Alcanza"}
            </p>
            <p className="text-xs text-muted-foreground">{p.reposicion.evidencia}</p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">Se compra cuando se pide</p>
        )}
      </TableCell>
      <TableCell className="pr-6 align-top" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <Switch
            checked={p.modo === "automatico"}
            disabled={guardando}
            onCheckedChange={(v) => onCambiar({ modo: v ? "automatico" : "manual" })}
            aria-label={`Comprar ${p.nombre_corto} solo`}
          />
          <span className="flex items-center gap-1 text-sm">
            {p.modo === "automatico" ? <BotIcon className="size-3.5" /> : <UserIcon className="size-3.5" />}
            {p.modo === "automatico" ? "Automático" : "Manual"}
          </span>
          {guardando && <Spinner className="size-3.5" />}
        </div>
        {p.modo === "automatico" && (
          <label className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            Tope $
            <Input
              value={tope}
              onChange={(e) => setTope(e.target.value)}
              onBlur={guardarTope}
              onKeyDown={(e) => e.key === "Enter" && guardarTope()}
              placeholder="sin tope"
              inputMode="numeric"
              className="h-7 w-24 text-xs tabular-nums"
              disabled={guardando}
            />
          </label>
        )}
        {p.modo === "automatico" && p.tope_automatico_uyu !== null && (
          <p className="mt-1 text-xs text-muted-foreground">Hasta {pesos(p.tope_automatico_uyu)} + IVA por compra</p>
        )}
      </TableCell>
    </TableRow>
  );
}

/** 24 meses de consumo y el pronóstico punteado: ahí se ve la estacionalidad. */
function GraficoConsumo({ producto }: { producto: ItemInventario }) {
  const hist = producto.historial;
  const pron = producto.pronostico?.meses ?? [];
  const puntos = [...hist.map((h) => ({ mes: h.mes, v: h.cantidad, prevision: false })), ...pron.map((m) => ({ mes: m.mes, v: m.cantidad, prevision: true }))];
  const W = 720;
  const H = 220;
  const pad = { l: 44, r: 16, t: 16, b: 28 };
  const max = Math.max(...puntos.map((p) => p.v)) * 1.1 || 1;
  const x = (i: number) => pad.l + (i / Math.max(1, puntos.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  const linea = (desde: number, hasta: number) =>
    puntos
      .slice(desde, hasta)
      .map((p, k) => `${k ? "L" : "M"}${x(desde + k)},${y(p.v)}`)
      .join(" ");
  const ticks = [0, max / 2, max * 0.95].map((v) => Math.round(v / 10) * 10);
  const u = unidad(producto.unidad, 2);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Consumo de {producto.nombre_corto}</CardTitle>
        <CardDescription>
          {u.charAt(0).toUpperCase() + u.slice(1)} por mes, últimos 24 meses{pron.length ? "; punteado, el pronóstico" : ""}.{" "}
          {producto.pronostico?.evidencia}
        </CardDescription>
      </CardHeader>
      <div className="px-6 pb-6">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-foreground" role="img" aria-label={`Consumo mensual de ${producto.nombre_corto}`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth="1" />
              <text x={pad.l - 8} y={y(t) + 4} textAnchor="end" fontSize="11" className="fill-muted-foreground">
                {formatNumero(t)}
              </text>
            </g>
          ))}
          {puntos.map((p, i) =>
            i % 3 === 0 || p.prevision ? (
              <text
                key={p.mes}
                x={x(i)}
                y={H - 8}
                textAnchor={i === puntos.length - 1 ? "end" : i === 0 ? "start" : "middle"}
                fontSize="11"
                className="fill-muted-foreground"
              >
                {mesCorto(p.mes)}
              </text>
            ) : null,
          )}
          {pron.length > 0 && (
            <path d={linea(hist.length - 1, puntos.length)} fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="5 4" opacity="0.6" />
          )}
          <path d={linea(0, hist.length)} fill="none" stroke="currentColor" strokeWidth="2" />
          {puntos.map((p, i) => (
            <circle
              key={p.mes}
              cx={x(i)}
              cy={y(p.v)}
              r={p.prevision ? 4.5 : 3}
              className={p.prevision ? "fill-background" : "fill-current"}
              stroke="currentColor"
              strokeWidth={p.prevision ? 2 : 0}
            >
              <title>{`${mesCorto(p.mes)}: ${formatNumero(p.v)} ${u}${p.prevision ? " (pronóstico)" : ""}`}</title>
            </circle>
          ))}
        </svg>
      </div>
    </Card>
  );
}
