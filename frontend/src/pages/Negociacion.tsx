import { useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeftIcon,
  BanknoteIcon,
  CheckIcon,
  HandshakeIcon,
  PackageIcon,
  PhoneIcon,
  ScaleIcon,
  SendIcon,
  StarIcon,
  type LucideIcon,
} from "lucide-react";
import * as api from "@/api";
import type { EnCurso } from "@/App";
import { mensajeError } from "@/lib/errores";
import { aPorcentaje, monedaOriginal, pesos, porcentaje, precioUnitario } from "@/lib/format";
import { nombreProveedor, proveedor } from "@/lib/proveedores";
import { useReloj } from "@/lib/usePolling";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, Encabezado, ErrorBanner, Etiqueta, type Tono } from "@/components/comunes";
import EvaluacionNegociacion from "@/features/proveedores/EvaluacionNegociacion";
import PanelLlamada, { BotonLlamar, ModoLlamadas, estaActiva, useConfigLlamadas, useLlamada } from "@/components/PanelLlamada";
import type {
  Cotizacion,
  EstrategiaNegociacion,
  Llamada,
  Negociacion,
  NombreEstrategia,
  PedidoDemo,
  Plan,
  Producto,
} from "@/types";

const ESTRATEGIAS: Record<NombreEstrategia, { icono: LucideIcon; titulo: string; resumen: string }> = {
  competencia: { icono: ScaleIcon, titulo: "Competencia", resumen: "Mencionar la mejor cotización alternativa real" },
  volumen: { icono: PackageIcon, titulo: "Volumen", resumen: "Comprometer compras futuras" },
  plazo: { icono: BanknoteIcon, titulo: "Plazo de pago", resumen: "Ofrecer pago contado a cambio de descuento" },
};

const RIESGO: Record<EstrategiaNegociacion["riesgo"], Tono> = { bajo: "verde", medio: "ambar", alto: "rojo" };

const MAX_PALABRAS = 80;

export default function NegociacionPage({
  demo,
  plan,
  negociaciones,
  negociando,
  iniciarNegociacion,
  onAprobada,
}: {
  demo: PedidoDemo;
  plan: Plan | null;
  negociaciones: Record<string, Negociacion>;
  negociando: Record<string, EnCurso>;
  iniciarNegociacion: (proveedorId: string) => void;
  onAprobada: (neg: Negociacion) => void;
}) {
  const { proveedorId } = useParams();
  const navigate = useNavigate();
  const neg = proveedorId ? negociaciones[proveedorId] : undefined;
  const curso = proveedorId ? negociando[proveedorId] : undefined;
  const corriendo = !!curso && !curso.error;
  const ahora = useReloj(1000, corriendo);

  const [cotizaciones, setCotizaciones] = useState<Cotizacion[] | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [aprobando, setAprobando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [llamarPedido, setLlamarPedido] = useState(false);

  // "Aprobar y llamar": el clic es la aprobación; antes no se llama a nadie.
  const config = useConfigLlamadas();
  const tel = useLlamada("llamada_negociacion", (simulada) => api.llamarParaNegociar(neg!.id, mensaje.trim(), simulada));
  const llamada = tel.llamada && neg && tel.llamada.negociacion_id === neg.id ? tel.llamada : null;
  const intentoLlamar = !!llamada || tel.iniciando || (!!tel.error && !!neg && tel.llamada === null && llamarPedido);
  const { setLlamada } = tel;
  const panel = useRef<HTMLDivElement>(null);

  // Tras un F5 (o volver a la página): la negociación recuerda su llamada_id.
  useEffect(() => {
    if (!neg?.llamada_id || tel.llamada?.id === neg.llamada_id) return;
    api
      .getLlamada(neg.llamada_id)
      .then(setLlamada)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [neg?.llamada_id]);

  useEffect(() => {
    api
      .getCotizaciones(demo.pedido.id)
      .then(setCotizaciones)
      .catch((e) => setError(mensajeError(e)));
  }, [demo.pedido.id]);

  const cotizacion = cotizaciones?.find((c) => c.proveedor_id === proveedorId) ?? null;
  const opciones = opcionesNegociacion(cotizaciones ?? [], plan);
  const elegir = (id: string) => navigate(`/negociacion/${id}`);

  useEffect(() => {
    setMensaje(neg?.mensaje_propuesto ?? "");
  }, [neg?.id, neg?.mensaje_propuesto]);

  useEffect(() => {
    if (!aviso) return;
    const id = setTimeout(() => setAviso(null), 4000);
    return () => clearTimeout(id);
  }, [aviso]);

  if (!proveedorId) {
    // Si el plan sugiere con quién negociar se va directo; si no, se elige de la lista (que marca los ya ensayados).
    const sugerido = plan?.oportunidad_negociacion;
    if (sugerido) return <Navigate to={`/negociacion/${sugerido}`} replace />;
    if (cotizaciones === null) {
      return error ? (
        <ErrorBanner mensaje={error} />
      ) : (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando proveedores…
        </div>
      );
    }
    if (opciones.length === 0) {
      return (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <HandshakeIcon />
            </EmptyMedia>
            <EmptyTitle>Todavía no hay con quién negociar</EmptyTitle>
            <EmptyDescription>Se puede ensayar la negociación con cualquier proveedor que haya cotizado.</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button onClick={() => navigate("/pedido")}>Ir al pedido</Button>
          </EmptyContent>
        </Empty>
      );
    }
    return (
      <div className="space-y-6">
        <Encabezado
          titulo="Negociación"
          bajada={
            plan
              ? "El plan no marca una brecha clara con ningún proveedor. Igual podés ensayar la negociación con cualquiera que haya cotizado."
              : "Elegí con qué proveedor ensayar la negociación. Con el plan armado, Abasto sugiere dónde hay más margen."
          }
        />
        <ElegirProveedor opciones={opciones} negociaciones={negociaciones} negociando={negociando} onElegir={elegir} />
      </div>
    );
  }

  const nombre = nombreProveedor(proveedorId);
  const enviada = neg?.estado === "enviada_simulada" || neg?.estado === "aprobada";
  const porTelefono = !!neg?.llamada_id || !!llamada;
  const palabras = mensaje.trim() ? mensaje.trim().split(/\s+/).length : 0;
  const elegida = neg?.estrategias.find((e) => e.nombre === neg.elegida);
  const enPlan = plan?.asignaciones.filter((a) => a.proveedor_id === proveedorId) ?? [];

  const aprobar = async () => {
    if (!neg) return;
    setAprobando(true);
    setError(null);
    try {
      const actualizada = await api.aprobar(neg.id, mensaje.trim());
      onAprobada(actualizada);
      setAviso(`Enviado (simulado) a ${nombre} por WhatsApp`);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setAprobando(false);
    }
  };

  const aprobarYLlamar = async () => {
    if (!neg) return;
    setError(null);
    setLlamarPedido(true);
    // El panel aparece abajo de todo: llevarlo a la vista para seguir la llamada.
    setTimeout(() => panel.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    const texto = mensaje.trim();
    const l = await tel.iniciarCon((simulada) => api.llamarParaNegociar(neg.id, texto, simulada));
    // El backend deja la negociación "aprobada" con su llamada_id.
    if (l) onAprobada({ ...neg, mensaje_propuesto: texto, estado: "aprobada", llamada_id: l.id });
  };

  return (
    <div className="space-y-6">
      <Encabezado
        titulo={`Negociación con ${nombre}`}
        bajada={`Antes de escribirle, Abasto simula la conversación contra un gemelo digital de ${nombre}: 3 estrategias × 2 corridas × 3 rondas. Mide cuál consigue más y propone el mensaje. Nada se envía sin tu aprobación.`}
      >
        <Button variant="ghost" onClick={() => navigate("/plan")}>
          <ArrowLeftIcon /> Volver al plan
        </Button>
      </Encabezado>

      {cotizacion && (
        <Card size="sm">
          <CardHeader>
            <div className="flex items-center gap-3">
              <Avatar proveedorId={proveedorId} />
              <div className="min-w-0 space-y-1">
                <CardDescription>Cotización actual</CardDescription>
                {cotizacion.items.map((i, k) => {
                  const producto = demo.catalogo.find((p) => p.id === i.producto_id)?.nombre ?? i.descripcion_original;
                  return (
                    <p key={k}>
                      <span className="font-medium">{producto}:</span> {precioUnitario(i.precio_unitario_sin_iva)} sin IVA{" "}
                      <span className="text-muted-foreground italic">
                        (“{i.evidencia}” · {monedaOriginal(i.precio_original, i.moneda_original)})
                      </span>
                    </p>
                  );
                })}
              </div>
            </div>
            {enPlan.length > 0 && (
              <CardAction className="text-right">
                <p className="text-xs text-muted-foreground">En el plan</p>
                <p className="text-xl font-semibold tabular-nums">{pesos(enPlan.reduce((s, a) => s + a.subtotal, 0))}</p>
              </CardAction>
            )}
          </CardHeader>
        </Card>
      )}

      {cotizaciones !== null && !cotizacion && (
        <ErrorBanner mensaje={`${nombre} no tiene una cotización para este pedido. Elegí otro proveedor.`} />
      )}

      {opciones.length > 1 && (
        <OtrosProveedores opciones={opciones} actual={proveedorId} negociaciones={negociaciones} onElegir={elegir} />
      )}

      <ErrorBanner mensaje={error} />
      {curso?.error && (
        <ErrorBanner mensaje={`La simulación falló: ${curso.error}`} onReintentar={() => iniciarNegociacion(proveedorId)} />
      )}

      {!neg && !curso && cotizacion && (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <HandshakeIcon />
            </EmptyMedia>
            <EmptyTitle>Ensayar la negociación</EmptyTitle>
            <EmptyDescription>Simula 3 estrategias contra el gemelo de {nombre} y propone el mejor mensaje.</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button size="lg" onClick={() => iniciarNegociacion(proveedorId)}>
              Ensayar negociación con {nombre}
            </Button>
          </EmptyContent>
        </Empty>
      )}

      {(corriendo || neg) && (
        <div className="grid gap-4 lg:grid-cols-3">
          {corriendo
            ? (Object.keys(ESTRATEGIAS) as NombreEstrategia[]).map((n) => (
                <ColumnaCargando key={n} nombre={n} segundos={Math.round((ahora - curso!.desde) / 1000)} proveedor={nombre} />
              ))
            : neg!.estrategias.map((e) => <ColumnaEstrategia key={e.nombre} e={e} elegida={e.nombre === neg!.elegida} />)}
        </div>
      )}

      {neg && !corriendo && <EvaluacionNegociacion negociacionId={neg.id} />}

      {neg && !corriendo && (
        <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
          <Card>
            <CardHeader>
              <CardTitle>Mensaje propuesto para {nombre}</CardTitle>
              <CardDescription>Podés editarlo antes de aprobar. El envío es simulado.</CardDescription>
              <CardAction>
                {enviada && porTelefono ? (
                  <Etiqueta tono="verde">
                    <PhoneIcon /> Aprobado · por teléfono
                  </Etiqueta>
                ) : enviada ? (
                  <Etiqueta tono="verde">
                    <CheckIcon /> Enviado (simulado)
                  </Etiqueta>
                ) : (
                  <span
                    className={cn(
                      "text-xs tabular-nums",
                      palabras > MAX_PALABRAS ? "font-medium text-amber-700" : "text-muted-foreground",
                    )}
                  >
                    {palabras}/{MAX_PALABRAS} palabras
                  </span>
                )}
              </CardAction>
            </CardHeader>
            <CardContent>
              <Textarea
                value={mensaje}
                onChange={(e) => setMensaje(e.target.value)}
                disabled={enviada}
                rows={5}
                className="text-base leading-relaxed"
              />
            </CardContent>
            <CardFooter className="flex-wrap gap-x-3 gap-y-2">
              {enviada && porTelefono ? (
                <p className="text-muted-foreground">
                  Aprobado por {demo.pedido.comprador?.split(" ")[0] ?? "quien compra"}: Abasto llamó a {nombre} para negociar
                  con este mensaje.
                </p>
              ) : enviada ? (
                <p className="text-muted-foreground">
                  Aprobado por {demo.pedido.comprador?.split(" ")[0] ?? "quien compra"} y enviado (simulado) a {nombre} por
                  WhatsApp.
                </p>
              ) : (
                <>
                  <Button size="lg" onClick={aprobar} disabled={aprobando || tel.iniciando || !mensaje.trim()}>
                    {aprobando ? <Spinner /> : <SendIcon />} Aprobar y enviar
                  </Button>
                  <BotonLlamar
                    config={config}
                    proveedorId={proveedorId}
                    size="lg"
                    variant="outline"
                    onClick={aprobarYLlamar}
                    disabled={aprobando || tel.iniciando || !mensaje.trim()}
                  >
                    {tel.iniciando ? <Spinner /> : <PhoneIcon />} Aprobar y llamar
                  </BotonLlamar>
                  <ModoLlamadas config={config} className="ml-auto" />
                </>
              )}
            </CardFooter>
          </Card>

          {elegida && (
            <Card>
              <CardHeader>
                <CardDescription>Por qué esta estrategia</CardDescription>
                <CardTitle className="flex items-center gap-2">
                  {(() => {
                    const Icono = ESTRATEGIAS[elegida.nombre]?.icono ?? StarIcon;
                    return <Icono className="size-4" />;
                  })()}
                  {ESTRATEGIAS[elegida.nombre]?.titulo ?? elegida.nombre}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-muted-foreground">
                <p>
                  Consiguió la mayor ganancia esperada en la simulación ({pesos(elegida.ganancia_esperada_uyu)},{" "}
                  {porcentaje(aPorcentaje(elegida.concesion_obtenida_pct))} de concesión) con riesgo {elegida.riesgo}.
                </p>
                <p>Abasto nunca negocia solo: propone, y quien compra aprueba cada mensaje.</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {neg && !corriendo && intentoLlamar && (
        <div ref={panel} className="grid scroll-mt-20 items-start gap-4 lg:grid-cols-[1fr_22rem]">
          <PanelLlamada proveedorId={proveedorId} tel={tel} titulo={`Llamada para negociar con ${nombre}`} />
          <ResultadoLlamada llamada={llamada} plan={plan} proveedorId={proveedorId} catalogo={demo.catalogo} />
        </div>
      )}

      {aviso && (
        <div className="fixed right-6 bottom-6 z-50 flex animate-entrar items-center gap-3 rounded-lg border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-lg">
          <CheckIcon className="size-4 text-emerald-600" />
          {aviso}
        </div>
      )}
    </div>
  );
}

function ColumnaCargando({ nombre, segundos, proveedor }: { nombre: NombreEstrategia; segundos: number; proveedor: string }) {
  const info = ESTRATEGIAS[nombre];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <info.icono className="size-4" /> {info.titulo}
        </CardTitle>
        <CardDescription>{info.resumen}</CardDescription>
      </CardHeader>
      <CardContent className="gap-4">
        <p className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Conversando con el gemelo de {proveedor}… {segundos} s
        </p>
        <div className="space-y-2" aria-hidden>
          {[70, 85, 60, 78].map((w, i) => (
            <Skeleton key={i} className={cn("h-9 rounded-xl", i % 2 === 0 && "ml-auto")} style={{ width: `${w}%` }} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function ColumnaEstrategia({ e, elegida }: { e: EstrategiaNegociacion; elegida: boolean }) {
  const [completa, setCompleta] = useState(false);
  const info = ESTRATEGIAS[e.nombre] ?? { icono: StarIcon, titulo: e.nombre, resumen: "" };
  const turnos = completa ? e.transcripcion : e.transcripcion.slice(0, 2);
  const pct = aPorcentaje(e.concesion_obtenida_pct);
  return (
    <Card className={cn(elegida ? "shadow-md ring-2 ring-primary" : "opacity-90")}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <info.icono className="size-4" /> {info.titulo}
        </CardTitle>
        <CardDescription>{e.descripcion || info.resumen}</CardDescription>
        {elegida && (
          <CardAction>
            <Badge>
              <StarIcon className="fill-current" /> Elegida
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      <CardContent className="gap-4">
        <div className="flex items-end justify-between gap-2">
          <div>
            <p className={cn("text-3xl font-semibold tracking-tight tabular-nums", e.ganancia_esperada_uyu <= 0 && "text-muted-foreground")}>
              {pesos(e.ganancia_esperada_uyu)}
            </p>
            <p className="text-xs text-muted-foreground">ganancia esperada · {porcentaje(pct)} de concesión</p>
          </div>
          <Etiqueta tono={RIESGO[e.riesgo] ?? "neutro"}>riesgo {e.riesgo}</Etiqueta>
        </div>

        <div className="space-y-2 rounded-lg bg-muted/50 p-3">
          {turnos.map((t, k) => (
            <div key={k} className={cn("flex", t.rol === "abasto" ? "justify-end" : "justify-start")}>
              <p
                className={cn(
                  "max-w-[90%] rounded-xl px-3 py-2 leading-snug",
                  t.rol === "abasto"
                    ? "rounded-br-sm bg-primary text-primary-foreground"
                    : "rounded-bl-sm bg-background shadow-xs ring-1 ring-foreground/10",
                )}
              >
                <span className="mb-0.5 block text-[10px] font-medium tracking-wide uppercase opacity-60">
                  {t.rol === "abasto" ? "Abasto" : "Gemelo del proveedor"}
                </span>
                {t.texto}
              </p>
            </div>
          ))}
          {e.transcripcion.length > 2 && (
            <Button variant="link" size="xs" className="w-full" onClick={() => setCompleta(!completa)}>
              {completa ? "Ver menos" : `Ver conversación completa (${e.transcripcion.length} mensajes)`}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

interface OpcionNegociacion {
  id: string;
  sugerido: boolean;
  enPlan: number | null; // lo que se le compra en el plan; null si no entra
}

/** Cualquier proveedor que cotizó: primero el que sugiere el plan, después los del plan, después el resto. */
function opcionesNegociacion(cotizaciones: Cotizacion[], plan: Plan | null): OpcionNegociacion[] {
  const ids = [...new Set(cotizaciones.map((c) => c.proveedor_id))];
  return ids
    .map((id) => {
      const asignadas = plan?.asignaciones.filter((a) => a.proveedor_id === id) ?? [];
      return {
        id,
        sugerido: plan?.oportunidad_negociacion === id,
        enPlan: asignadas.length ? asignadas.reduce((s, a) => s + a.subtotal, 0) : null,
      };
    })
    .sort((a, b) => Number(b.sugerido) - Number(a.sugerido) || (b.enPlan ?? -1) - (a.enPlan ?? -1));
}

function EstadoNegociacion({ neg, curso }: { neg?: Negociacion; curso?: EnCurso }) {
  if (curso && !curso.error)
    return (
      <Etiqueta>
        <Spinner className="size-3" /> Ensayando
      </Etiqueta>
    );
  if (neg?.estado === "enviada_simulada" || neg?.estado === "aprobada")
    return (
      <Etiqueta tono="verde">
        <CheckIcon /> Enviado
      </Etiqueta>
    );
  if (neg) return <Etiqueta>Ensayada</Etiqueta>;
  return null;
}

function ElegirProveedor({
  opciones,
  negociaciones,
  negociando,
  onElegir,
}: {
  opciones: OpcionNegociacion[];
  negociaciones: Record<string, Negociacion>;
  negociando: Record<string, EnCurso>;
  onElegir: (id: string) => void;
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {opciones.map((o) => (
        <Card key={o.id} size="sm">
          <CardHeader>
            <div className="flex items-center gap-3">
              <Avatar proveedorId={o.id} />
              <div className="min-w-0 space-y-0.5">
                <CardTitle>{nombreProveedor(o.id)}</CardTitle>
                <CardDescription className="truncate">{proveedor(o.id).rubro}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="flex-row flex-wrap gap-1.5">
            {o.sugerido && (
              <Etiqueta tono="verde">
                <StarIcon /> Sugerido por el plan
              </Etiqueta>
            )}
            <Etiqueta>{o.enPlan !== null ? `En el plan · ${pesos(o.enPlan)}` : "Fuera del plan"}</Etiqueta>
            <EstadoNegociacion neg={negociaciones[o.id]} curso={negociando[o.id]} />
          </CardContent>
          <CardFooter>
            <Button variant="outline" className="w-full" onClick={() => onElegir(o.id)}>
              Negociar con {nombreProveedor(o.id)}
            </Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}

function OtrosProveedores({
  opciones,
  actual,
  negociaciones,
  onElegir,
}: {
  opciones: OpcionNegociacion[];
  actual: string;
  negociaciones: Record<string, Negociacion>;
  onElegir: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">Ensayar con otro proveedor:</span>
      {opciones
        .filter((o) => o.id !== actual)
        .map((o) => (
          <Button key={o.id} variant="outline" size="sm" onClick={() => onElegir(o.id)} title={o.sugerido ? "Sugerido por el plan" : undefined}>
            {o.sugerido && <StarIcon className="fill-current" />}
            {nombreProveedor(o.id)}
            {negociaciones[o.id] && <CheckIcon className="text-muted-foreground" />}
          </Button>
        ))}
    </div>
  );
}

/** Resultado de la llamada de negociación: acuerdo y precio acordado frente al cotizado. */
function ResultadoLlamada({
  llamada,
  plan,
  proveedorId,
  catalogo,
}: {
  llamada: Llamada | null;
  plan: Plan | null;
  proveedorId: string;
  catalogo: Producto[];
}) {
  const r = llamada?.estado === "terminada" ? llamada.resultado : null;
  if (!r) {
    return (
      <Card size="sm">
        <CardHeader>
          <CardDescription>Resultado de la llamada</CardDescription>
          <CardTitle className="text-muted-foreground">
            {llamada?.estado === "fallida"
              ? "La llamada no se completó"
              : estaActiva(llamada) || !llamada
                ? "Aparece cuando termine la llamada"
                : "Sin resultado"}
          </CardTitle>
        </CardHeader>
      </Card>
    );
  }
  // El precio acordado es por unidad canónica, sin IVA, del primer ítem que el plan le asigna (como el backend).
  const asignacion = plan?.asignaciones.find((a) => a.proveedor_id === proveedorId);
  const cotizado = asignacion?.precio_unitario_sin_iva ?? null;
  const acordado = r.precio_acordado;
  const diferencia = cotizado !== null && acordado !== null ? cotizado - acordado : null;
  const pct = diferencia !== null && cotizado ? (diferencia / cotizado) * 100 : null;
  const total = diferencia !== null && asignacion ? diferencia * asignacion.cantidad : null;
  const producto = asignacion ? (catalogo.find((p) => p.id === asignacion.producto_id)?.nombre ?? asignacion.producto_id) : null;

  return (
    <Card size="sm" className="animate-entrar">
      <CardHeader>
        <CardDescription>Resultado de la llamada</CardDescription>
        <CardTitle className="flex items-center gap-2">
          {r.acuerdo === true ? (
            <Etiqueta tono="verde">
              <HandshakeIcon /> Hubo acuerdo
            </Etiqueta>
          ) : r.acuerdo === false ? (
            <Etiqueta tono="ambar">Sin acuerdo</Etiqueta>
          ) : (
            <Etiqueta>Acuerdo sin confirmar</Etiqueta>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="gap-4">
        {r.resumen && <p className="leading-relaxed">{r.resumen}</p>}

        {acordado !== null ? (
          <div className="space-y-2 rounded-lg border p-3">
            {producto && <p className="text-xs text-muted-foreground">{producto} · por unidad, sin IVA</p>}
            <div className="flex items-end justify-between gap-3">
              <div>
                <p className="text-xs text-muted-foreground">Acordado</p>
                <p className="text-2xl font-semibold tracking-tight tabular-nums">{precioUnitario(acordado)}</p>
              </div>
              {cotizado !== null && (
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Cotizado</p>
                  <p className="text-muted-foreground tabular-nums line-through">{precioUnitario(cotizado)}</p>
                </div>
              )}
            </div>
            {diferencia !== null && pct !== null && (
              <p
                className={cn(
                  "text-sm font-medium tabular-nums",
                  diferencia > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-muted-foreground",
                )}
              >
                {diferencia > 0 ? "−" : diferencia < 0 ? "+" : ""}
                {porcentaje(Math.abs(pct))}
                {total !== null && asignacion && (
                  <>
                    {" "}
                    · {diferencia > 0 ? "ahorro de " : diferencia < 0 ? "costo extra de " : ""}
                    {pesos(Math.abs(total))} en las {asignacion.cantidad} del plan
                  </>
                )}
              </p>
            )}
          </div>
        ) : (
          <p className="text-muted-foreground">El proveedor no dijo un precio concreto en la llamada.</p>
        )}

        {r.condicion && (
          <p className="text-sm">
            <span className="text-muted-foreground">Condición: </span>
            {r.condicion}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
