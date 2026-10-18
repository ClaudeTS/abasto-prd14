// Nuevo pedido (PRD 1.4 RF-01, RF-03, RF-05, §6.1): el agente de compras hace la compra entera.
// Contrato: docs/AGENTE.md §2 (qué muestra cada estado) y §3 (endpoints).
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRightIcon, BotIcon, CircleCheckIcon, InfoIcon, RotateCcwIcon, XIcon } from "lucide-react";
import * as api from "@/api";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";
import { borrarSesion } from "@/lib/sesion";
import { usePolling } from "@/lib/usePolling";
import { Encabezado, ErrorBanner, Etiqueta, Puntos, type Tono } from "@/components/comunes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import * as agenteApi from "@/features/agente/api";
import Entrada, { nombreCliente } from "@/features/agente/Entrada";
import LineaDeTiempo from "@/features/agente/LineaDeTiempo";
import Llamadas from "@/features/agente/Llamadas";
import Ordenes from "@/features/agente/Ordenes";
import Propuesta from "@/features/agente/Propuesta";
import Revision from "@/features/agente/Revision";
import Stock from "@/features/agente/Stock";
import { cantidadConUnidad } from "@/features/agente/comunes";
import { estaTerminada, type ClienteInterno, type CorridaAgente, type OrdenCompra } from "@/features/agente/types";

const POLLING_MS = 1500;

/** Estado del pedido en palabras del PRD (§6.2), para el badge de arriba. */
function estadoPedido(c: CorridaAgente): { texto: string; tono: Tono } {
  const enCurso = c.pasos.find((p) => p.estado === "en_curso")?.id;
  switch (c.estado) {
    case "esperando_confirmacion": {
      const dudas = c.propuesta.some((l) => l.dudas.length > 0 || l.cantidad <= 0);
      return dudas ? { texto: "Datos incompletos", tono: "ambar" } : { texto: "Esperando tu OK", tono: "ambar" };
    }
    case "esperando_revision":
      return { texto: "Cotizando · para revisar", tono: "ambar" };
    case "esperando_aprobacion":
      return { texto: "Pendiente de aprobación", tono: "ambar" };
    case "completada":
      return { texto: "Aprobado", tono: "verde" };
    case "cancelada":
      return { texto: "Cancelado", tono: "neutro" };
    case "error":
      return { texto: "Con error", tono: "rojo" };
    default:
      if (enCurso === "cotizar" || enCurso === "insistir" || enCurso === "revisar") return { texto: "Cotizando", tono: "azul" };
      if (enCurso === "optimizar") return { texto: "Cotizado", tono: "azul" };
      if (enCurso === "negociar") return { texto: "Negociando", tono: "azul" };
      if (enCurso === "ordenes") return { texto: "Emitiendo órdenes", tono: "azul" };
      return { texto: "Nuevo", tono: "azul" };
  }
}

/** ¿El pedido de la demo ya pasó por el simulador? Entonces otra compra necesita POST /reset. */
const yaSeCotizo = (c: CorridaAgente) => c.pasos.find((p) => p.id === "cotizar")?.estado !== "pendiente";

export default function NuevoPedido() {
  const { usuario } = useAuth();
  const [corrida, setCorrida] = useState<CorridaAgente | null>(null);
  const [ultima, setUltima] = useState<CorridaAgente | null>(null);
  const [cargando, setCargando] = useState(true);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorPolling, setErrorPolling] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [texto, setTexto] = useState("");
  const [cliente, setCliente] = useState<ClienteInterno>(usuario?.cliente_interno ?? "personal");
  const [enviando, setEnviando] = useState<"texto" | "reponer" | null>(null);
  const [cancelando, setCancelando] = useState(false);
  const [reiniciando, setReiniciando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setErrorCarga(null);
    try {
      const c = await agenteApi.actual();
      if (c && !estaTerminada(c)) setCorrida(c);
      else setUltima(c);
    } catch (e) {
      setErrorCarga(mensajeError(e));
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  usePolling(
    async () => {
      if (!corrida) return;
      try {
        const c = await agenteApi.obtener(corrida.id);
        setCorrida((prev) => (prev && prev.id === c.id ? c : prev));
        setErrorPolling(null);
      } catch (e) {
        setErrorPolling(mensajeError(e));
      }
    },
    POLLING_MS,
    !!corrida && !estaTerminada(corrida),
  );

  const reiniciarDemo = async (): Promise<boolean> => {
    const ok = window.confirm(
      "El pedido de la demo ya se cotizó. Para empezar otra compra hay que reiniciar la demo: se borran " +
        "las cotizaciones, el plan, la negociación y las órdenes. ¿Reinicio?",
    );
    if (!ok) return false;
    await api.reset();
    borrarSesion();
    return true;
  };

  const mandar = async (t: string) => {
    setEnviando(t.trim() ? "texto" : "reponer");
    setError(null);
    setAviso(null);
    const nueva = { texto: t.trim() || undefined, cliente_interno: cliente };
    try {
      let c: CorridaAgente;
      try {
        c = await agenteApi.iniciar(nueva);
      } catch (e) {
        const d = agenteApi.detalle409(e);
        if (d?.corrida_id) {
          c = await agenteApi.obtener(d.corrida_id);
          setAviso("Ya había una compra en curso: la retomo. Si querés otra, cancelala primero.");
        } else if (d && "estado_pedido" in d) {
          if (!(await reiniciarDemo())) return;
          c = await agenteApi.iniciar(nueva);
        } else throw e;
      }
      setUltima(null);
      setCorrida(c);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setEnviando(null);
    }
  };

  const cancelar = async () => {
    if (!corrida) return;
    if (!window.confirm("¿Cancelar la compra? El agente deja de trabajar en este pedido.")) return;
    setCancelando(true);
    setError(null);
    try {
      setCorrida(await agenteApi.cancelar(corrida.id));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setCancelando(false);
    }
  };

  const empezarDeNuevo = async () => {
    const previa = corrida ?? ultima;
    setError(null);
    setReiniciando(true);
    try {
      if (previa && yaSeCotizo(previa) && !(await reiniciarDemo())) return;
      setCorrida(null);
      setUltima(null);
      setAviso(null);
      if (previa) {
        setTexto(previa.texto ?? "");
        setCliente(previa.cliente_interno ?? "personal");
      }
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setReiniciando(false);
    }
  };

  const confirmar = async (lineas?: { producto_id: string; cantidad: number }[]) => {
    if (!corrida) return;
    setCorrida(await agenteApi.confirmar(corrida.id, lineas));
  };
  const aprobarOrden = async (o: OrdenCompra) => {
    if (corrida) setCorrida(await agenteApi.aprobarOrden(corrida.id, o.id));
  };
  const rechazarOrden = async (o: OrdenCompra) => {
    if (corrida) setCorrida(await agenteApi.rechazarOrden(corrida.id, o.id));
  };

  const terminada = estaTerminada(corrida);

  return (
    <div className="mx-auto max-w-6xl">
      <Encabezado
        titulo="Nuevo pedido"
        bajada="Pedíselo al agente por voz o por email. Entiende el pedido, revisa el inventario, cotiza, llama a quien no responde, negocia y emite las órdenes."
      >
        {corrida && !terminada && corrida.estado !== "esperando_confirmacion" && (
          <Button variant="outline" onClick={cancelar} disabled={cancelando}>
            {cancelando ? <Spinner /> : <XIcon />} Cancelar la compra
          </Button>
        )}
      </Encabezado>

      <div className="space-y-6">
        {errorCarga && <ErrorBanner mensaje={errorCarga} onReintentar={cargar} />}
        {error && <ErrorBanner mensaje={error} />}
        {aviso && (
          <Alert>
            <InfoIcon />
            <AlertDescription>{aviso}</AlertDescription>
          </Alert>
        )}

        {cargando ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Buscando si hay una compra en curso…
          </div>
        ) : !corrida ? (
          !errorCarga && (
            <>
              {ultima && <UltimaCompra c={ultima} onVer={() => setCorrida(ultima)} />}
              {api.MODO !== "mock" && (
                <Stock
                  onArranco={(c, a) => {
                    setUltima(null);
                    setAviso(a);
                    setCorrida(c);
                  }}
                />
              )}
              <Entrada
                texto={texto}
                setTexto={setTexto}
                cliente={cliente}
                setCliente={setCliente}
                enviando={enviando}
                onMandar={mandar}
              />
            </>
          )
        ) : (
          <Corrida
            corrida={corrida}
            errorPolling={errorPolling}
            cancelando={cancelando}
            reiniciando={reiniciando}
            onConfirmar={confirmar}
            onCancelar={cancelar}
            onEmpezarDeNuevo={empezarDeNuevo}
            onAprobar={aprobarOrden}
            onRechazar={rechazarOrden}
          />
        )}
      </div>
    </div>
  );
}

function UltimaCompra({ c, onVer }: { c: CorridaAgente; onVer: () => void }) {
  const estado = estadoPedido(c);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border bg-background px-4 py-3 text-sm">
      <span className="text-muted-foreground">Tu última compra con el agente:</span>
      <Etiqueta tono={estado.tono}>{estado.texto}</Etiqueta>
      <span className="min-w-0 flex-1 truncate text-muted-foreground">
        {c.resumen ?? c.error ?? (c.estado === "cancelada" ? "La cancelaste." : "")}
      </span>
      <Button size="sm" variant="ghost" onClick={onVer}>
        Verla <ArrowRightIcon />
      </Button>
    </div>
  );
}

function Corrida({
  corrida,
  errorPolling,
  cancelando,
  reiniciando,
  onConfirmar,
  onCancelar,
  onEmpezarDeNuevo,
  onAprobar,
  onRechazar,
}: {
  corrida: CorridaAgente;
  errorPolling: string | null;
  cancelando: boolean;
  reiniciando: boolean;
  onConfirmar: (lineas?: { producto_id: string; cantidad: number }[]) => Promise<void>;
  onCancelar: () => void;
  onEmpezarDeNuevo: () => void;
  onAprobar: (o: OrdenCompra) => Promise<void>;
  onRechazar: (o: OrdenCompra) => Promise<void>;
}) {
  const c = corrida;
  const estado = estadoPedido(c);
  // El último activo: mientras cotiza, "insistir" (la llamada) es lo más nuevo.
  const pasoActivo = [...c.pasos].reverse().find((p) => p.estado === "en_curso" || p.estado === "esperando");
  const pasoError = c.pasos.find((p) => p.estado === "error");
  const confirmada = c.pasos.find((p) => p.id === "confirmar")?.estado === "hecho";

  return (
    <>
      <Card size="sm">
        <CardContent className="gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Etiqueta tono={estado.tono}>{estado.texto}</Etiqueta>
            <Etiqueta>Cliente interno: {nombreCliente(c.cliente_interno)}</Etiqueta>
            <Etiqueta>
              Horizonte: {c.horizonte_meses} {c.horizonte_meses === 1 ? "mes" : "meses"}
            </Etiqueta>
            {c.interpretacion?.origen === "fijo" && (
              <Etiqueta title="Sin clave de IA el agente usa la interpretación fija de la frase de la demo">
                Interpretación fija (sin IA)
              </Etiqueta>
            )}
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">{c.id}</span>
          </div>
          {c.texto ? (
            <blockquote className="border-l-2 pl-3 text-base text-pretty">“{c.texto}”</blockquote>
          ) : (
            <p className="text-sm text-muted-foreground">Sin texto: reponer lo de siempre según el inventario.</p>
          )}
        </CardContent>
      </Card>

      {c.avisos.length > 0 && (
        <Alert className="border-amber-200 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/30">
          <InfoIcon />
          <AlertTitle>Para que sepas</AlertTitle>
          <AlertDescription className="text-pretty">
            <ul className="list-disc space-y-0.5 pl-4">
              {[...new Set(c.avisos)].map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {errorPolling && (
        <p className="text-sm text-muted-foreground">No pude consultar al agente ({errorPolling}). Sigo intentando…</p>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-6">
          {c.estado === "en_curso" && (
            <Card>
              <CardContent className="flex flex-row items-start gap-3">
                <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-full bg-muted">
                  <BotIcon className="size-5" />
                </span>
                <div className="min-w-0 space-y-1" aria-live="polite">
                  <p className="flex items-center gap-2 font-medium">
                    {pasoActivo ? pasoActivo.titulo : "Trabajando"} <Puntos />
                  </p>
                  {pasoActivo?.detalle && <p className="text-sm text-muted-foreground">{pasoActivo.detalle}</p>}
                  {confirmada && c.propuesta.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 pt-2">
                      {c.propuesta.map((l) => (
                        <Etiqueta key={l.producto_id}>{cantidadConUnidad(l.cantidad, l.unidad, l.nombre_corto)}</Etiqueta>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {c.estado === "esperando_confirmacion" && (
            <Propuesta
              key={c.id}
              corrida={c}
              onConfirmar={onConfirmar}
              onCancelar={onCancelar}
              cancelando={cancelando}
            />
          )}

          {c.estado === "esperando_revision" && <Revision revision={c.revision} />}

          {c.estado === "completada" && (
            <Card className="ring-emerald-200 dark:ring-emerald-900">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <CircleCheckIcon className="size-5 text-emerald-600" />
                  <CardTitle className="text-lg">Terminé la compra</CardTitle>
                </div>
                {c.resumen && <CardDescription className="text-base text-pretty">{c.resumen}</CardDescription>}
              </CardHeader>
              <CardContent className="flex-row flex-wrap gap-2">
                <Button asChild>
                  <Link to={`/pedidos/${c.pedido_id}`}>
                    Ver el pedido <ArrowRightIcon />
                  </Link>
                </Button>
                <Button variant="outline" onClick={onEmpezarDeNuevo} disabled={reiniciando}>
                  {reiniciando ? <Spinner /> : <RotateCcwIcon />} Nueva compra
                </Button>
              </CardContent>
            </Card>
          )}

          {c.estado === "error" && (
            <Alert variant="destructive">
              <XIcon />
              <AlertTitle>
                {pasoError ? `Falló el paso «${pasoError.titulo}»` : "El agente no pudo terminar la compra"}
              </AlertTitle>
              <AlertDescription className="text-pretty">
                <p>{c.error ?? "Error sin detalle."}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={onEmpezarDeNuevo} disabled={reiniciando}>
                    {reiniciando ? <Spinner /> : <RotateCcwIcon />} Empezar de nuevo
                  </Button>
                  {yaSeCotizo(c) && (
                    <Button size="sm" variant="ghost" asChild>
                      <Link to={`/pedidos/${c.pedido_id}`}>Ver el pedido</Link>
                    </Button>
                  )}
                </div>
              </AlertDescription>
            </Alert>
          )}

          {c.estado === "cancelada" && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Cancelaste la compra.</CardTitle>
                <CardDescription>El agente dejó de trabajar en este pedido.</CardDescription>
              </CardHeader>
              <CardContent className="flex-row">
                <Button onClick={onEmpezarDeNuevo} disabled={reiniciando}>
                  {reiniciando ? <Spinner /> : <RotateCcwIcon />} Empezar de nuevo
                </Button>
              </CardContent>
            </Card>
          )}

          {c.ordenes.length > 0 && <Ordenes ordenes={c.ordenes} onAprobar={onAprobar} onRechazar={onRechazar} />}

          <Llamadas ids={c.llamada_ids} pedidoId={c.pedido_id} />
        </div>

        <aside className="lg:sticky lg:top-6">
          <Card size="sm">
            <CardHeader>
              <CardTitle>Lo que hace el agente</CardTitle>
              <CardDescription>9 pasos. Se para solo cuando te necesita.</CardDescription>
            </CardHeader>
            <CardContent>
              <LineaDeTiempo corrida={c} />
            </CardContent>
          </Card>
        </aside>
      </div>
    </>
  );
}
