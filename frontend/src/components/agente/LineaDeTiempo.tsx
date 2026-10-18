import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRightIcon,
  BotIcon,
  CheckIcon,
  CircleAlertIcon,
  MinusIcon,
  PauseIcon,
  PhoneIcon,
  TrendingDownIcon,
  XIcon,
} from "lucide-react";
import { aPorcentaje, fechaCorta, formatNumero, pesos, porcentaje, precioUnitario, unidad } from "@/lib/format";
import { CANALES, PROVEEDORES, nombreProveedor } from "@/lib/proveedores";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Avatar, Etiqueta, Puntos } from "@/components/comunes";
import TarjetaOrden from "@/components/agente/TarjetaOrden";
import type {
  CorridaAgente,
  Cotizacion,
  EstadoPaso,
  Llamada,
  MensajeCrudo,
  Negociacion,
  PasoAgente,
  Plan,
} from "@/types";

/** Todo lo que el agente fue juntando, para mostrar debajo de cada paso. */
export interface DatosCorrida {
  mensajes: MensajeCrudo[];
  cotizaciones: Cotizacion[];
  llamadas: Llamada[];
  plan: Plan | null;
  negociacion: Negociacion | null;
}

export default function LineaDeTiempo({ corrida, datos }: { corrida: CorridaAgente; datos: DatosCorrida }) {
  return (
    <ol className="relative">
      {corrida.pasos.map((paso, i) => (
        <PasoItem key={paso.id} paso={paso} ultimo={i === corrida.pasos.length - 1}>
          <Contenido paso={paso} corrida={corrida} datos={datos} />
        </PasoItem>
      ))}
    </ol>
  );
}

function PasoItem({ paso, ultimo, children }: { paso: PasoAgente; ultimo: boolean; children: ReactNode }) {
  const activo = paso.estado === "en_curso" || paso.estado === "esperando";
  const apagado = paso.estado === "pendiente" || paso.estado === "omitido";
  return (
    <li className="relative flex gap-4 pb-6">
      {!ultimo && <span aria-hidden className="absolute top-8 bottom-0 left-[15px] w-px bg-border" />}
      <IconoPaso estado={paso.estado} />
      <div
        className={cn(
          "min-w-0 flex-1 rounded-xl border p-4 transition-colors",
          activo ? "border-foreground/20 bg-background shadow-sm" : "bg-background",
          apagado && "border-dashed bg-transparent",
          paso.estado === "error" && "border-red-200 dark:border-red-900",
        )}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <p className={cn("font-medium", apagado && "text-muted-foreground")}>{paso.titulo}</p>
          <Duracion paso={paso} />
        </div>
        {paso.detalle && (
          <p
            className={cn(
              "mt-1 text-sm",
              paso.estado === "error" ? "text-red-700 dark:text-red-300" : "text-muted-foreground",
            )}
          >
            {paso.estado === "en_curso" ? (
              <>
                {paso.detalle} <Puntos />
              </>
            ) : (
              paso.detalle
            )}
          </p>
        )}
        {children}
      </div>
    </li>
  );
}

function IconoPaso({ estado }: { estado: EstadoPaso }) {
  const base = "relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border bg-background";
  switch (estado) {
    case "en_curso":
      return (
        <span className={cn(base, "border-foreground/30")}>
          <Spinner className="size-4" />
        </span>
      );
    case "esperando":
      return (
        <span className={cn(base, "border-amber-300 bg-amber-50 text-amber-700 dark:bg-amber-950")}>
          <PauseIcon className="size-3.5 fill-current" />
        </span>
      );
    case "hecho":
      return (
        <span className={cn(base, "border-transparent bg-primary text-primary-foreground")}>
          <CheckIcon className="size-4" />
        </span>
      );
    case "omitido":
      return (
        <span className={cn(base, "text-muted-foreground")}>
          <MinusIcon className="size-4" />
        </span>
      );
    case "error":
      return (
        <span className={cn(base, "border-red-300 bg-red-50 text-red-700 dark:bg-red-950")}>
          <XIcon className="size-4" />
        </span>
      );
    default:
      return <span className={cn(base, "border-dashed")} />;
  }
}

function Duracion({ paso }: { paso: PasoAgente }) {
  if (!paso.inicio || !paso.fin) return null;
  const s = Math.max(0, Math.round((Date.parse(paso.fin) - Date.parse(paso.inicio)) / 1000));
  if (s < 1) return null;
  return <span className="text-xs text-muted-foreground tabular-nums">{s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`}</span>;
}

function Contenido({ paso, corrida, datos }: { paso: PasoAgente; corrida: CorridaAgente; datos: DatosCorrida }) {
  if (paso.estado === "pendiente") return null;
  switch (paso.id) {
    case "entender":
      return <Entendido corrida={corrida} />;
    case "inventario":
      return <Propuesta corrida={corrida} />;
    case "cotizar":
      return <Respuestas corrida={corrida} datos={datos} />;
    case "insistir":
      return <Llamadas llamadas={datos.llamadas} />;
    case "revisar":
      return paso.estado === "hecho" ? <Repreguntas detalle={paso.detalle} /> : null;
    case "optimizar":
      return datos.plan ? <ResumenPlan plan={datos.plan} /> : null;
    case "negociar":
      return datos.negociacion ? <ResumenNegociacion negociacion={datos.negociacion} /> : null;
    case "ordenes":
      return corrida.ordenes.length ? (
        <div className="mt-3 space-y-2">
          {corrida.ordenes.map((o) => (
            <TarjetaOrden key={o.id} orden={o} />
          ))}
        </div>
      ) : null;
    default:
      return null;
  }
}

function Entendido({ corrida }: { corrida: CorridaAgente }) {
  const leido = corrida.interpretacion;
  if (!leido || leido.items.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {leido.items.map((i) => (
          <Etiqueta key={i.producto_id} className="h-auto py-1" title={`“${i.evidencia}”`}>
            {i.cantidad !== null ? `${formatNumero(i.cantidad)} · ` : ""}
            {i.descripcion}
            {i.necesario_para ? ` · para el ${fechaCorta(i.necesario_para)}` : ""}
          </Etiqueta>
        ))}
      </div>
      {leido.no_entendido.length > 0 && (
        <p className="text-xs text-amber-800 dark:text-amber-300">No entendí: {leido.no_entendido.join(", ")}.</p>
      )}
    </div>
  );
}

function Propuesta({ corrida }: { corrida: CorridaAgente }) {
  if (corrida.propuesta.length === 0) return null;
  return (
    <ul className="mt-3 divide-y rounded-lg border text-sm">
      {corrida.propuesta.map((l) => (
        <li key={l.producto_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2">
          <span className="font-medium tabular-nums">
            {formatNumero(l.cantidad)} {l.unidad === "unidad" ? "" : unidad(l.unidad) + " de "}
            {l.nombre_corto}
          </span>
          <Etiqueta tono={l.origen === "pedido" ? "azul" : "neutro"}>
            {l.origen === "pedido" ? "Lo pediste" : "Reposición"}
          </Etiqueta>
          <span className="text-xs text-muted-foreground">para el {fechaCorta(l.necesario_para)}</span>
          <span className="basis-full text-xs text-muted-foreground">{l.evidencia}</span>
        </li>
      ))}
    </ul>
  );
}

function Respuestas({ corrida, datos }: { corrida: CorridaAgente; datos: DatosCorrida }) {
  const llegaron = datos.mensajes.length;
  return (
    <div className="mt-3 space-y-2">
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {PROVEEDORES.map((p) => {
          const m = datos.mensajes.find((x) => x.proveedor_id === p.id);
          const c = m ? datos.cotizaciones.find((x) => x.mensaje_id === m.id) : undefined;
          const canal = CANALES[m?.canal ?? p.canal_preferido];
          return (
            <li key={p.id} className="flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm">
              <Avatar proveedorId={p.id} className="size-6 text-[9px]" />
              <span className="min-w-0 flex-1 truncate">{p.nombre}</span>
              {canal && <canal.icono className="size-3.5 shrink-0 text-muted-foreground" aria-label={canal.etiqueta} />}
              <EstadoRespuesta mensaje={m} cotizacion={c} sinRespuesta={corrida.sin_respuesta.includes(p.id)} />
            </li>
          );
        })}
      </ul>
      {llegaron > 0 && (
        <div className="flex flex-wrap gap-1">
          <Button asChild variant="link" size="xs" className="px-0">
            <Link to="/feed">
              Ver los mensajes <ArrowRightIcon />
            </Link>
          </Button>
          <Button asChild variant="link" size="xs">
            <Link to="/cotizaciones">
              Ver las cotizaciones con su evidencia <ArrowRightIcon />
            </Link>
          </Button>
        </div>
      )}
    </div>
  );
}

function EstadoRespuesta({
  mensaje,
  cotizacion,
  sinRespuesta,
}: {
  mensaje?: MensajeCrudo;
  cotizacion?: Cotizacion;
  sinRespuesta: boolean;
}) {
  if (!mensaje)
    return sinRespuesta ? (
      <Etiqueta tono="rojo">Sin respuesta</Etiqueta>
    ) : (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        esperando <Puntos />
      </span>
    );
  if (mensaje.estado === "pendiente" || mensaje.estado === "leyendo")
    return (
      <Etiqueta>
        <Spinner className="size-3" /> Leyendo
      </Etiqueta>
    );
  if (mensaje.estado === "error") return <Etiqueta tono="rojo">No se pudo leer</Etiqueta>;
  if (cotizacion?.estado === "revisar") return <Etiqueta tono="ambar">Con dudas</Etiqueta>;
  if (cotizacion?.estado === "confirmada") return <Etiqueta tono="verde">Aclarada</Etiqueta>;
  return (
    <Etiqueta tono="verde">
      <CheckIcon />{" "}
      {cotizacion ? `${cotizacion.items.length} ${cotizacion.items.length === 1 ? "precio" : "precios"}` : "Leída"}
    </Etiqueta>
  );
}

function Llamadas({ llamadas }: { llamadas: Llamada[] }) {
  if (llamadas.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      {llamadas.map((l) => (
        <div key={l.id} className="rounded-lg border p-3">
          <div className="mb-2 flex items-center gap-2 text-sm">
            <PhoneIcon className="size-4 text-muted-foreground" />
            <span className="font-medium">{nombreProveedor(l.proveedor_id)}</span>
            <span className="text-xs text-muted-foreground">{l.modo === "real" ? "llamada real" : "llamada simulada"}</span>
            <span className="ml-auto">
              {l.estado === "terminada" ? (
                <Etiqueta tono="verde">Terminada</Etiqueta>
              ) : l.estado === "fallida" ? (
                <Etiqueta tono="rojo">No salió</Etiqueta>
              ) : (
                <Etiqueta>
                  <Spinner className="size-3" /> {l.estado === "sonando" ? "Sonando" : "En curso"}
                </Etiqueta>
              )}
            </span>
          </div>
          <div className="space-y-1.5">
            {l.transcripcion.slice(-4).map((t, k) => (
              <Burbuja key={k} deAbasto={t.rol === "abasto"} texto={t.texto} />
            ))}
          </div>
          {l.resultado?.resumen && <p className="mt-2 text-xs text-muted-foreground">{l.resultado.resumen}</p>}
        </div>
      ))}
    </div>
  );
}

/** "Le pregunté a X: «…». Respondió: «…»." → la charla en burbujas. */
function Repreguntas({ detalle }: { detalle: string | null }) {
  if (!detalle) return null;
  const charlas = [...detalle.matchAll(/Le pregunté a (.+?): «(.+?)»\. Respondió: «(.+?)»\./g)];
  if (charlas.length === 0) return null;
  return (
    <div className="mt-3 space-y-3">
      {charlas.map(([, proveedor, pregunta, respuesta], k) => (
        <div key={k} className="space-y-1.5 rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">WhatsApp con {proveedor}</p>
          <Burbuja deAbasto texto={pregunta} />
          <Burbuja deAbasto={false} texto={respuesta} />
        </div>
      ))}
    </div>
  );
}

function Burbuja({ deAbasto, texto }: { deAbasto: boolean; texto: string }) {
  return (
    <div className={cn("flex", deAbasto ? "justify-end" : "justify-start")}>
      <p
        className={cn(
          "max-w-[85%] rounded-xl px-3 py-1.5 text-sm",
          deAbasto ? "rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm bg-muted",
        )}
      >
        {deAbasto && <BotIcon className="mr-1 inline size-3.5 opacity-70" />}
        {texto}
      </p>
    </div>
  );
}

function ResumenPlan({ plan }: { plan: Plan }) {
  const caso = plan.no_mas_barato?.[0];
  return (
    <div className="mt-3 space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <p className="text-xs text-muted-foreground">Ahorro contra el proveedor de siempre</p>
          <p className="text-2xl font-semibold tracking-tight tabular-nums">{pesos(plan.ahorro)}</p>
        </div>
        <Etiqueta tono="verde">
          <TrendingDownIcon /> {porcentaje(aPorcentaje(plan.ahorro_pct))}
        </Etiqueta>
        <div className="text-sm text-muted-foreground">
          Total {pesos(plan.costo_total)} + IVA · {plan.proveedores_usados.length} proveedores
        </div>
      </div>
      {caso && (
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">No siempre el más barato:</span> {nombreProveedor(caso.mas_barato_id)}{" "}
          cotiza {precioUnitario(caso.precio_mas_barato)}, pero {caso.motivo.replace(nombreProveedor(caso.mas_barato_id), "").trim()}.
        </p>
      )}
      <Button asChild variant="link" size="xs" className="px-0">
        <Link to="/plan">
          Ver el plan y por qué <ArrowRightIcon />
        </Link>
      </Button>
    </div>
  );
}

function ResumenNegociacion({ negociacion }: { negociacion: Negociacion }) {
  const enviada = negociacion.estado !== "simulada";
  return (
    <div className="mt-3 space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap gap-1.5">
        {negociacion.estrategias.map((e) => (
          <Etiqueta key={e.nombre} tono={e.nombre === negociacion.elegida ? "verde" : "neutro"}>
            {e.nombre === negociacion.elegida && <CheckIcon />}
            {e.nombre}: {pesos(e.ganancia_esperada_uyu)}
          </Etiqueta>
        ))}
      </div>
      <blockquote className="border-l-2 pl-3 text-sm italic">“{negociacion.mensaje_propuesto}”</blockquote>
      <div className="flex flex-wrap items-center gap-2">
        {enviada ? (
          <Etiqueta tono="verde">
            <BotIcon /> Mensaje enviado (simulado)
          </Etiqueta>
        ) : (
          <Etiqueta tono="ambar">
            <CircleAlertIcon /> Listo para aprobar
          </Etiqueta>
        )}
        <Button asChild variant="link" size="xs">
          <Link to={`/negociacion/${negociacion.proveedor_id}`}>
            Ver el ensayo completo <ArrowRightIcon />
          </Link>
        </Button>
      </div>
    </div>
  );
}
