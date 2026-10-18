// Proveedores (PRD 1.4 §7, RF-17 y RF-19): listado con perfil de negociación, perfil completo y altas.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { PlusIcon, SearchIcon } from "lucide-react";
import { mensajeError } from "@/lib/errores";
import { formatNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Encabezado, ErrorBanner, Etiqueta } from "@/components/comunes";
import * as api from "@/features/proveedores/api";
import AltaProveedor from "@/features/proveedores/AltaProveedor";
import PerfilProveedor from "@/features/proveedores/PerfilProveedor";
import { BadgeConfianza, DatosEjemplo, Selector, nombreCanal } from "@/features/proveedores/comunes";
import type { Listado, NivelConfianza, ProveedorListado } from "@/features/proveedores/types";

const rubroCorto = (r: string) => r.split("/")[0].trim();
const capital = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

export default function Proveedores() {
  const { proveedorId } = useParams();
  const navigate = useNavigate();
  const [listado, setListado] = useState<Listado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [rubro, setRubro] = useState("todos");
  const [confianza, setConfianza] = useState<NivelConfianza | "todas">("todas");
  const [altaAbierta, setAltaAbierta] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setError(null);
      setListado(await api.listarProveedores());
    } catch (e) {
      setError(mensajeError(e));
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const proveedores = listado?.proveedores ?? [];
  const rubros = useMemo(() => [...new Set(proveedores.map((p) => rubroCorto(p.rubro)).filter(Boolean))].sort(), [proveedores]);
  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return proveedores.filter(
      (p) =>
        (rubro === "todos" || rubroCorto(p.rubro) === rubro) &&
        (confianza === "todas" || p.confianza.nivel === confianza) &&
        (!q || [p.nombre, p.rubro, ...p.productos].some((t) => t.toLowerCase().includes(q))),
    );
  }, [proveedores, busqueda, rubro, confianza]);

  const seleccionado = proveedorId ?? filtrados[0]?.id ?? proveedores[0]?.id;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5">
      <Encabezado
        titulo="Proveedores"
        bajada="Condiciones, desempeño y perfil de negociación de cada proveedor. El agente también puede darlos de alta."
      >
        <Button onClick={() => setAltaAbierta(true)}>
          <PlusIcon /> Alta de proveedor
        </Button>
      </Encabezado>

      <ErrorBanner mensaje={error} onReintentar={cargar} />

      <div className="flex flex-wrap gap-2">
        <label className="flex h-9 min-w-0 flex-[3_1_18rem] items-center gap-2 rounded-md border bg-background px-3 text-muted-foreground shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50">
          <SearchIcon className="size-4 shrink-0" aria-hidden />
          <input
            type="search"
            aria-label="Buscar proveedores"
            placeholder="Buscar por nombre, rubro o producto…"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            className="w-full min-w-0 bg-transparent text-sm text-foreground outline-none"
          />
        </label>
        <Selector aria-label="Rubro" value={rubro} onChange={(e) => setRubro(e.target.value)} className="w-auto flex-[1_1_11rem] bg-background">
          <option value="todos">Rubro: todos</option>
          {rubros.map((r) => (
            <option key={r} value={r}>
              {capital(r)}
            </option>
          ))}
        </Selector>
        <Selector
          aria-label="Confianza"
          value={confianza}
          onChange={(e) => setConfianza(e.target.value as NivelConfianza | "todas")}
          className="w-auto flex-[1_1_11rem] bg-background"
        >
          <option value="todas">Confianza: todas</option>
          <option value="alta">Alta</option>
          <option value="media">Media</option>
          <option value="baja">Baja</option>
          <option value="sin_datos">Sin datos</option>
        </Selector>
      </div>

      <div className="overflow-hidden rounded-xl border bg-background">
        {!listado && !error ? (
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 6 }, (_, k) => (
              <Skeleton key={k} className="h-10" />
            ))}
          </div>
        ) : (
          <Table className="min-w-[960px]">
            <TableHeader>
              <TableRow>
                {["Proveedor", "Rubro", "Canal preferido", "Antigüedad", "Cumplimiento", "Sensible a", "Concesión típica", "Confianza del perfil"].map(
                  (h) => (
                    <TableHead key={h} className="px-3.5 text-muted-foreground">
                      {h}
                    </TableHead>
                  ),
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtrados.map((p) => (
                <Fila
                  key={p.id}
                  p={p}
                  activa={p.id === seleccionado}
                  onClick={() => navigate(`/proveedores/${p.id}`, { replace: !!proveedorId })}
                />
              ))}
              {filtrados.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                    Ningún proveedor coincide con la búsqueda.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </div>
      <DatosEjemplo>
        Antigüedad, cumplimiento y el historial de negociaciones previas son ilustrativos. Confianza = desvío promedio
        entre la concesión simulada por el gemelo y la real: alta hasta ±{listado?.umbrales_confianza.alta_pp ?? 2} pp, media
        hasta ±{listado?.umbrales_confianza.media_pp ?? 5} pp, baja con más de ±5 pp o menos de{" "}
        {listado?.umbrales_confianza.min_negociaciones ?? 3} negociaciones.
      </DatosEjemplo>

      {seleccionado && <PerfilProveedor key={seleccionado} proveedorId={seleccionado} onCambio={cargar} />}

      <AltaProveedor
        open={altaAbierta}
        onOpenChange={setAltaAbierta}
        onCreado={(a) => {
          cargar();
          navigate(`/proveedores/${a.id}`);
        }}
      />
    </div>
  );
}

function Fila({ p, activa, onClick }: { p: ProveedorListado; activa: boolean; onClick: () => void }) {
  return (
    <TableRow
      data-state={activa ? "selected" : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      tabIndex={0}
      aria-selected={activa}
      className={cn("cursor-pointer align-top [&>td]:px-3.5 [&>td]:py-3", activa && "bg-muted/60")}
    >
      <TableCell className="whitespace-normal">
        <div className="font-medium">{p.nombre}</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {p.habitual && <span className="text-xs text-muted-foreground">habitual</span>}
          {p.alta_por === "agente" && <Etiqueta tono="azul">Alta por el agente</Etiqueta>}
          {p.estado === "en_revision" && <Etiqueta tono="ambar">En revisión</Etiqueta>}
          {p.estado === "rechazado" && <Etiqueta tono="rojo">Rechazado</Etiqueta>}
        </div>
      </TableCell>
      <TableCell className="max-w-56 whitespace-normal">{capital(p.rubro.replace(" / ", " · ")) || "—"}</TableCell>
      <TableCell>{nombreCanal(p.canal_preferido)}</TableCell>
      <TableCell>{p.antiguedad.texto}</TableCell>
      <TableCell className="tabular-nums">
        {p.cumplimiento_historico_pct !== null ? `${formatNumero(p.cumplimiento_historico_pct)} %` : <span className="text-muted-foreground">—</span>}
      </TableCell>
      <TableCell className="max-w-60 whitespace-normal">
        {p.perfil?.sensible_a.length ? (
          capital(p.perfil.sensible_a.join(", "))
        ) : (
          <span className="text-muted-foreground">sin historial</span>
        )}
      </TableCell>
      <TableCell className="tabular-nums">
        {p.perfil?.concesion_tipica_rango ?? <span className="text-muted-foreground">—</span>}
      </TableCell>
      <TableCell>
        <BadgeConfianza c={p.confianza} />
      </TableCell>
    </TableRow>
  );
}
