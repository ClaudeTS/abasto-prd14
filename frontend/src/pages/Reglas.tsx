// Panel de reglas por producto (PRD 1.4 §11.4; RF-13, RF-14, RF-15). Mockup: Reglas.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CheckCircle2Icon, LockIcon } from "lucide-react";
import { MODO } from "@/api";
import { ErrorBanner, Etiqueta } from "@/components/comunes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import * as api from "@/features/reglas/api";
import { aPropuesta, desdeReglas, type Borrador } from "@/features/reglas/borrador";
import { Campo, Input, Label, Select } from "@/features/reglas/campos";
import {
  AvisoVistaPrevia,
  BuscadorProducto,
  Dato,
  Historial,
  TablaProveedores,
  TarjetaReposicion,
  TarjetaSustitutos,
  TarjetaTope,
  fechaHora,
  pesos,
  u,
} from "@/features/reglas/panel";
import type { CambioRegla, VistaPrevia, VistaReglas } from "@/features/reglas/types";
import { ApiError, mensajeError } from "@/lib/errores";
import { useAuth } from "@/lib/auth";
import { formatNumero } from "@/lib/format";

export default function Reglas() {
  const { productoId } = useParams();
  const navigate = useNavigate();
  const { usuario, esAdmin } = useAuth();
  const [productos, setProductos] = useState<VistaReglas[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargarLista = useCallback(async () => {
    try {
      setProductos(await api.listarReglas());
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, []);

  useEffect(() => {
    cargarLista();
  }, [cargarLista]);

  const encabezado = (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Reglas por producto</h1>
          <Badge variant="secondary">Solo el administrador edita</Badge>
        </div>
        <p className="text-muted-foreground">Las reglas viven en la base de datos: el agente las consulta antes de cada decisión.</p>
      </div>
    </div>
  );

  if (MODO === "mock")
    return (
      <div className="mx-auto flex max-w-6xl flex-col gap-5">
        {encabezado}
        <Alert>
          <AlertTitle>Esta pantalla necesita el backend</AlertTitle>
          <AlertDescription>En modo mock no hay reglas guardadas. Abrila con el backend corriendo.</AlertDescription>
        </Alert>
      </div>
    );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      {!productoId && encabezado}
      {!esAdmin && <AvisoConsulta />}
      {error && <ErrorBanner mensaje={error} onReintentar={cargarLista} />}
      {!productos && !error && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando las reglas…
        </div>
      )}
      {productos && !productoId && (
        <ListaProductos productos={productos} onElegir={(id) => navigate(`/reglas/${id}`)} />
      )}
      {productos && productoId && (
        <PanelProducto
          key={productoId}
          productoId={productoId}
          productos={productos}
          esAdmin={esAdmin}
          usuario={usuario?.nombre ?? ""}
          encabezado={encabezado}
          onGuardado={cargarLista}
        />
      )}
    </div>
  );
}

function AvisoConsulta() {
  return (
    <Alert>
      <LockIcon />
      <AlertTitle>Modo consulta</AlertTitle>
      <AlertDescription>Ves las reglas y su historial, pero solo el administrador de compras puede cambiarlas.</AlertDescription>
    </Alert>
  );
}

// ─────────── /reglas: elegir producto ───────────
function ListaProductos({ productos, onElegir }: { productos: VistaReglas[]; onElegir: (id: string) => void }) {
  return (
    <>
      <Card>
        <CardContent>
          <Campo id="producto" etiqueta="Producto" ayuda="Elegí un producto por nombre o código para ver y editar sus reglas.">
            <BuscadorProducto productos={productos} actual={null} onElegir={onElegir} />
          </Campo>
        </CardContent>
      </Card>
      <Card className="py-0">
        <Table className="min-w-[720px]">
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Producto</TableHead>
              <TableHead>Compra</TableHead>
              <TableHead>Stock al cierre</TableHead>
              <TableHead>Mínimo / base</TableHead>
              <TableHead>Tope unitario</TableHead>
              <TableHead className="pr-6">Hoy el cierre pide</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {productos.map((p) => {
              const r = p.reglas;
              const un = u(p.unidad);
              const repo = p.contexto.reposicion;
              return (
                <TableRow key={p.producto_id} className="cursor-pointer" onClick={() => onElegir(p.producto_id)}>
                  <TableCell className="pl-6">
                    <Link to={`/reglas/${p.producto_id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                      {p.nombre}
                    </Link>
                    <div className="text-xs text-muted-foreground">{p.producto_id}</div>
                  </TableCell>
                  <TableCell>{r.compra_automatica ? <Etiqueta tono="verde">Automática</Etiqueta> : <Etiqueta>Manual</Etiqueta>}</TableCell>
                  <TableCell className="tabular-nums">
                    {formatNumero(p.contexto.stock_actual)} {un}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatNumero(r.stock_minimo)} / {r.stock_base === null ? <span className="text-muted-foreground">—</span> : formatNumero(r.stock_base)}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {r.tope_precio_unitario === null ? (
                      <span className="text-muted-foreground">sin tope</span>
                    ) : (
                      `${r.moneda_tope === "USD" ? "USD " + formatNumero(r.tope_precio_unitario, 2) : pesos(r.tope_precio_unitario)}`
                    )}
                  </TableCell>
                  <TableCell className="pr-6 tabular-nums">
                    {!repo ? (
                      <span className="text-muted-foreground">se compra a pedido</span>
                    ) : repo.cantidad > 0 ? (
                      `${formatNumero(repo.cantidad)} ${un}`
                    ) : (
                      <span className="text-muted-foreground">nada</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </>
  );
}

// ─────────── /reglas/:productoId ───────────
function PanelProducto({
  productoId,
  productos,
  esAdmin,
  usuario,
  encabezado,
  onGuardado,
}: {
  productoId: string;
  productos: VistaReglas[];
  esAdmin: boolean;
  usuario: string;
  encabezado: React.ReactNode;
  onGuardado: () => void;
}) {
  const navigate = useNavigate();
  const [vista, setVista] = useState<VistaReglas | null>(null);
  const [borrador, setBorrador] = useState<Borrador | null>(null);
  const [historial, setHistorial] = useState<CambioRegla[]>([]);
  const [motivo, setMotivo] = useState("");
  const [previa, setPrevia] = useState<VistaPrevia | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [revirtiendo, setRevirtiendo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [erroresServidor, setErroresServidor] = useState<Record<string, string>>({});
  const [aviso, setAviso] = useState<string | null>(null);
  const soloLectura = !esAdmin;

  const aplicarVista = useCallback((v: VistaReglas) => {
    setVista(v);
    setBorrador(desdeReglas(v.reglas));
    setErroresServidor({});
    setPrevia(null); // la anterior era de otras reglas: no mostrarla ni un instante
  }, []);

  const cargar = useCallback(async () => {
    try {
      const [v, h] = await Promise.all([api.verReglas(productoId), api.historialReglas(productoId)]);
      aplicarVista(v);
      setHistorial(h);
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [productoId, aplicarVista]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const { propuesta, errores: erroresLocales } = useMemo(
    () => (borrador && vista ? aPropuesta(borrador, vista.reglas) : { propuesta: {}, errores: {} }),
    [borrador, vista],
  );
  const hayCambios = Object.keys(propuesta).length > 0 || Object.keys(erroresLocales).length > 0;
  const clavePropuesta = JSON.stringify(propuesta);

  // Vista previa: con lo guardado al entrar y con cada cambio (espera a que dejes de tipear).
  useEffect(() => {
    if (!vista) return;
    let vigente = true;
    setCalculando(true);
    const t = window.setTimeout(() => {
      api
        .vistaPrevia(productoId, JSON.parse(clavePropuesta))
        .then((vp) => vigente && setPrevia(vp))
        .catch((e) => vigente && setPrevia({ ...vacia, texto: mensajeError(e) }))
        .finally(() => vigente && setCalculando(false));
    }, 350);
    return () => {
      vigente = false;
      window.clearTimeout(t);
    };
  }, [clavePropuesta, productoId, vista]);

  const errores = { ...(previa?.errores ?? {}), ...erroresServidor, ...erroresLocales };
  const set = <K extends keyof Borrador>(campo: K, valor: Borrador[K]) => {
    setAviso(null);
    setBorrador((b) => (b ? { ...b, [campo]: valor } : b));
  };

  const guardar = async () => {
    if (!motivo.trim()) {
      setErroresServidor({ motivo: "Contá el motivo: queda en el historial." });
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const v = await api.cambiarReglas(productoId, propuesta, motivo.trim());
      aplicarVista(v);
      setHistorial(await api.historialReglas(productoId));
      setMotivo("");
      setAviso("Cambios guardados. Aplican a los pedidos nuevos.");
      onGuardado();
    } catch (e) {
      setError(mensajeError(e));
      if (e instanceof ApiError && e.detalle && typeof e.detalle === "object") setErroresServidor(e.detalle as Record<string, string>);
    } finally {
      setGuardando(false);
    }
  };

  const revertir = async (c: CambioRegla) => {
    if (hayCambios && !window.confirm("Tenés cambios sin guardar: se descartan al revertir. ¿Seguimos?")) return;
    setRevirtiendo(c.id);
    setError(null);
    try {
      aplicarVista(await api.revertirCambio(productoId, c.id));
      setHistorial(await api.historialReglas(productoId));
      setAviso(`Revertido: ${c.etiqueta} vuelve a ${c.texto_anterior}.`);
      onGuardado();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setRevirtiendo(null);
    }
  };

  const elegir = (id: string) => {
    if (id === productoId) return;
    if (hayCambios && !window.confirm("Tenés cambios sin guardar en este producto. ¿Los descartás?")) return;
    navigate(`/reglas/${id}`);
  };

  const puedeGuardar = esAdmin && Object.keys(propuesta).length > 0 && Object.keys(erroresLocales).length === 0 && !guardando;

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-[1_1_20rem]">{encabezado}</div>
        {esAdmin && (
          <div className="flex gap-2">
            <Button variant="outline" disabled={!hayCambios || guardando} onClick={() => vista && aplicarVista(vista)}>
              Descartar cambios
            </Button>
            <Button disabled={!puedeGuardar} onClick={guardar}>
              {guardando && <Spinner />} Guardar cambios
            </Button>
          </div>
        )}
      </div>

      {error && <ErrorBanner mensaje={error} onReintentar={vista ? undefined : cargar} />}
      {!vista || !borrador ? (
        !error && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Cargando…
          </div>
        )
      ) : (
        <>
          <Card>
            <CardContent>
              <div className="flex flex-wrap items-end gap-4">
                <Campo id="producto" etiqueta="Producto" className="min-w-64 flex-[2_1_320px]">
                  <BuscadorProducto productos={productos} actual={vista} onElegir={elegir} />
                </Campo>
                <div className="flex min-w-40 flex-[1_1_160px] flex-col gap-1.5">
                  <Label htmlFor="cliente-interno">Cliente interno</Label>
                  <Select
                    id="cliente-interno"
                    value={borrador.cliente_interno}
                    onChange={(e) => set("cliente_interno", e.target.value as Borrador["cliente_interno"])}
                    disabled={soloLectura}
                  >
                    <option value="personal">Personal</option>
                    <option value="ventas">Ventas</option>
                  </Select>
                </div>
                <div className="flex-[1_1_200px]">
                  <Dato etiqueta="Stock al último cierre">
                    <span className="font-semibold tabular-nums">
                      {formatNumero(vista.contexto.stock_actual)} {u(vista.unidad)} · {fechaHora(vista.contexto.fecha_corte)}
                    </span>
                    {vista.contexto.en_camino > 0 && (
                      <span className="ml-2 text-xs text-muted-foreground">+ {formatNumero(vista.contexto.en_camino)} en camino</span>
                    )}
                  </Dato>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                {vista.nombre} · código {vista.producto_id} · {vista.tipo === "consumible" ? "consumible" : "equipamiento"}
                {vista.actualizado_por && vista.actualizado_en && ` · última edición: ${vista.actualizado_por}, ${fechaHora(vista.actualizado_en)}`}
              </p>
            </CardContent>
          </Card>

          <AvisoVistaPrevia vista={previa} cargando={calculando} hayCambios={hayCambios} />
          {previa && previa.cambios.length > 0 && (
            <div className="-mt-2 flex flex-wrap gap-1.5 text-xs">
              {previa.cambios.map((c) => (
                <Badge key={c.campo} variant="outline" className="h-auto py-0.5 whitespace-normal">
                  {c.etiqueta}: {c.anterior} → {c.nuevo}
                </Badge>
              ))}
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <TarjetaReposicion b={borrador} set={set} vista={vista} errores={errores} soloLectura={soloLectura} />
            <TarjetaTope b={borrador} set={set} ctx={vista.contexto} errores={errores} soloLectura={soloLectura} />
          </div>
          <TablaProveedores b={borrador} set={set} ctx={vista.contexto} unidad={vista.unidad} error={errores.proveedores} soloLectura={soloLectura} />
          <div className="grid gap-4 lg:grid-cols-2">
            <TarjetaSustitutos b={borrador} set={set} errores={errores} soloLectura={soloLectura} usuario={usuario} />
            <Historial cambios={historial} soloLectura={soloLectura} revirtiendo={revirtiendo} onRevertir={revertir} />
          </div>

          {esAdmin && (
            <Card>
              <CardContent>
                <div className="flex flex-wrap items-start gap-4">
                  <Campo id="motivo" etiqueta="Motivo del cambio" error={errores.motivo} className="flex-[1_1_360px]">
                    <Input
                      id="motivo"
                      placeholder="Obligatorio para guardar"
                      value={motivo}
                      aria-invalid={errores.motivo ? true : undefined}
                      onChange={(e) => {
                        setMotivo(e.target.value);
                        setErroresServidor(({ motivo: _, ...resto }) => resto);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && puedeGuardar) guardar();
                      }}
                    />
                  </Campo>
                  <p className="flex-[1_1_280px] pt-6 text-sm text-muted-foreground">
                    Los cambios aplican desde que guardás: al próximo cierre y a las cotizaciones y órdenes que se armen después.
                  </p>
                </div>
                {aviso && (
                  <p role="status" className="flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-400">
                    <CheckCircle2Icon className="size-4" /> {aviso}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </>
  );
}

const vacia: VistaPrevia = {
  valido: false,
  errores: {},
  cambios: [],
  aplica_cierre: false,
  dispara_compra: false,
  cantidad: 0,
  motivo: null,
  aprobacion: null,
  mejor_precio: null,
  tope_unitario_uyu: null,
  bajo_tope: null,
  texto: "",
  evidencia: null,
};
