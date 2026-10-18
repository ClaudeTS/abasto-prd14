import { useCallback, useEffect, useRef, useState } from "react";
import {
  BotIcon,
  CheckCircle2Icon,
  CircleAlertIcon,
  PlusIcon,
  SquareIcon,
  TrendingDownIcon,
  TriangleAlertIcon,
} from "lucide-react";
import * as api from "@/api";
import { ApiError, mensajeError } from "@/lib/errores";
import { aPorcentaje, pesos, porcentaje } from "@/lib/format";
import { nombreProveedor } from "@/lib/proveedores";
import { usePolling, useReloj } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { ErrorBanner, Etiqueta } from "@/components/comunes";
import Composer from "@/components/agente/Composer";
import LineaDeTiempo, { type DatosCorrida } from "@/components/agente/LineaDeTiempo";
import TarjetaOrden from "@/components/agente/TarjetaOrden";
import type { CorridaAgente, Negociacion, NuevaCorrida, Plan } from "@/types";

// Pantalla principal del rediseño: la persona dice qué comprar y el agente hace todo lo demás.
// Se ve en vivo cada paso; solo aparece algo para tocar si el agente de verdad necesita a alguien.

const TERMINADAS: CorridaAgente["estado"][] = ["completada", "error", "cancelada"];
const ESPERANDO: CorridaAgente["estado"][] = ["esperando_confirmacion", "esperando_revision", "esperando_aprobacion"];

const VACIO: DatosCorrida = { mensajes: [], cotizaciones: [], llamadas: [], plan: null, negociacion: null };

export default function Agente({
  onReseteado,
  onSincronizar,
}: {
  /** El agente reseteó la demo para empezar una compra nueva: la app limpia lo que tenía guardado. */
  onReseteado: () => Promise<void>;
  /** Plan y negociación del agente, para que las vistas de detalle muestren lo mismo. */
  onSincronizar: (plan: Plan | null, negociacion: Negociacion | null) => void;
}) {
  const [corrida, setCorrida] = useState<CorridaAgente | null>(null);
  const [cargado, setCargado] = useState(false);
  const [nueva, setNueva] = useState(false);
  const [iniciando, setIniciando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getAgenteActual()
      .then(setCorrida)
      .catch((e) => setError(mensajeError(e)))
      .finally(() => setCargado(true));
  }, []);

  const comprar = async (pedido: NuevaCorrida) => {
    setIniciando(true);
    setError(null);
    try {
      let c: CorridaAgente;
      try {
        c = await api.iniciarAgente(pedido);
      } catch (e) {
        const detalle = e instanceof ApiError ? (e.detalle as Record<string, unknown> | undefined) : undefined;
        if (detalle && "corrida_id" in detalle) {
          // Ya había una compra en curso: se muestra esa.
          c = await api.getAgente(String(detalle.corrida_id));
        } else if (detalle && "estado_pedido" in detalle) {
          // El pedido ya se usó en otra compra: el agente resetea la demo solo y arranca de cero.
          await api.reset();
          await onReseteado();
          c = await api.iniciarAgente(pedido);
        } else {
          throw e;
        }
      }
      setCorrida(c);
      setNueva(false);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setIniciando(false);
    }
  };

  if (!cargado) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Spinner /> Buscando la última compra…
      </div>
    );
  }

  if (api.MODO === "mock") {
    return (
      <Alert className="mx-auto max-w-2xl">
        <CircleAlertIcon />
        <AlertTitle>El agente necesita el backend</AlertTitle>
        <AlertDescription>
          <p>
            En modo mock solo funcionan las vistas paso a paso (Detalle). Abrí la app sin <code>?modo=mock</code> y con el
            backend corriendo para que el agente haga la compra.
          </p>
        </AlertDescription>
      </Alert>
    );
  }

  if (!corrida || nueva) {
    return <Composer onComprar={comprar} ocupado={iniciando} error={error} />;
  }

  return (
    <Corrida
      key={corrida.id}
      inicial={corrida}
      onNueva={() => {
        setError(null);
        setNueva(true);
      }}
      onSincronizar={onSincronizar}
    />
  );
}

function Corrida({
  inicial,
  onNueva,
  onSincronizar,
}: {
  inicial: CorridaAgente;
  onNueva: () => void;
  onSincronizar: (plan: Plan | null, negociacion: Negociacion | null) => void;
}) {
  const [corrida, setCorrida] = useState(inicial);
  const [datos, setDatos] = useState<DatosCorrida>(VACIO);
  const [error, setError] = useState<string | null>(null);
  const [cancelando, setCancelando] = useState(false);
  const [vueltas, setVueltas] = useState(0);
  const terminada = TERMINADAS.includes(corrida.estado);
  const ahora = useReloj(1000, !terminada);
  const sincronizar = useRef(onSincronizar);
  sincronizar.current = onSincronizar;

  const actualizar = useCallback(async () => {
    try {
      const c = await api.getAgente(inicial.id);
      const estado = (id: string) => c.pasos.find((p) => p.id === id)?.estado ?? "pendiente";
      const [respuestas, llamadas, plan, negociacion] = await Promise.all([
        estado("cotizar") !== "pendiente"
          ? Promise.all([api.getMensajes(c.pedido_id), api.getCotizaciones(c.pedido_id)])
          : Promise.resolve(null),
        Promise.all(c.llamada_ids.map((id) => api.getLlamada(id).catch(() => null))),
        estado("optimizar") === "hecho" ? api.getPlan(c.pedido_id).catch(() => null) : Promise.resolve(null),
        c.negociacion_id ? api.getNegociacion(c.negociacion_id).catch(() => null) : Promise.resolve(null),
      ]);
      setCorrida(c);
      setDatos({
        mensajes: respuestas?.[0] ?? [],
        cotizaciones: respuestas?.[1] ?? [],
        llamadas: llamadas.filter((l) => l !== null),
        plan,
        negociacion,
      });
      sincronizar.current(plan, negociacion);
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setVueltas((n) => n + 1);
    }
  }, [inicial.id]);

  // Mientras trabaja, cada 1,5 s. Terminada, una vuelta para traer el detalle y listo.
  usePolling(actualizar, 1500, !terminada || vueltas === 0);

  const accion = async (fn: () => Promise<CorridaAgente>) => {
    try {
      setCorrida(await fn());
      await actualizar();
    } catch (e) {
      setError(mensajeError(e));
    }
  };

  const cancelar = async () => {
    setCancelando(true);
    await accion(() => api.cancelarAgente(corrida.id));
    setCancelando(false);
  };

  const hechos = corrida.pasos.filter((p) => ["hecho", "omitido", "error"].includes(p.estado)).length;
  const actual = corrida.pasos.find((p) => p.estado === "en_curso" || p.estado === "esperando");
  const fin = terminada ? Date.parse(corrida.actualizada_en) : ahora;
  const segundos = Math.max(0, Math.round((fin - Date.parse(corrida.creada_en)) / 1000));

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start gap-4">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
              <BotIcon className="size-5" />
            </span>
            <div className="min-w-0 flex-1 space-y-1">
              <CardDescription>Le pediste a Abasto</CardDescription>
              <CardTitle className="text-lg leading-snug">
                {corrida.texto ? `“${corrida.texto}”` : "Reponé lo de siempre."}
              </CardTitle>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <EstadoCorrida corrida={corrida} />
                {corrida.opciones.autonomia === "total" ? (
                  <Etiqueta>
                    <BotIcon /> Piloto automático
                  </Etiqueta>
                ) : (
                  <Etiqueta>Respeta tus topes</Etiqueta>
                )}
                <span className="text-xs text-muted-foreground tabular-nums">{reloj(segundos)}</span>
              </div>
            </div>
            <div className="flex gap-2">
              {!terminada ? (
                <Button variant="outline" onClick={cancelar} disabled={cancelando}>
                  {cancelando ? <Spinner /> : <SquareIcon className="fill-current" />} Detener
                </Button>
              ) : (
                <Button onClick={onNueva}>
                  <PlusIcon /> Nueva compra
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="gap-2">
          <Progress value={(hechos / corrida.pasos.length) * 100} />
          <p className="text-sm text-muted-foreground">
            {terminada
              ? `${hechos} de ${corrida.pasos.length} pasos`
              : actual
                ? `Paso ${corrida.pasos.indexOf(actual) + 1} de ${corrida.pasos.length}: ${actual.titulo.toLowerCase()}`
                : "Arrancando…"}
          </p>
        </CardContent>
      </Card>

      <ErrorBanner mensaje={error} />

      {corrida.avisos.length > 0 && (
        <Alert>
          <TriangleAlertIcon />
          <AlertTitle>Avisos del agente</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {corrida.avisos.map((a, k) => (
                <li key={k}>{a}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {ESPERANDO.includes(corrida.estado) && (
        <TeNecesita
          corrida={corrida}
          onConfirmar={() => accion(() => api.confirmarAgente(corrida.id))}
          onAclarar={async (cotizacionId, incluyeIva) => {
            try {
              if (incluyeIva === null) await api.confirmarLectura(cotizacionId);
              else await api.confirmarCampo(cotizacionId, "iva", incluyeIva);
              await actualizar(); // el agente lo ve en el próximo polling y sigue solo
            } catch (e) {
              setError(mensajeError(e));
            }
          }}
          onAprobarOrden={(id) => accion(() => api.aprobarOrden(corrida.id, id))}
          onRechazarOrden={(id) => accion(() => api.rechazarOrden(corrida.id, id))}
        />
      )}

      {corrida.estado === "completada" && <Resultado corrida={corrida} datos={datos} />}
      {corrida.estado === "error" && corrida.error && (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertTitle>La compra se frenó</AlertTitle>
          <AlertDescription>
            <p>{corrida.error}</p>
          </AlertDescription>
        </Alert>
      )}

      <LineaDeTiempo corrida={corrida} datos={datos} />
    </div>
  );
}

function reloj(segundos: number): string {
  const m = Math.floor(segundos / 60);
  return `${m}:${String(segundos % 60).padStart(2, "0")}`;
}

function EstadoCorrida({ corrida }: { corrida: CorridaAgente }) {
  switch (corrida.estado) {
    case "completada":
      return (
        <Etiqueta tono="verde">
          <CheckCircle2Icon /> Compra cerrada
        </Etiqueta>
      );
    case "error":
      return <Etiqueta tono="rojo">Se frenó</Etiqueta>;
    case "cancelada":
      return <Etiqueta>Detenida</Etiqueta>;
    case "en_curso":
      return (
        <Etiqueta tono="azul">
          <Spinner className="size-3" /> Trabajando
        </Etiqueta>
      );
    default:
      return (
        <Etiqueta tono="ambar">
          <CircleAlertIcon /> Te necesita
        </Etiqueta>
      );
  }
}

/** Solo aparece si el agente no puede seguir solo (piloto automático apagado, o una duda que no se aclaró). */
function TeNecesita({
  corrida,
  onConfirmar,
  onAclarar,
  onAprobarOrden,
  onRechazarOrden,
}: {
  corrida: CorridaAgente;
  onConfirmar: () => Promise<void>;
  onAclarar: (cotizacionId: string, incluyeIva: boolean | null) => Promise<void>;
  onAprobarOrden: (id: string) => Promise<void>;
  onRechazarOrden: (id: string) => Promise<void>;
}) {
  const [ocupado, setOcupado] = useState(false);
  const correr = async (fn: () => Promise<void>) => {
    setOcupado(true);
    try {
      await fn();
    } finally {
      setOcupado(false);
    }
  };
  return (
    <Card className="ring-2 ring-amber-300 dark:ring-amber-800">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5 text-amber-800 dark:text-amber-300">
          <CircleAlertIcon className="size-4" /> Abasto necesita tu OK para seguir
        </CardDescription>
        <CardTitle>
          {corrida.estado === "esperando_confirmacion"
            ? "Confirmá la propuesta"
            : corrida.estado === "esperando_revision"
              ? "Hay una respuesta que no pudo aclarar"
              : "Hay órdenes que esperan tu aprobación"}
        </CardTitle>
      </CardHeader>
      <CardContent className="gap-3">
        {corrida.estado === "esperando_confirmacion" && (
          <Button className="self-start" disabled={ocupado} onClick={() => correr(onConfirmar)}>
            {ocupado && <Spinner />} Confirmar y que siga
          </Button>
        )}
        {corrida.estado === "esperando_revision" &&
          corrida.revision.map((r) => (
            <div key={r.cotizacion_id} className="flex flex-wrap items-center gap-2 rounded-lg border p-3">
              <p className="basis-full text-sm">{r.pregunta}</p>
              {r.pide_iva ? (
                <>
                  <Button size="sm" disabled={ocupado} onClick={() => correr(() => onAclarar(r.cotizacion_id, true))}>
                    Incluyen IVA
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={ocupado}
                    onClick={() => correr(() => onAclarar(r.cotizacion_id, false))}
                  >
                    Son + IVA
                  </Button>
                </>
              ) : (
                <Button size="sm" disabled={ocupado} onClick={() => correr(() => onAclarar(r.cotizacion_id, null))}>
                  Está bien así
                </Button>
              )}
            </div>
          ))}
        {corrida.estado === "esperando_aprobacion" &&
          corrida.ordenes
            .filter((o) => o.estado === "esperando_aprobacion")
            .map((o) => (
              <TarjetaOrden
                key={o.id}
                orden={o}
                onAprobar={() => onAprobarOrden(o.id)}
                onRechazar={() => onRechazarOrden(o.id)}
              />
            ))}
      </CardContent>
    </Card>
  );
}

/** Al terminar: lo que hizo el agente, en números. */
function Resultado({ corrida, datos }: { corrida: CorridaAgente; datos: DatosCorrida }) {
  const enviadas = corrida.ordenes.filter((o) => o.estado === "enviada_simulada");
  const total = enviadas.reduce((s, o) => s + o.total_sin_iva, 0);
  const solas = enviadas.filter((o) => o.aprobada_por === "agente").length;
  const elegida = datos.negociacion?.estrategias.find((e) => e.nombre === datos.negociacion?.elegida);
  const cifras: { titulo: string; valor: string; nota: string }[] = [
    {
      titulo: "Órdenes enviadas",
      valor: String(enviadas.length),
      nota:
        solas === enviadas.length
          ? "todas las mandó el agente solo"
          : solas === 0
            ? "todas las aprobaste vos"
            : `${solas === 1 ? "1 la mandó" : `${solas} las mandó`} el agente solo`,
    },
    { titulo: "Total comprado", valor: pesos(total), nota: "sin IVA, con envíos" },
  ];
  if (datos.plan)
    cifras.push({
      titulo: "Ahorro",
      valor: pesos(datos.plan.ahorro),
      nota: `${porcentaje(aPorcentaje(datos.plan.ahorro_pct))} contra el proveedor de siempre`,
    });
  if (elegida && datos.negociacion)
    cifras.push({
      titulo: "Negociación",
      valor: pesos(elegida.ganancia_esperada_uyu),
      nota: `con ${nombreProveedor(datos.negociacion.proveedor_id)}, estrategia «${elegida.nombre}»`,
    });
  return (
    <Card className="border-emerald-200 bg-emerald-50/40 dark:border-emerald-900 dark:bg-emerald-950/20">
      <CardHeader>
        <CardDescription className="flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300">
          <CheckCircle2Icon className="size-4" /> Listo
        </CardDescription>
        <CardTitle className="text-xl">{corrida.resumen ?? "Compra cerrada."}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={cn("grid gap-3", cifras.length > 3 ? "sm:grid-cols-4" : "sm:grid-cols-3")}>
          {cifras.map((c) => (
            <div key={c.titulo} className="rounded-lg border bg-background p-3">
              <p className="text-xs text-muted-foreground">{c.titulo}</p>
              <p className="flex items-center gap-1 text-2xl font-semibold tracking-tight tabular-nums">
                {c.titulo === "Ahorro" && <TrendingDownIcon className="size-5 text-emerald-600" />}
                {c.valor}
              </p>
              <p className="text-xs text-muted-foreground">{c.nota}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
