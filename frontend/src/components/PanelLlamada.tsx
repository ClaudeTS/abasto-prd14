import { useEffect, useRef, useState, type ComponentProps, type ReactNode } from "react";
import {
  CheckIcon,
  PhoneIcon,
  PhoneOffIcon,
  PhoneOutgoingIcon,
  RotateCcwIcon,
  WandSparklesIcon,
  XIcon,
} from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { nombreProveedor } from "@/lib/proveedores";
import { useSesion } from "@/lib/sesion";
import { usePolling, useReloj } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Avatar, Etiqueta, Puntos } from "@/components/comunes";
import type { ConfigLlamadas, EstadoLlamada, Llamada } from "@/types";

// Llamadas telefónicas del agente (ElevenLabs + Twilio, o simuladas). Un panel reutilizable para
// "llamar al que no respondió" (feed) y "Aprobar y llamar" (negociación).

export const LLAMADA_ACTIVA: EstadoLlamada[] = ["iniciando", "sonando", "en_curso", "procesando"];
export const estaActiva = (l: Llamada | null | undefined) => !!l && LLAMADA_ACTIVA.includes(l.estado);

// ─────────── Configuración (GET /llamadas/config) ───────────

let configCache: Promise<ConfigLlamadas | null> | null = null;

/** null mientras carga o si el backend no la expone: en ese caso no se bloquea nada. */
export function useConfigLlamadas(): ConfigLlamadas | null {
  const [config, setConfig] = useState<ConfigLlamadas | null>(null);
  useEffect(() => {
    let vivo = true;
    configCache ??= api.getConfigLlamadas().catch(() => {
      configCache = null; // reintentar en el próximo montaje
      return null;
    });
    configCache.then((c) => vivo && setConfig(c));
    return () => {
      vivo = false;
    };
  }, []);
  return config;
}

/** Por qué no se puede llamar (modo real sin configurar o sin teléfono), o null si se puede. */
export function motivoNoLlamar(config: ConfigLlamadas | null, proveedorId: string): string | null {
  if (!config || config.modo !== "real") return null;
  if (!config.lista) return `Para llamar de verdad faltan: ${config.faltan.join(", ")} (backend/.env)`;
  if (!config.proveedores_con_telefono.includes(proveedorId))
    return `No hay teléfono cargado para ${nombreProveedor(proveedorId)} en TELEFONOS_PROVEEDORES`;
  return null;
}

/** Indicador discreto: si las llamadas son reales o simuladas. */
export function ModoLlamadas({ config, className }: { config: ConfigLlamadas | null; className?: string }) {
  if (!config) return null;
  const real = config.modo === "real";
  return (
    <p
      className={cn("flex items-center gap-1.5 text-xs text-muted-foreground", className)}
      title={real ? "ElevenLabs + Twilio" : "Sin red ni costo: la conversación es de los fixtures"}
    >
      <PhoneIcon className="size-3" />
      {real ? (config.lista ? "Llamadas reales" : "Llamadas reales · falta configurar") : "Llamadas simuladas"}
    </p>
  );
}

/** Botón de llamar: deshabilitado con tooltip si en modo real falta configuración. */
export function BotonLlamar({
  config,
  proveedorId,
  onClick,
  disabled,
  motivoDeshabilitado,
  children,
  ...props
}: {
  config: ConfigLlamadas | null;
  proveedorId: string;
  onClick: () => void;
  disabled?: boolean;
  /** Tooltip cuando `disabled` viene de afuera (ej. otra llamada en curso). */
  motivoDeshabilitado?: string;
  children: ReactNode;
} & Pick<ComponentProps<typeof Button>, "size" | "variant" | "className">) {
  const motivo = motivoNoLlamar(config, proveedorId) ?? (disabled ? motivoDeshabilitado : undefined);
  const boton = (
    <Button {...props} onClick={onClick} disabled={disabled || !!motivoNoLlamar(config, proveedorId)}>
      {children}
    </Button>
  );
  if (!motivo) return boton;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* Un botón deshabilitado no recibe el hover: el tooltip va en un span. */}
          <span tabIndex={0} className="inline-flex">
            {boton}
          </span>
        </TooltipTrigger>
        <TooltipContent>{motivo}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ─────────── Estado de una llamada: inicio, polling y reintento ───────────

export interface EstadoTelefono {
  llamada: Llamada | null;
  /** Error al iniciarla (POST): 409 si ya respondió o falta configuración. */
  error: string | null;
  /** Error al consultarla (GET): se sigue intentando. */
  errorConsulta: string | null;
  iniciando: boolean;
  /** Reintenta con la última acción usada (o la del hook). `simulada`: respaldo sin red. */
  iniciar: (simulada?: boolean) => Promise<Llamada | null>;
  /** Inicia con otra acción (ej. otro proveedor) y la recuerda para los reintentos. */
  iniciarCon: (accion: (simulada: boolean) => Promise<Llamada>) => Promise<Llamada | null>;
  setLlamada: (l: Llamada | null) => void;
  cerrar: () => void;
}

/**
 * `iniciar(simulada)` dispara la llamada; mientras está activa se consulta GET /llamadas/{id} cada 1 s.
 * La llamada se guarda en sessionStorage (`clave`) para que un F5 no la pierda.
 */
export function useLlamada(clave: string, iniciarFn: (simulada: boolean) => Promise<Llamada>): EstadoTelefono {
  const [llamada, setLlamada] = useSesion<Llamada | null>(clave, null);
  const [error, setError] = useState<string | null>(null);
  const [errorConsulta, setErrorConsulta] = useState<string | null>(null);
  const [iniciando, setIniciando] = useState(false);
  const fn = useRef(iniciarFn);
  fn.current = iniciarFn;
  const ultima = useRef<((simulada: boolean) => Promise<Llamada>) | null>(null);

  usePolling(
    async () => {
      if (!llamada) return;
      try {
        const l = await api.getLlamada(llamada.id);
        setLlamada(l);
        setErrorConsulta(null);
      } catch (e) {
        setErrorConsulta(mensajeError(e));
      }
    },
    1000,
    estaActiva(llamada),
  );

  const correr = async (accion: (simulada: boolean) => Promise<Llamada>, simulada: boolean) => {
    setIniciando(true);
    setError(null);
    setErrorConsulta(null);
    try {
      const l = await accion(simulada);
      setLlamada(l);
      return l;
    } catch (e) {
      setError(mensajeError(e));
      return null;
    } finally {
      setIniciando(false);
    }
  };

  const iniciar = (simulada = false) => correr(ultima.current ?? fn.current, simulada);
  const iniciarCon = (accion: (simulada: boolean) => Promise<Llamada>) => {
    ultima.current = accion;
    return correr(accion, false);
  };

  const cerrar = () => {
    ultima.current = null;
    setLlamada(null);
    setError(null);
    setErrorConsulta(null);
  };

  return { llamada, error, errorConsulta, iniciando, iniciar, iniciarCon, setLlamada, cerrar };
}

// ─────────── Panel ───────────

function reloj(segundos: number): string {
  const s = Math.max(0, Math.round(segundos));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Segundos de llamada que se muestran: lo que diga el backend, o el reloj local mientras está en curso. */
function useDuracion(llamada: Llamada | null): number {
  const desde = useRef<{ id: string; t: number } | null>(null);
  const enCurso = llamada?.estado === "en_curso";
  const ahora = useReloj(1000, enCurso);
  if (llamada && enCurso && desde.current?.id !== llamada.id) desde.current = { id: llamada.id, t: Date.now() };
  const local = enCurso && desde.current ? (ahora - desde.current.t) / 1000 : 0;
  const turnos = llamada?.transcripcion ?? [];
  const ultimo = turnos.length ? (turnos[turnos.length - 1].segundo ?? 0) : 0;
  const maximo = useRef<{ id: string; s: number }>({ id: "", s: 0 });
  const s = Math.max(llamada?.duracion_segundos ?? 0, ultimo, local);
  if (!llamada) return 0;
  if (maximo.current.id !== llamada.id) maximo.current = { id: llamada.id, s: 0 };
  maximo.current.s = Math.max(maximo.current.s, s); // nunca para atrás
  return maximo.current.s;
}

export default function PanelLlamada({
  proveedorId,
  tel,
  titulo,
  onCerrar,
  compacto = false,
  className,
  children,
}: {
  proveedorId: string;
  /** Para una columna angosta: transcripción más baja y plegada al terminar (ya queda en el feed). */
  compacto?: boolean;
  tel: EstadoTelefono;
  titulo?: string;
  /** Si está, al terminar (o fallar) se puede cerrar el panel. */
  onCerrar?: () => void;
  className?: string;
  /** Lo que se muestra debajo de la transcripción (ej. el resultado al terminar). */
  children?: ReactNode;
}) {
  const { llamada, error, errorConsulta, iniciando } = tel;
  const segundos = useDuracion(llamada);
  const nombre = nombreProveedor(proveedorId);
  const caja = useRef<HTMLDivElement>(null);
  const turnos = llamada?.transcripcion ?? [];
  const [verTranscripcion, setVerTranscripcion] = useState(false);

  useEffect(() => {
    const el = caja.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turnos.length]);

  const fallida = !iniciando && (llamada?.estado === "fallida" || (!llamada && !!error));
  const motivoFalla = llamada?.estado === "fallida" ? (llamada.error ?? error) : error;
  const terminada = llamada?.estado === "terminada";
  const cerrable = !!onCerrar && (terminada || fallida);

  return (
    <Card size="sm" className={cn("gap-0 py-0", className)} aria-live="polite">
      <CardHeader className="border-b py-3">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar proveedorId={proveedorId} className="size-8 text-[10px]" />
          <div className="min-w-0 space-y-0.5">
            <CardTitle className="truncate">{titulo ?? `Llamada a ${nombre}`}</CardTitle>
            <CardDescription className="flex flex-wrap items-center gap-x-2 gap-y-1">
              {llamada?.telefono && <span className="tabular-nums">{llamada.telefono}</span>}
              {llamada && (
                <Etiqueta tono={llamada.modo === "real" ? "azul" : "neutro"} className="h-4.5 text-[11px]">
                  {llamada.modo === "real" ? "Llamada real" : "Simulada"}
                </Etiqueta>
              )}
            </CardDescription>
          </div>
        </div>
        {cerrable && (
          <CardAction>
            <Button variant="ghost" size="icon-xs" onClick={onCerrar} aria-label="Cerrar">
              <XIcon />
            </Button>
          </CardAction>
        )}
      </CardHeader>

      <CardContent className="py-3">
        <EstadoVisible llamada={llamada} iniciando={iniciando} fallida={fallida} segundos={segundos} motivo={motivoFalla} />

        {compacto && terminada && turnos.length > 0 && (
          <Button
            variant="link"
            size="xs"
            className="h-auto self-start px-0"
            onClick={() => setVerTranscripcion(!verTranscripcion)}
          >
            {verTranscripcion ? "Ocultar transcripción" : `Ver transcripción (${turnos.length} turnos)`}
          </Button>
        )}

        {turnos.length > 0 && (!compacto || !terminada || verTranscripcion) && (
          <div
            ref={caja}
            className={cn("space-y-2 overflow-y-auto rounded-lg bg-muted/50 p-3", compacto ? "max-h-56" : "max-h-96")}
          >
            {turnos.map((t, k) => (
              <div key={k} className={cn("flex animate-entrar", t.rol === "abasto" ? "justify-end" : "justify-start")}>
                <p
                  className={cn(
                    "max-w-[90%] rounded-xl px-3 py-2 text-sm leading-snug",
                    t.rol === "abasto"
                      ? "rounded-br-sm bg-primary text-primary-foreground"
                      : "rounded-bl-sm bg-background shadow-xs ring-1 ring-foreground/10",
                  )}
                >
                  <span className="mb-0.5 flex items-center justify-between gap-3 text-[10px] font-medium tracking-wide uppercase opacity-60">
                    {t.rol === "abasto" ? "Abasto" : nombre}
                    {t.segundo !== null && t.segundo !== undefined && (
                      <span className="tabular-nums normal-case">{reloj(t.segundo)}</span>
                    )}
                  </span>
                  {t.texto}
                </p>
              </div>
            ))}
            {llamada?.estado === "en_curso" && (
              <p className="flex items-center gap-1.5 px-1 text-xs text-muted-foreground">
                Escuchando <Puntos />
              </p>
            )}
          </div>
        )}

        {errorConsulta && (
          <p className="text-xs text-muted-foreground">
            No pude consultar la llamada ({errorConsulta}). Sigo intentando…
          </p>
        )}

        {fallida && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => tel.iniciar(false)}>
              <RotateCcwIcon /> Reintentar
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => tel.iniciar(true)}
              title="La misma llamada en modo simulado: respaldo sin red"
            >
              <WandSparklesIcon /> Simular llamada
            </Button>
          </div>
        )}

        {children}
      </CardContent>
    </Card>
  );
}

function EstadoVisible({
  llamada,
  iniciando,
  fallida,
  segundos,
  motivo,
}: {
  llamada: Llamada | null;
  iniciando: boolean;
  fallida: boolean;
  segundos: number;
  motivo: string | null;
}) {
  if (fallida) {
    return (
      <div className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
        <PhoneOffIcon className="mt-0.5 size-4 shrink-0" />
        <div>
          <p className="font-medium">No se pudo completar</p>
          {motivo && <p className="text-destructive/90">{motivo}</p>}
        </div>
      </div>
    );
  }
  if (iniciando || !llamada || llamada.estado === "iniciando") {
    return (
      <Fila>
        <Spinner /> Iniciando la llamada…
      </Fila>
    );
  }
  switch (llamada.estado) {
    case "sonando":
      return (
        <Fila>
          <span className="relative flex size-5 items-center justify-center">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400/50" />
            <PhoneOutgoingIcon className="relative size-4 text-emerald-600" />
          </span>
          Llamando <Puntos />
        </Fila>
      );
    case "en_curso":
      return (
        <Fila>
          <span className="relative flex size-2.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex size-2.5 rounded-full bg-red-500" />
          </span>
          En curso · <span className="tabular-nums">{reloj(segundos)}</span>
        </Fila>
      );
    case "procesando":
      return (
        <Fila>
          <Spinner /> Procesando la llamada…
        </Fila>
      );
    case "terminada":
      return (
        <Fila className="text-emerald-700 dark:text-emerald-400">
          <CheckIcon className="size-4" /> Terminada · <span className="tabular-nums">{reloj(segundos)}</span>
        </Fila>
      );
    default:
      return null;
  }
}

function Fila({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={cn("flex items-center gap-2 text-sm font-medium", className)}>{children}</p>;
}
