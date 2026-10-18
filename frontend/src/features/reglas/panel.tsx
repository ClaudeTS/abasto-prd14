// Piezas del panel de reglas por producto (PRD 1.4 §11.4, mockup Reglas).
import { useMemo, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  HistoryIcon,
  InfoIcon,
  PlusIcon,
  RotateCcwIcon,
  SearchIcon,
  TriangleAlertIcon,
  XIcon,
} from "lucide-react";
import { Etiqueta, Evidencia } from "@/components/comunes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fechaCorta, formatNumero, hora } from "@/lib/format";
import { PROVEEDORES, nombreProveedor } from "@/lib/proveedores";
import { cn } from "@/lib/utils";
import type { Borrador, ProveedorBorrador } from "./borrador";
import { Campo, Input, InputNumero, Label, Select, Switch } from "./campos";
import type { CambioRegla, Contexto, VistaPrevia, VistaReglas } from "./types";

export const u = (unidad: string) => (unidad === "l" ? "L" : unidad === "kg" ? "kg" : "u.");
export const pesos = (n: number) => `$ ${formatNumero(n, Math.round(n * 100) % 100 ? 2 : 0)}`;
export const fechaHora = (iso: string) => `${fechaCorta(iso)} ${hora(iso)}`;

type Set = <K extends keyof Borrador>(campo: K, valor: Borrador[K]) => void;

// ─────────── Buscador ───────────
export function BuscadorProducto({
  productos,
  actual,
  onElegir,
}: {
  productos: VistaReglas[];
  actual: VistaReglas | null;
  onElegir: (productoId: string) => void;
}) {
  const [texto, setTexto] = useState("");
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  const filtrados = useMemo(() => {
    const q = texto.trim().toLowerCase();
    return productos.filter((p) => !q || `${p.nombre} ${p.producto_id} ${p.nombre_corto}`.toLowerCase().includes(q));
  }, [productos, texto]);
  const elegir = (id: string) => {
    setAbierto(false);
    setTexto("");
    onElegir(id);
  };
  return (
    <div
      ref={caja}
      className="relative"
      onBlur={(e) => {
        if (!caja.current?.contains(e.relatedTarget as Node)) setAbierto(false);
      }}
    >
      <SearchIcon className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" aria-hidden />
      <Input
        id="producto"
        role="combobox"
        aria-expanded={abierto}
        aria-controls="lista-productos"
        autoComplete="off"
        className="pl-9"
        placeholder={actual ? `${actual.nombre} · ${actual.producto_id}` : "Buscá por nombre o código"}
        value={texto}
        onFocus={() => setAbierto(true)}
        onChange={(e) => {
          setTexto(e.target.value);
          setAbierto(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && filtrados[0]) elegir(filtrados[0].producto_id);
          if (e.key === "Escape") setAbierto(false);
        }}
      />
      {abierto && (
        <ul
          id="lista-productos"
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border bg-popover p-1 text-sm shadow-md"
        >
          {filtrados.length === 0 && <li className="px-2 py-1.5 text-muted-foreground">Ningún producto coincide.</li>}
          {filtrados.map((p) => (
            <li key={p.producto_id}>
              <button
                type="button"
                role="option"
                aria-selected={p.producto_id === actual?.producto_id}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => elegir(p.producto_id)}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-sm px-2 py-1.5 text-left hover:bg-muted",
                  p.producto_id === actual?.producto_id && "bg-muted",
                )}
              >
                <span className="min-w-0 truncate">
                  {p.nombre} <span className="text-muted-foreground">· {p.producto_id}</span>
                </span>
                {p.reglas.compra_automatica ? <Etiqueta tono="verde">Automática</Etiqueta> : <Etiqueta>Manual</Etiqueta>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─────────── Vista previa del efecto ───────────
export function AvisoVistaPrevia({ vista, cargando, hayCambios }: { vista: VistaPrevia | null; cargando: boolean; hayCambios: boolean }) {
  const alerta = vista && (!vista.valido || vista.aprobacion === "requiere_aprobacion" || vista.bajo_tope === false);
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex gap-3 rounded-xl border px-4 py-3.5 text-sm",
        alerta
          ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
          : "border-sky-200 bg-sky-50 text-sky-950 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100",
      )}
    >
      {alerta ? <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden /> : <InfoIcon className="mt-0.5 size-4 shrink-0" aria-hidden />}
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2 font-semibold">
          Vista previa del efecto
          {hayCambios ? <Badge variant="secondary">Con tus cambios sin guardar</Badge> : <Badge variant="outline">Reglas guardadas</Badge>}
          {cargando && <Spinner className="size-3.5" />}
        </div>
        <p className={cn(cargando && "opacity-60")}>{vista ? vista.texto : "Calculando…"}</p>
        {vista?.evidencia && <p className="text-xs opacity-80">Cuenta: {vista.evidencia}</p>}
      </div>
    </div>
  );
}

// ─────────── Reposición ───────────
export function TarjetaReposicion({
  b,
  set,
  vista,
  errores,
  soloLectura,
}: {
  b: Borrador;
  set: Set;
  vista: VistaReglas;
  errores: Record<string, string>;
  soloLectura: boolean;
}) {
  const ctx = vista.contexto;
  const un = u(vista.unidad);
  const equipamiento = vista.tipo === "equipamiento";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Reposición</CardTitle>
        <CardDescription>Si está activada, el agente compra sin aprobación dentro del tope.</CardDescription>
        <CardAction>
          <div className="flex items-center gap-2.5">
            <Switch
              id="compra-automatica"
              checked={b.compra_automatica}
              onCheckedChange={(v) => set("compra_automatica", v)}
              disabled={soloLectura}
            />
            <Label htmlFor="compra-automatica">Compra automática</Label>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        {equipamiento && (
          <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
            Equipamiento: se compra cuando alguien lo pide. El stock mínimo, el base y la zafra aplican a los consumibles.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id="stock-minimo" etiqueta="Stock mínimo" error={errores.stock_minimo} ayuda={`Dispara la reposición · hoy hay ${formatNumero(ctx.stock_actual)} ${un}`}>
            <InputNumero id="stock-minimo" valor={b.stock_minimo} onCambio={(v) => set("stock_minimo", v)} sufijo={un} disabled={soloLectura} error={errores.stock_minimo} />
          </Campo>
          <Campo id="stock-base" etiqueta="Stock base" error={errores.stock_base} ayuda="Nivel al que se repone · vacío: pronóstico + mínimo">
            <InputNumero id="stock-base" valor={b.stock_base} onCambio={(v) => set("stock_base", v)} sufijo={un} placeholder="Sin definir" disabled={soloLectura} error={errores.stock_base} />
          </Campo>
          <Campo id="zafra-cantidad" etiqueta="Cantidad de zafra" error={errores.zafra} ayuda={ctx.en_zafra ? "Hoy está dentro de la zafra" : "Se pide al comenzar la zafra"}>
            <InputNumero id="zafra-cantidad" valor={b.zafra_cantidad} onCambio={(v) => set("zafra_cantidad", v)} sufijo={un} placeholder="Sin zafra" disabled={soloLectura} error={errores.zafra} />
          </Campo>
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="zafra-inicio">Período de zafra</Label>
            <div className="flex items-center gap-2">
              <Input id="zafra-inicio" aria-label="Inicio de la zafra (día/mes)" placeholder="01/05" value={b.zafra_inicio} onChange={(e) => set("zafra_inicio", e.target.value)} disabled={soloLectura} aria-invalid={errores.zafra ? true : undefined} />
              <span className="text-muted-foreground">–</span>
              <Input id="zafra-fin" aria-label="Fin de la zafra (día/mes)" placeholder="31/08" value={b.zafra_fin} onChange={(e) => set("zafra_fin", e.target.value)} disabled={soloLectura} aria-invalid={errores.zafra ? true : undefined} />
            </div>
            <span className="text-xs text-muted-foreground">Día/mes, se repite cada año · ej. antigripales en invierno</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────── Tope y condiciones ───────────
export function TarjetaTope({
  b,
  set,
  ctx,
  errores,
  soloLectura,
}: {
  b: Borrador;
  set: Set;
  ctx: Contexto;
  errores: Record<string, string>;
  soloLectura: boolean;
}) {
  const mejor = ctx.mejor_precio;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tope de precio unitario y condiciones</CardTitle>
        <CardDescription>Si el mejor precio supera el tope, el pedido pasa a aprobación.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo
            id="tope-unitario"
            etiqueta="Tope por unidad, sin IVA"
            error={errores.tope_precio_unitario}
            ayuda={mejor ? `Mejor precio vigente: ${pesos(mejor.precio_sin_iva_uyu)} (${mejor.proveedor_nombre})` : "Todavía no hay cotizaciones de este producto"}
          >
            <InputNumero id="tope-unitario" valor={b.tope_precio_unitario} onCambio={(v) => set("tope_precio_unitario", v)} prefijo={b.moneda_tope === "USD" ? "USD" : "$"} placeholder="Sin tope" disabled={soloLectura} error={errores.tope_precio_unitario} />
          </Campo>
          <Campo id="moneda-tope" etiqueta="Moneda del tope" ayuda={b.moneda_tope === "USD" ? `Se compara a ${formatNumero(ctx.tipo_cambio_usd, 2)} $/USD` : "Se compara en pesos, sin IVA"}>
            <Select id="moneda-tope" value={b.moneda_tope} onChange={(e) => set("moneda_tope", e.target.value as Borrador["moneda_tope"])} disabled={soloLectura}>
              <option value="UYU">Pesos (UYU)</option>
              <option value="USD">Dólares (USD)</option>
            </Select>
          </Campo>
          <Campo id="plazo-entrega" etiqueta="Plazo de entrega máximo" error={errores.plazo_entrega_max_dias} ayuda="Solo proveedores que lo garantizan">
            <InputNumero id="plazo-entrega" valor={b.plazo_entrega_max_dias} onCambio={(v) => set("plazo_entrega_max_dias", v)} sufijo="días" placeholder="Sin exigir" disabled={soloLectura} error={errores.plazo_entrega_max_dias} />
          </Campo>
          <Campo id="plazo-pago" etiqueta="Plazo de pago requerido" error={errores.plazo_pago_requerido_dias}>
            <InputNumero id="plazo-pago" valor={b.plazo_pago_requerido_dias} onCambio={(v) => set("plazo_pago_requerido_dias", v)} sufijo="días" placeholder="Sin exigir" disabled={soloLectura} error={errores.plazo_pago_requerido_dias} />
          </Campo>
          <Campo
            id="tope-total"
            etiqueta="Tope del total por producto"
            className="sm:col-span-2"
            error={errores.tope_automatico_uyu}
            ayuda="Sin IVA. El agente tampoco compra solo si el total del producto en la orden lo supera."
          >
            <InputNumero id="tope-total" valor={b.tope_automatico_uyu} onCambio={(v) => set("tope_automatico_uyu", v)} prefijo="$" placeholder="Sin tope" disabled={soloLectura} error={errores.tope_automatico_uyu} />
          </Campo>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────── Proveedores habilitados ───────────
export function TablaProveedores({
  b,
  set,
  ctx,
  unidad,
  error,
  soloLectura,
}: {
  b: Borrador;
  set: Set;
  ctx: Contexto;
  unidad: string;
  error?: string;
  soloLectura: boolean;
}) {
  const [agregar, setAgregar] = useState("");
  const precios = Object.fromEntries(ctx.precios.map((p) => [p.proveedor_id, p]));
  const disponibles = PROVEEDORES.filter((p) => !b.proveedores.some((x) => x.proveedor_id === p.id));
  const cambiar = (i: number, cambio: Partial<ProveedorBorrador>) =>
    set("proveedores", b.proveedores.map((p, k) => (k === i ? { ...p, ...cambio } : p)));
  const mover = (i: number, d: -1 | 1) => {
    const lista = [...b.proveedores];
    [lista[i], lista[i + d]] = [lista[i + d]!, lista[i]!];
    set("proveedores", lista);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Proveedores habilitados</CardTitle>
        <CardDescription>Orden de prioridad, mínimos y unidad de venta para este producto.</CardDescription>
      </CardHeader>
      <CardContent>
        {!soloLectura && (
          <div className="flex flex-wrap items-center gap-2">
            <Select aria-label="Proveedor para agregar" value={agregar} onChange={(e) => setAgregar(e.target.value)} className="h-8 w-56 max-w-full">
              <option value="">Elegí un proveedor…</option>
              {disponibles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </Select>
            <Button
              variant="outline"
              size="sm"
              disabled={!agregar}
              onClick={() => {
                set("proveedores", [...b.proveedores, { proveedor_id: agregar, minimo_compra: "", unidad_venta: "", factor_conversion: "1" }]);
                setAgregar("");
              }}
            >
              <PlusIcon /> Agregar proveedor
            </Button>
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
        <div className="rounded-lg border">
          <Table className="min-w-[640px]">
            <TableHeader>
              <TableRow>
                <TableHead className="w-24">Prioridad</TableHead>
                <TableHead>Proveedor</TableHead>
                <TableHead>Precio vigente</TableHead>
                <TableHead className="w-32">Mínimo de compra</TableHead>
                <TableHead className="w-40">Unidad de venta</TableHead>
                <TableHead className="w-24">Conversión</TableHead>
                {!soloLectura && <TableHead className="w-10" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {b.proveedores.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-6 text-center text-muted-foreground">
                    Sin proveedores habilitados: el agente no tiene a quién pedirle.
                  </TableCell>
                </TableRow>
              )}
              {b.proveedores.map((p, i) => {
                const precio = precios[p.proveedor_id];
                return (
                  <TableRow key={p.proveedor_id}>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <span className="w-4 tabular-nums">{i + 1}</span>
                        {!soloLectura && (
                          <>
                            <Button variant="ghost" size="icon-xs" aria-label="Subir prioridad" disabled={i === 0} onClick={() => mover(i, -1)}>
                              <ArrowUpIcon />
                            </Button>
                            <Button variant="ghost" size="icon-xs" aria-label="Bajar prioridad" disabled={i === b.proveedores.length - 1} onClick={() => mover(i, 1)}>
                              <ArrowDownIcon />
                            </Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="font-medium">{nombreProveedor(p.proveedor_id)}</TableCell>
                    <TableCell title={precio?.evidencia ? `“${precio.evidencia}”` : undefined}>
                      {precio ? (
                        <span className="tabular-nums">{pesos(precio.precio_sin_iva_uyu)} <span className="text-xs text-muted-foreground">+ IVA</span></span>
                      ) : (
                        <span className="text-muted-foreground">sin cotización</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {soloLectura ? (
                        p.minimo_compra ? `${p.minimo_compra} ${u(unidad)}` : <span className="text-muted-foreground">sin mínimo</span>
                      ) : (
                        <Input aria-label={`Mínimo de compra de ${nombreProveedor(p.proveedor_id)}`} className="h-8" placeholder="sin mínimo" value={p.minimo_compra} onChange={(e) => cambiar(i, { minimo_compra: e.target.value })} />
                      )}
                    </TableCell>
                    <TableCell>
                      {soloLectura ? (
                        p.unidad_venta || <span className="text-muted-foreground">Unidad</span>
                      ) : (
                        <Input aria-label={`Unidad de venta de ${nombreProveedor(p.proveedor_id)}`} className="h-8" placeholder="Unidad" value={p.unidad_venta} onChange={(e) => cambiar(i, { unidad_venta: e.target.value })} />
                      )}
                    </TableCell>
                    <TableCell>
                      {soloLectura ? (
                        `× ${p.factor_conversion || 1}`
                      ) : (
                        <Input aria-label={`Conversión de ${nombreProveedor(p.proveedor_id)}`} className="h-8" value={p.factor_conversion} onChange={(e) => cambiar(i, { factor_conversion: e.target.value })} />
                      )}
                    </TableCell>
                    {!soloLectura && (
                      <TableCell>
                        <Button variant="ghost" size="icon-xs" aria-label={`Quitar ${nombreProveedor(p.proveedor_id)}`} onClick={() => set("proveedores", b.proveedores.filter((_, k) => k !== i))}>
                          <XIcon />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        {ctx.precios.length > 0 && <Evidencia texto={ctx.precios[0]!.evidencia} className="text-xs" />}
      </CardContent>
    </Card>
  );
}

// ─────────── Sustitutos y negociación ───────────
export function TarjetaSustitutos({
  b,
  set,
  errores,
  soloLectura,
  usuario,
}: {
  b: Borrador;
  set: Set;
  errores: Record<string, string>;
  soloLectura: boolean;
  usuario: string;
}) {
  const [nuevo, setNuevo] = useState("");
  const agregar = () => {
    if (!nuevo.trim()) return;
    set("sustitutos", [...b.sustitutos, { nombre: nuevo.trim(), producto_id: null, aprobado_por: usuario }]);
    setNuevo("");
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sustitutos y negociación</CardTitle>
        <CardDescription>Solo se ofrecen los sustitutos cargados acá.</CardDescription>
      </CardHeader>
      <CardContent className="gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sustituto-nuevo">Sustitutos aceptados</Label>
          <div className="flex flex-wrap items-center gap-2">
            {b.sustitutos.length === 0 && <span className="text-sm text-muted-foreground">Ninguno</span>}
            {b.sustitutos.map((s, i) => (
              <Badge key={`${s.nombre}-${i}`} variant="outline" className="h-6 gap-1 pr-1" title={s.aprobado_por ? `Aprobado por ${s.aprobado_por}` : undefined}>
                {s.nombre}
                {!soloLectura && (
                  <button type="button" aria-label={`Quitar ${s.nombre}`} className="rounded-full p-0.5 hover:bg-muted" onClick={() => set("sustitutos", b.sustitutos.filter((_, k) => k !== i))}>
                    <XIcon className="size-3" />
                  </button>
                )}
              </Badge>
            ))}
          </div>
          {!soloLectura && (
            <div className="flex gap-2">
              <Input
                id="sustituto-nuevo"
                className="h-8"
                placeholder="Ej. Resma A4 80 g"
                value={nuevo}
                onChange={(e) => setNuevo(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    agregar();
                  }
                }}
              />
              <Button variant="outline" size="sm" onClick={agregar} disabled={!nuevo.trim()}>
                Agregar
              </Button>
            </div>
          )}
          {errores.sustitutos && <span className="text-xs text-destructive">{errores.sustitutos}</span>}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo id="descuento" etiqueta="Descuento objetivo" error={errores.descuento_objetivo_pct} ayuda="Pregunta abierta del PRD (§14.1)">
            <InputNumero id="descuento" valor={b.descuento_objetivo_pct} onCambio={(v) => set("descuento_objetivo_pct", v)} sufijo="%" placeholder="A definir" disabled={soloLectura} error={errores.descuento_objetivo_pct} />
          </Campo>
          <Campo id="concesion" etiqueta="Concesión máxima" error={errores.concesion_maxima_pct} ayuda="Lo que el agente puede ceder sin aprobación">
            <InputNumero id="concesion" valor={b.concesion_maxima_pct} onCambio={(v) => set("concesion_maxima_pct", v)} sufijo="%" placeholder="A definir" disabled={soloLectura} error={errores.concesion_maxima_pct} />
          </Campo>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────── Historial ───────────
export function Historial({
  cambios,
  soloLectura,
  revirtiendo,
  onRevertir,
}: {
  cambios: CambioRegla[];
  soloLectura: boolean;
  revirtiendo: string | null;
  onRevertir: (c: CambioRegla) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Historial de cambios <Badge variant="secondary">{cambios.length}</Badge>
        </CardTitle>
        <CardDescription>Valor anterior y nuevo, quién, cuándo y por qué.</CardDescription>
      </CardHeader>
      <CardContent className="gap-0">
        {cambios.length === 0 && (
          <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
            <HistoryIcon className="size-4" aria-hidden /> Todavía no hay cambios: las reglas son las de la carga inicial.
          </div>
        )}
        <ul className="max-h-96 divide-y overflow-auto">
          {cambios.map((c) => (
            <li key={c.id} className="flex items-start gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">
                  {c.etiqueta}: {c.texto_anterior} → {c.texto_nuevo}
                </div>
                <div className="text-xs text-muted-foreground">
                  {c.usuario} · {fechaHora(c.fecha)} · “{c.motivo}”
                </div>
                {c.revertido_por && <Etiqueta className="mt-1">Revertido</Etiqueta>}
                {c.revierte && <Etiqueta tono="azul" className="mt-1">Reversión</Etiqueta>}
              </div>
              {!soloLectura && !c.revertido_por && (
                <Button variant="outline" size="xs" onClick={() => onRevertir(c)} disabled={revirtiendo !== null}>
                  {revirtiendo === c.id ? <Spinner className="size-3" /> : <RotateCcwIcon />} Revertir
                </Button>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export function Dato({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="text-sm leading-none font-medium">{etiqueta}</span>
      <div className="flex h-9 items-center">{children}</div>
    </div>
  );
}
