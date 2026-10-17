import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRightIcon, CheckCheckIcon, CheckIcon, ClockIcon, InboxIcon, PhoneIcon, TriangleAlertIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { fechaCorta, formatNumero, hora, unidad } from "@/lib/format";
import { CANALES, PROVEEDORES, nombreProveedor } from "@/lib/proveedores";
import { usePolling, useReloj } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { Avatar, ErrorBanner, Etiqueta, Puntos } from "@/components/comunes";
import { necesitaRevision } from "@/components/TarjetaCotizacion";
import PanelLlamada, { BotonLlamar, ModoLlamadas, estaActiva, useConfigLlamadas, useLlamada } from "@/components/PanelLlamada";
import VistaMensaje from "@/components/VistaMensaje";
import type { Canal, Cotizacion, Llamada, MensajeCrudo, PedidoDemo } from "@/types";

const SEGUNDOS_PARA_INSISTIR = 25;

const QUE_LEE: Record<Canal, string> = {
  whatsapp_texto: "el mensaje",
  whatsapp_audio: "el audio",
  pdf: "el PDF",
  foto: "la foto",
  llamada: "la llamada",
};

export default function Feed({
  demo,
  cotizarEn,
  recargarPedido,
}: {
  demo: PedidoDemo;
  cotizarEn: number | null;
  recargarPedido: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const { pedido, catalogo } = demo;
  const [mensajes, setMensajes] = useState<MensajeCrudo[]>([]);
  const [cotizaciones, setCotizaciones] = useState<Cotizacion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargado, setCargado] = useState(false);
  const chat = useRef<HTMLDivElement>(null);

  // Llamada al proveedor que no respondió (una a la vez). El panel va en la columna, debajo de la lista.
  const config = useConfigLlamadas();
  const [objetivo, setObjetivo] = useState<string | null>(null);
  const tel = useLlamada("llamada_feed", (simulada) =>
    api.llamarParaCotizar(pedido.id, objetivo ?? tel.llamada?.proveedor_id ?? "", simulada),
  );
  const llamado = tel.llamada?.proveedor_id ?? objetivo;
  const panelAbierto = !!llamado && (!!tel.llamada || tel.iniciando || !!tel.error);
  const llamar = async (proveedorId: string) => {
    setObjetivo(proveedorId);
    // El objetivo nuevo todavía no está en el closure: se llama directo.
    tel.setLlamada(null);
    await tel.iniciarCon((simulada) => api.llamarParaCotizar(pedido.id, proveedorId, simulada));
  };
  const cerrarLlamada = () => {
    tel.cerrar();
    setObjetivo(null);
  };

  const enLectura = mensajes.some((m) => m.estado === "pendiente" || m.estado === "leyendo");
  const faltan = PROVEEDORES.filter((p) => !mensajes.some((m) => m.proveedor_id === p.id));
  const recienPedido = cotizarEn !== null && Date.now() - cotizarEn < 120_000 && faltan.length > 0;
  // Si la llamada trajo la respuesta, el mensaje llega por este mismo polling.
  const esperandoLlamada =
    estaActiva(tel.llamada) ||
    (tel.llamada?.tipo === "cotizacion" &&
      tel.llamada.estado === "terminada" &&
      !mensajes.some((m) => m.proveedor_id === tel.llamada!.proveedor_id && m.estado === "extraido"));
  const activo = !cargado || pedido.estado === "cotizando" || enLectura || recienPedido || esperandoLlamada;
  const ahora = useReloj(1000, activo);

  usePolling(
    async () => {
      try {
        const [m, c] = await Promise.all([api.getMensajes(pedido.id), api.getCotizaciones(pedido.id)]);
        setMensajes([...m].sort((a, b) => Date.parse(a.recibido_en) - Date.parse(b.recibido_en)));
        setCotizaciones(c);
        setError(null);
        if (pedido.estado === "cotizando" || pedido.estado === "nuevo") await recargarPedido();
      } catch (e) {
        setError(mensajeError(e));
      } finally {
        setCargado(true);
      }
    },
    1500,
    activo,
  );

  const listos = mensajes.filter((m) => m.estado === "extraido").length;
  useEffect(() => {
    const el = chat.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [mensajes.length, listos]);

  const inicio = cotizarEn ?? (mensajes[0] ? Date.parse(mensajes[0].recibido_en) : null);
  const segundos = inicio ? Math.max(0, Math.round((ahora - inicio) / 1000)) : 0;
  const todosListos = listos === PROVEEDORES.length;
  const cotPorMensaje = (m: MensajeCrudo) => cotizaciones.find((c) => c.mensaje_id === m.id);

  if (pedido.estado === "nuevo" && !cotizarEn && cargado && mensajes.length === 0) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <InboxIcon />
          </EmptyMedia>
          <EmptyTitle>Todavía no se pidió cotización</EmptyTitle>
          <EmptyDescription>Desde el pedido, un clic en “Cotizar” le escribe a los proveedores.</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button onClick={() => navigate("/pedido")}>Ir al pedido</Button>
        </EmptyContent>
      </Empty>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <Card className="gap-0 py-0">
        <CardHeader className="border-b py-4">
          <CardTitle>Cotización de octubre</CardTitle>
          <CardDescription>
            {PROVEEDORES.length} proveedores · WhatsApp y mail de {pedido.negocio}, leídos por Abasto
          </CardDescription>
          {activo && (
            <CardAction className="flex items-center gap-1.5 self-center text-xs text-muted-foreground">
              <span className="size-2 animate-pulse rounded-full bg-emerald-500" /> En vivo
            </CardAction>
          )}
        </CardHeader>

        <div ref={chat} className="h-[calc(100svh-15rem)] min-h-[28rem] space-y-5 overflow-y-auto bg-muted/30 p-4 sm:p-6">
          {inicio && (
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-sm text-primary-foreground sm:max-w-[32rem]">
                <p>
                  Hola! Les escribe {pedido.comprador?.split(" ")[0] ?? "compras"} de {pedido.negocio}. Necesitamos cotización de:
                </p>
                <ul className="my-2 space-y-0.5">
                  {pedido.lineas.map((l) => {
                    const p = catalogo.find((x) => x.id === l.producto_id);
                    return (
                      <li key={l.producto_id}>
                        · {formatNumero(l.cantidad)} {unidad(p?.unidad_canonica ?? "unidad", l.cantidad)} de{" "}
                        {p?.nombre ?? l.producto_id} <span className="opacity-60">(para el {fechaCorta(l.necesario_para)})</span>
                      </li>
                    );
                  })}
                </ul>
                <p>¿Me pasan precio, condiciones de pago y plazo de entrega? Gracias!</p>
                <p className="mt-1.5 flex items-center justify-end gap-1 text-[11px] opacity-60">
                  Enviado a {PROVEEDORES.length} proveedores · {hora(new Date(inicio).toISOString())}
                  <CheckCheckIcon className="size-3.5" />
                </p>
              </div>
            </div>
          )}

          {mensajes.map((m) => (
            <Burbuja key={m.id} mensaje={m} cotizacion={cotPorMensaje(m)} />
          ))}

          {inicio &&
            segundos >= SEGUNDOS_PARA_INSISTIR &&
            faltan
              .filter((p) => p.id !== tel.llamada?.proveedor_id)
              .map((p) => (
              <div key={p.id} className="flex animate-entrar justify-center">
                <Etiqueta tono="ambar" className="h-auto py-1 text-sm">
                  <ClockIcon /> {p.nombre} no respondió todavía · Abasto le va a insistir en 30 min
                </Etiqueta>
              </div>
            ))}

          {todosListos && (
            <div className="flex animate-entrar justify-center">
              <Etiqueta className="h-auto bg-background py-1 text-sm">
                <CheckIcon /> Las {PROVEEDORES.length} respuestas están leídas y normalizadas
              </Etiqueta>
            </div>
          )}
        </div>
      </Card>

      <aside className="space-y-4">
        <ErrorBanner mensaje={error} />

        <Card size="sm">
          <CardHeader>
            <CardDescription>Respondieron</CardDescription>
            <p className="text-3xl font-semibold tracking-tight tabular-nums">
              {mensajes.length}
              <span className="text-lg font-normal text-muted-foreground"> / {PROVEEDORES.length}</span>
            </p>
          </CardHeader>
          <CardContent className="gap-2">
            <Progress value={(listos / PROVEEDORES.length) * 100} />
            <p className="text-xs text-muted-foreground">
              {listos} leídas por Abasto{inicio ? ` · pedido hace ${segundos} s` : ""}
            </p>
          </CardContent>
        </Card>

        <Card size="sm" className="gap-0 py-0">
          {PROVEEDORES.map((p, i) => {
            const m = mensajes.find((x) => x.proveedor_id === p.id);
            const c = m ? cotPorMensaje(m) : undefined;
            const llamadaDeEste = tel.llamada?.proveedor_id === p.id ? tel.llamada : null;
            const enLlamada = estaActiva(llamadaDeEste) || (tel.iniciando && llamado === p.id);
            return (
              <div key={p.id} className={cn("flex items-center gap-2 px-4 py-2.5", i > 0 && "border-t")}>
                <Avatar proveedorId={p.id} className="size-7 text-[10px]" />
                <span className="min-w-0 flex-1 truncate font-medium" title={p.nombre}>
                  {p.nombre}
                </span>
                {!m && enLlamada ? (
                  <Etiqueta tono="verde">
                    <span className="size-1.5 animate-pulse rounded-full bg-current" /> En llamada
                  </Etiqueta>
                ) : (
                  <EstadoProveedor mensaje={m} cotizacion={c} tarda={segundos >= SEGUNDOS_PARA_INSISTIR} />
                )}
                {!m && inicio && !enLlamada && llamadaDeEste?.estado !== "terminada" && (
                  <BotonLlamar
                    config={config}
                    proveedorId={p.id}
                    size="xs"
                    variant="outline"
                    onClick={() => llamar(p.id)}
                    disabled={estaActiva(tel.llamada) || tel.iniciando}
                    motivoDeshabilitado="Hay otra llamada en curso"
                  >
                    <PhoneIcon /> Llamar
                  </BotonLlamar>
                )}
              </div>
            );
          })}
          {faltan.length > 0 && inicio && <ModoLlamadas config={config} className="border-t px-4 py-2" />}
        </Card>

        {panelAbierto && llamado && (
          <PanelLlamada
            proveedorId={llamado}
            tel={tel}
            titulo={`Llamada a ${nombreProveedor(llamado)}`}
            onCerrar={cerrarLlamada}
            className="animate-entrar"
          >
            {tel.llamada?.estado === "terminada" && (
              <RespuestaPorTelefono llamada={tel.llamada} mensajes={mensajes} cotizacion={cotPorMensaje} />
            )}
          </PanelLlamada>
        )}

        <div className="flex flex-col gap-2">
          {cotizaciones.length > 0 && (
            <Button variant={todosListos ? "outline" : "default"} onClick={() => navigate("/cotizaciones")}>
              Ver cotizaciones ({cotizaciones.length})
            </Button>
          )}
          {todosListos && (
            <Button onClick={() => navigate("/plan")}>
              Armar el plan de compra <ArrowRightIcon />
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}

function Burbuja({ mensaje, cotizacion }: { mensaje: MensajeCrudo; cotizacion?: Cotizacion }) {
  const canal = CANALES[mensaje.canal];
  return (
    <div className="flex animate-entrar items-end gap-2">
      <Avatar proveedorId={mensaje.proveedor_id} className="size-8 text-[10px]" />
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-background p-3 shadow-xs ring-1 ring-foreground/10 sm:max-w-[36rem]">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-sm font-medium">{nombreProveedor(mensaje.proveedor_id)}</span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <canal.icono className="size-3" /> {canal.etiqueta}
          </span>
        </div>
        <VistaMensaje mensaje={mensaje} />
        <p className="mt-1 text-right text-[11px] text-muted-foreground">{hora(mensaje.recibido_en)}</p>
        <EstadoLectura mensaje={mensaje} cotizacion={cotizacion} />
      </div>
    </div>
  );
}

function EstadoLectura({ mensaje, cotizacion }: { mensaje: MensajeCrudo; cotizacion?: Cotizacion }) {
  if (mensaje.estado === "pendiente" || mensaje.estado === "leyendo") {
    return (
      <div className="mt-2 flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm">
        <Spinner />
        Abasto está leyendo {QUE_LEE[mensaje.canal] ?? "el mensaje"} <Puntos />
      </div>
    );
  }
  if (mensaje.estado === "error") {
    return (
      <div className="mt-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
        No se pudo leer este mensaje{mensaje.error ? `: ${mensaje.error}` : "."} Se puede cargar a mano.
      </div>
    );
  }
  if (!cotizacion) {
    return <div className="mt-2 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">Leído</div>;
  }
  const revisar = necesitaRevision(cotizacion);
  const n = cotizacion.items.length;
  return (
    <Link
      to={`/cotizaciones#${cotizacion.id}`}
      className={cn(
        "mt-2 flex animate-entrar items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
        revisar
          ? "border-amber-200 bg-amber-50 text-amber-900 hover:bg-amber-100 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200"
          : "hover:bg-muted",
      )}
    >
      {revisar ? <TriangleAlertIcon className="size-4" /> : <CheckIcon className="size-4 text-emerald-600" />}
      <span className="flex-1">
        {revisar
          ? `Revisar: ${cotizacion.campos_dudosos.includes("iva") ? "no aclara si incluye IVA" : "lectura con baja confianza"}`
          : `${n} ${n === 1 ? "producto extraído" : "productos extraídos"} con evidencia`}
      </span>
      <span className="flex items-center gap-1 font-medium whitespace-nowrap">
        Ver tarjeta <ArrowRightIcon className="size-3.5" />
      </span>
    </Link>
  );
}

function EstadoProveedor({ mensaje, cotizacion, tarda }: { mensaje?: MensajeCrudo; cotizacion?: Cotizacion; tarda: boolean }) {
  if (!mensaje) {
    return tarda ? (
      <Etiqueta tono="ambar">
        <ClockIcon /> Tarda
      </Etiqueta>
    ) : (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        esperando <Puntos />
      </span>
    );
  }
  if (mensaje.estado === "pendiente" || mensaje.estado === "leyendo")
    return (
      <Etiqueta>
        <Spinner className="size-3" /> Leyendo
      </Etiqueta>
    );
  if (mensaje.estado === "error") return <Etiqueta tono="rojo">Error</Etiqueta>;
  if (cotizacion && necesitaRevision(cotizacion)) return <Etiqueta tono="ambar">Revisar</Etiqueta>;
  return (
    <Etiqueta tono="verde">
      <CheckIcon /> Listo
    </Etiqueta>
  );
}

/** Al terminar la llamada: la respuesta entra al feed como un mensaje más y pasa por la extracción. */
function RespuestaPorTelefono({
  llamada,
  mensajes,
  cotizacion,
}: {
  llamada: Llamada;
  mensajes: MensajeCrudo[];
  cotizacion: (m: MensajeCrudo) => Cotizacion | undefined;
}) {
  const nombre = nombreProveedor(llamada.proveedor_id);
  const m =
    mensajes.find((x) => x.id === llamada.mensaje_id) ??
    mensajes.find((x) => x.proveedor_id === llamada.proveedor_id && x.canal === "llamada");
  const cotId = m ? (m.cotizacion_id ?? cotizacion(m)?.id) : undefined;
  if (!m || m.estado === "pendiente" || m.estado === "leyendo") {
    return (
      <p className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm">
        <Spinner /> Abasto está leyendo la llamada <Puntos />
      </p>
    );
  }
  if (m.estado === "error") {
    return (
      <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
        La llamada terminó pero no se pudo leer{m.error ? `: ${m.error}` : "."}
      </p>
    );
  }
  return (
    <Link
      to={cotId ? `/cotizaciones#${cotId}` : "/cotizaciones"}
      className="flex animate-entrar items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 transition-colors hover:bg-emerald-100 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
    >
      <CheckIcon className="size-4 shrink-0" />
      <span className="flex-1">La cotización de {nombre} entró por teléfono</span>
      <span className="flex items-center gap-1 font-medium whitespace-nowrap">
        Ver tarjeta <ArrowRightIcon className="size-3.5" />
      </span>
    </Link>
  );
}
