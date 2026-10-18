// Dashboard (home) — RF-09 y KPI de la §4 del PRD 1.4. Mockup: "Abasto · Dashboard".
import { useCallback, useEffect, useState } from "react";
import { CalendarIcon, UsersIcon } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";
import { usePolling } from "@/lib/usePolling";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Etiqueta, ErrorBanner } from "@/components/comunes";
import { descartarRecomendacion, getDashboard, getPedidosRecientes, getRecomendaciones } from "@/features/dashboard/api";
import { saludo } from "@/features/dashboard/formato";
import { PanelPendientes, PanelTiempoPorCanal } from "@/features/dashboard/PanelesLaterales";
import { PanelRecomendaciones } from "@/features/dashboard/PanelRecomendaciones";
import { PedidosRecientes } from "@/features/dashboard/PedidosRecientes";
import { TarjetaKpi } from "@/features/dashboard/TarjetaKpi";
import type {
  ClienteInterno,
  Dashboard,
  FiltrosDashboard,
  PedidoReciente,
  Recomendaciones,
} from "@/features/dashboard/types";

const PERIODOS = [
  { dias: 30, etiqueta: "Últimos 30 días" },
  { dias: 90, etiqueta: "Últimos 90 días" },
  { dias: 180, etiqueta: "Últimos 6 meses" },
  { dias: 365, etiqueta: "Últimos 12 meses" },
];
const CLIENTES: { valor: ClienteInterno | "todos"; etiqueta: string }[] = [
  { valor: "todos", etiqueta: "Todos los clientes internos" },
  { valor: "ventas", etiqueta: "Ventas" },
  { valor: "personal", etiqueta: "Personal" },
];
// Orden de las tarjetas del mockup; el tiempo por canal va en su propio panel.
const ORDEN_KPI = [
  "ahorro_cotizacion_inicial",
  "tasa_compras_automaticas",
  "tiempo_pedido_a_orden",
  "cotizaciones_sin_correccion",
  "precision_gemelo",
  "efectividad_negociacion",
  "tasa_respuesta_proveedores",
  "tiempo_respuesta_pedidos_internos",
];
const REFRESCO_MS = 10_000;

function Selector<T extends string | number>({
  icono,
  etiqueta,
  valor,
  opciones,
  onChange,
}: {
  icono: React.ReactNode;
  etiqueta: string;
  valor: T;
  opciones: { valor: T; etiqueta: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <label className="relative inline-flex h-9 items-center gap-2 rounded-md border bg-background pr-2 pl-2.5 text-sm font-medium shadow-xs focus-within:ring-3 focus-within:ring-ring/50 hover:bg-muted">
      <span className="text-muted-foreground" aria-hidden>
        {icono}
      </span>
      <span className="sr-only">{etiqueta}</span>
      <select
        className="cursor-pointer appearance-none bg-transparent pr-4 outline-none"
        value={String(valor)}
        onChange={(e) => {
          const elegido = opciones.find((o) => String(o.valor) === e.target.value);
          if (elegido) onChange(elegido.valor);
        }}
      >
        {opciones.map((o) => (
          <option key={String(o.valor)} value={String(o.valor)}>
            {o.etiqueta}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute right-2.5 text-xs text-muted-foreground" aria-hidden>
        ▾
      </span>
    </label>
  );
}

export default function Inicio() {
  const { usuario } = useAuth();
  const [filtros, setFiltros] = useState<FiltrosDashboard>({ dias: 30, cliente: "todos" });
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [recos, setRecos] = useState<Recomendaciones | null>(null);
  const [pedidos, setPedidos] = useState<PedidoReciente[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  const cargarDashboard = useCallback(async () => {
    try {
      setDashboard(await getDashboard(filtros));
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [filtros]);

  const cargarResto = useCallback(async () => {
    const [r, p] = await Promise.allSettled([getRecomendaciones(), getPedidosRecientes()]);
    if (r.status === "fulfilled") setRecos(r.value);
    if (p.status === "fulfilled") setPedidos(p.value);
  }, []);

  useEffect(() => {
    setCargando(true);
    cargarDashboard().finally(() => setCargando(false));
  }, [cargarDashboard]);

  // Refresco silencioso: datos del agente que avanzan y la redacción de la IA, que llega en segundo plano.
  usePolling(
    async () => {
      await Promise.all([dashboard ? cargarDashboard() : Promise.resolve(), cargarResto()]);
    },
    REFRESCO_MS,
    true,
  );

  const descartar = async (id: string) => {
    try {
      await descartarRecomendacion(id);
      setRecos((r) => r && { ...r, recomendaciones: r.recomendaciones.filter((x) => x.id !== id), descartadas: r.descartadas + 1 });
    } catch (e) {
      setError(mensajeError(e));
    }
  };

  const periodo = PERIODOS.find((p) => p.dias === filtros.dias)?.etiqueta.toLowerCase() ?? "";
  const cliente =
    filtros.cliente === "todos" ? "Ventas y Personal" : CLIENTES.find((c) => c.valor === filtros.cliente)?.etiqueta;
  const kpis = ORDEN_KPI.map((id) => dashboard?.kpis.find((k) => k.id === id)).filter((k) => k !== undefined);

  return (
    <TooltipProvider delayDuration={150}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">
                {saludo()}
                {usuario ? `, ${usuario.nombre}` : ""}
              </h1>
              {dashboard?.ejemplo && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={0}>
                      <Etiqueta tono="ambar">Datos de ejemplo</Etiqueta>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-72 text-pretty">{dashboard.nota_ejemplo}</TooltipContent>
                </Tooltip>
              )}
            </div>
            <p className="mt-1 text-muted-foreground">
              Resumen de compras · {periodo} · {cliente}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Selector
              icono={<CalendarIcon className="size-4" />}
              etiqueta="Período"
              valor={filtros.dias}
              opciones={PERIODOS.map((p) => ({ valor: p.dias, etiqueta: p.etiqueta }))}
              onChange={(dias) => setFiltros((f) => ({ ...f, dias }))}
            />
            <Selector
              icono={<UsersIcon className="size-4" />}
              etiqueta="Cliente interno"
              valor={filtros.cliente}
              opciones={CLIENTES}
              onChange={(c) => setFiltros((f) => ({ ...f, cliente: c }))}
            />
          </div>
        </div>

        {error && <ErrorBanner mensaje={error} onReintentar={cargarDashboard} />}

        <section aria-label="Indicadores" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          {!dashboard && cargando
            ? ORDEN_KPI.map((id) => <Skeleton key={id} className="h-40 rounded-xl" />)
            : kpis.map((k) => <TarjetaKpi key={k.id} k={k} />)}
        </section>

        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-[3_1_520px]">
            <PanelRecomendaciones datos={recos} cargando={!recos} onDescartar={descartar} />
          </div>
          <div className="flex min-w-0 flex-[2_1_340px] flex-col gap-4">
            {dashboard ? (
              <>
                <PanelPendientes pendientes={dashboard.pendientes} />
                <PanelTiempoPorCanal canales={dashboard.tiempo_por_canal} dias={filtros.dias} />
              </>
            ) : (
              <>
                <Skeleton className="h-40 rounded-xl" />
                <Skeleton className="h-48 rounded-xl" />
              </>
            )}
          </div>
        </div>

        {pedidos && <PedidosRecientes pedidos={pedidos} />}
      </div>
    </TooltipProvider>
  );
}
