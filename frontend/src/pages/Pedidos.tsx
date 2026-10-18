// Listado de pedidos (RF-12, RF-05): en trámite, recibidos y todos, con buscador y filtros.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ClipboardListIcon, PlusIcon, SearchIcon, XIcon } from "lucide-react";
import { Encabezado, ErrorBanner } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listarPedidos } from "@/features/pedidos/api";
import {
  BadgeEstado,
  CLIENTE,
  ESTADOS,
  ETIQUETA_ESTADO,
  Marca,
  ORIGEN,
  Origen,
  diaHora,
  textoProductos,
} from "@/features/pedidos/presentacion";
import type { FiltrosPedidos, ListadoPedidos, ResumenPedido, Situacion } from "@/features/pedidos/types";
import { Campo, ListaPestanas, Pestana, Pestanas, Selector } from "@/features/pedidos/ui";
import { mensajeError } from "@/lib/errores";
import { usePolling } from "@/lib/usePolling";

const CLAVES = ["q", "estado", "cliente_interno", "origen", "desde", "hasta"] as const;

function leerFiltros(params: URLSearchParams): FiltrosPedidos {
  const situacion = params.get("situacion");
  return {
    q: params.get("q") ?? "",
    estado: (params.get("estado") ?? "") as FiltrosPedidos["estado"],
    cliente_interno: (params.get("cliente_interno") ?? "") as FiltrosPedidos["cliente_interno"],
    origen: (params.get("origen") ?? "") as FiltrosPedidos["origen"],
    desde: params.get("desde") ?? "",
    hasta: params.get("hasta") ?? "",
    situacion: situacion === "recibidos" || situacion === "todos" ? situacion : "en_tramite",
  };
}

function Proveedores({ nombres }: { nombres: string[] }) {
  if (!nombres.length) return <span className="text-muted-foreground">—</span>;
  if (nombres.length <= 2) return <>{nombres.join(", ")}</>;
  return <span title={nombres.join(", ")}>{nombres.length} proveedores</span>;
}

function Fila({ p, onAbrir }: { p: ResumenPedido; onAbrir: () => void }) {
  return (
    <TableRow className="cursor-pointer" onClick={onAbrir}>
      <TableCell className="pl-4 align-top">
        <Link
          to={`/pedidos/${encodeURIComponent(p.id)}`}
          className="font-medium underline-offset-4 hover:underline"
          onClick={(e) => e.stopPropagation()}
        >
          {p.numero}
        </Link>
        <div className="mt-0.5 flex max-w-56 items-center gap-1.5 text-xs whitespace-normal text-muted-foreground">
          <span className="line-clamp-1">{p.titulo}</span>
        </div>
        {(p.ejemplo || p.demo) && (
          <Marca tono={p.demo ? "azul" : "gris"} className="mt-1">
            {p.demo ? "Pedido de la demo" : "Datos de ejemplo"}
          </Marca>
        )}
      </TableCell>
      <TableCell className="max-w-64 align-top whitespace-normal">{textoProductos(p.productos)}</TableCell>
      <TableCell className="align-top">{CLIENTE[p.cliente_interno]}</TableCell>
      <TableCell className="align-top">
        <Origen origen={p.origen} />
      </TableCell>
      <TableCell className="max-w-48 align-top whitespace-normal">
        <Proveedores nombres={p.proveedores} />
      </TableCell>
      <TableCell className="align-top">
        {p.ordenes.length ? p.ordenes.join(", ") : <span className="text-muted-foreground">—</span>}
      </TableCell>
      <TableCell className="align-top">
        <BadgeEstado estado={p.estado} />
      </TableCell>
      <TableCell className="pr-4 align-top text-muted-foreground tabular-nums">{diaHora(p.actualizado_en)}</TableCell>
    </TableRow>
  );
}

export default function Pedidos() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const filtros = useMemo(() => leerFiltros(params), [params]);
  const [busqueda, setBusqueda] = useState(filtros.q ?? "");
  const [datos, setDatos] = useState<ListadoPedidos | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cambiar = useCallback(
    (cambios: Partial<Record<(typeof CLAVES)[number] | "situacion", string>>) => {
      const nuevos = new URLSearchParams(params);
      for (const [clave, valor] of Object.entries(cambios)) {
        if (valor) nuevos.set(clave, valor);
        else nuevos.delete(clave);
      }
      setParams(nuevos, { replace: true });
    },
    [params, setParams],
  );

  // Buscador: espera a que termine de escribir.
  useEffect(() => {
    if (busqueda === (filtros.q ?? "")) return;
    const id = setTimeout(() => cambiar({ q: busqueda.trim() }), 250);
    return () => clearTimeout(id);
  }, [busqueda, filtros.q, cambiar]);

  const cargar = useCallback(async () => {
    try {
      setDatos(await listarPedidos(filtros));
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [filtros]);

  useEffect(() => {
    setDatos(null);
    cargar();
  }, [cargar]);
  // El pedido de la demo cambia mientras trabaja el agente: refresco suave.
  usePolling(cargar, 5000, true);

  const hayFiltros = CLAVES.some((c) => (filtros[c] ?? "") !== "");
  const ejemplos = datos?.pedidos.filter((p) => p.ejemplo).length ?? 0;

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <Encabezado titulo="Pedidos" bajada="Pedidos en trámite y pedidos procesados con la mercadería recibida.">
        <Button asChild>
          <Link to="/pedidos/nuevo">
            <PlusIcon />
            Nuevo pedido
          </Link>
        </Button>
      </Encabezado>

      <Pestanas value={filtros.situacion} onValueChange={(v) => cambiar({ situacion: v as Situacion })}>
        <ListaPestanas aria-label="Situación de los pedidos">
          <Pestana value="en_tramite">En trámite{datos ? ` · ${datos.conteos.en_tramite}` : ""}</Pestana>
          <Pestana value="recibidos">Recibidos{datos ? ` · ${datos.conteos.recibidos}` : ""}</Pestana>
          <Pestana value="todos">Todos{datos ? ` · ${datos.conteos.todos}` : ""}</Pestana>
        </ListaPestanas>
      </Pestanas>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-64 flex-[3_1_320px]">
            <span className="sr-only">Buscar pedidos</span>
            <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Campo
              type="search"
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por producto, proveedor u orden de compra…"
              className="pl-9"
            />
          </label>
          <div className="flex flex-[1_1_300px] items-center gap-1.5">
            <label className="flex-1">
              <span className="sr-only">Desde</span>
              <Campo
                type="date"
                value={filtros.desde}
                max={filtros.hasta || undefined}
                onChange={(e) => cambiar({ desde: e.target.value })}
                title="Creados desde"
              />
            </label>
            <span className="text-muted-foreground" aria-hidden>
              –
            </span>
            <label className="flex-1">
              <span className="sr-only">Hasta</span>
              <Campo
                type="date"
                value={filtros.hasta}
                min={filtros.desde || undefined}
                onChange={(e) => cambiar({ hasta: e.target.value })}
                title="Creados hasta"
              />
            </label>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Selector
            aria-label="Estado"
            value={filtros.estado}
            onChange={(e) => cambiar({ estado: e.target.value })}
            className="flex-[0_1_220px] min-w-44"
          >
            <option value="">Estado: todos</option>
            {ESTADOS.map((e) => (
              <option key={e} value={e}>
                {ETIQUETA_ESTADO[e]}
              </option>
            ))}
          </Selector>
          <Selector
            aria-label="Cliente interno"
            value={filtros.cliente_interno}
            onChange={(e) => cambiar({ cliente_interno: e.target.value })}
            className="flex-[0_1_220px] min-w-44"
          >
            <option value="">Cliente interno: todos</option>
            <option value="ventas">Ventas</option>
            <option value="personal">Personal</option>
          </Selector>
          <Selector
            aria-label="Origen"
            value={filtros.origen}
            onChange={(e) => cambiar({ origen: e.target.value })}
            className="flex-[0_1_200px] min-w-40"
          >
            <option value="">Origen: todos</option>
            {Object.entries(ORIGEN).map(([valor, { etiqueta }]) => (
              <option key={valor} value={valor}>
                {etiqueta}
              </option>
            ))}
          </Selector>
          {hayFiltros && (
            <Button
              variant="ghost"
              onClick={() => {
                setBusqueda("");
                cambiar({ q: "", estado: "", cliente_interno: "", origen: "", desde: "", hasta: "" });
              }}
            >
              <XIcon />
              Limpiar
            </Button>
          )}
        </div>
      </div>

      {error && <ErrorBanner mensaje={error} onReintentar={cargar} />}

      {!datos && !error ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando pedidos…
        </div>
      ) : datos && datos.pedidos.length === 0 ? (
        <Empty className="border bg-background">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ClipboardListIcon />
            </EmptyMedia>
            <EmptyTitle>No hay pedidos para mostrar</EmptyTitle>
            <EmptyDescription>
              {hayFiltros
                ? "Ningún pedido coincide con la búsqueda y los filtros."
                : filtros.situacion === "recibidos"
                  ? "Todavía no hay pedidos con la mercadería recibida."
                  : "No hay pedidos en trámite."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        datos && (
          <Card className="py-0">
            <Table className="min-w-[980px]">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-11 pl-4">Pedido</TableHead>
                  <TableHead>Productos</TableHead>
                  <TableHead>Cliente interno</TableHead>
                  <TableHead>Origen</TableHead>
                  <TableHead>Proveedor</TableHead>
                  <TableHead>Orden de compra</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="pr-4">Actualizado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {datos.pedidos.map((p) => (
                  <Fila key={p.id} p={p} onAbrir={() => navigate(`/pedidos/${encodeURIComponent(p.id)}`)} />
                ))}
              </TableBody>
            </Table>
          </Card>
        )
      )}

      {datos && datos.pedidos.length > 0 && (
        <p className="text-sm text-muted-foreground">
          {datos.total} {datos.total === 1 ? "pedido" : "pedidos"}
          {ejemplos > 0 && ` · ${ejemplos} con datos de ejemplo (no son compras reales)`}
        </p>
      )}
    </div>
  );
}
