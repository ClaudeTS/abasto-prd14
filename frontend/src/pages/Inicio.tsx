// Dashboard (home) — RF-09 y KPI de la §4 del PRD 1.4. Mockup: "Abasto · Dashboard".
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarIcon, MicIcon, UsersIcon } from "lucide-react";
import Facetas from "@/components/Facetas";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";
import { usePolling } from "@/lib/usePolling";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Etiqueta, ErrorBanner } from "@/components/comunes";
import { descartarRecomendacion, getDashboard, getPedidosRecientes, getRecomendaciones } from "@/features/dashboard/api";
import { saludo, valorKpi } from "@/features/dashboard/formato";
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
    <label className="relative inline-flex h-9 items-center gap-2 rounded-full border bg-card pr-3 pl-3 text-sm font-medium shadow-xs focus-within:ring-3 focus-within:ring-ring/50 hover:bg-muted">
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
  const ahorro = dashboard?.kpis.find((k) => k.id === "ahorro_cotizacion_inicial");
  const kpis = ORDEN_KPI.map((id) => dashboard?.kpis.find((k) => k.id === id)).filter((k) => k !== undefined);

  return (
    <TooltipProvider delayDuration={150}>
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        {/* Hero oscuro con las facetas de la portada (plantilla institucional) */}
        <section
          aria-label="Resumen"
          className="relative isolate flex flex-wrap items-center justify-between gap-6 overflow-hidden rounded-2xl bg-negro px-6 py-6 text-white sm:px-7"
        >
          <Facetas className="-z-10 opacity-35 sm:opacity-100" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex h-6 items-center rounded-full border border-[#4a5053] px-3 text-[11px] font-bold tracking-[0.14em] text-gris-claro uppercase">
                {periodo} · {cliente}
              </span>
              {dashboard?.ejemplo && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span tabIndex={0}>
                      <Etiqueta tono="ejemplo">Datos de ejemplo</Etiqueta>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-72 text-pretty">{dashboard.nota_ejemplo}</TooltipContent>
                </Tooltip>
              )}
            </div>
            <h1 className="mt-3 text-3xl tracking-tight">
              {saludo()}
              {usuario ? (
                <>
                  , <span className="text-celeste">{usuario.nombre}</span>
                </>
              ) : (
                ""
              )}
            </h1>
            <p className="mt-1 text-gris-oscuro">Esto pasó con tus compras</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button asChild className="rounded-full px-4 font-bold">
                <Link to="/pedidos/nuevo">
                  <MicIcon /> Nuevo pedido por voz
                </Link>
              </Button>
              <Button
                asChild
                variant="outline"
                className="rounded-full border-[#4a5053] bg-transparent px-4 text-white hover:bg-white/10 hover:text-white"
              >
                <Link to="/pedidos">Ver pedidos</Link>
              </Button>
            </div>
          </div>
          {dashboard && (
            <dl className="flex flex-wrap gap-x-8 gap-y-3 rounded-xl bg-negro/75 px-4 py-3 backdrop-blur-sm">
              {ahorro && ahorro.valor !== null && (
                <div>
                  <dd className="font-heading text-3xl font-bold text-celeste tabular-nums">
                    {valorKpi(ahorro.valor, ahorro.unidad, ahorro.id)}
                  </dd>
                  <dt className="text-xs text-gris-oscuro">ahorro contra la cotización inicial</dt>
                </div>
              )}
              <div>
                <dd className="font-heading text-3xl font-bold tabular-nums">{dashboard.pendientes.length}</dd>
                <dt className="text-xs text-gris-oscuro">esperan tu aprobación</dt>
              </div>
              {recos && (
                <div>
                  <dd className="font-heading text-3xl font-bold tabular-nums">{recos.recomendaciones.length}</dd>
                  <dt className="text-xs text-gris-oscuro">recomendaciones de la IA</dt>
                </div>
              )}
            </dl>
          )}
        </section>

        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-xl tracking-tight">
            El período <span className="text-celeste-ink">en números</span>
          </h2>
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
