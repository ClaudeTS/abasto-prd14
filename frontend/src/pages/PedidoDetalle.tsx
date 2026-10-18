// Detalle del pedido (RF-10, RF-18): estados, cotizaciones, negociación y conversaciones por canal,
// exportación a PDF y aprobación de órdenes.
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertTriangleIcon, ArrowLeftIcon, CheckCheckIcon, PackageCheckIcon, PlayCircleIcon } from "lucide-react";
import { ErrorBanner } from "@/components/comunes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cerrarPedido, detallePedido, recibirPedido } from "@/features/pedidos/api";
import BarraEstados from "@/features/pedidos/BarraEstados";
import Facetas from "@/components/Facetas";
import Conversaciones from "@/features/pedidos/Conversaciones";
import { BadgeEstado, CLIENTE, EtiquetaEjemplo, fechaHoraLarga, fechaLarga } from "@/features/pedidos/presentacion";
import { Cotizaciones, Negociacion, Resumen } from "@/features/pedidos/Secciones";
import { TarjetaInforme, TarjetaOrdenes, TarjetaProductos } from "@/features/pedidos/TarjetasLaterales";
import type { DetallePedido, OrigenPedido } from "@/features/pedidos/types";
import RankingProveedores from "@/features/proveedores/RankingProveedores";
import { ContenidoPestana, ListaPestanas, Pestana, Pestanas } from "@/features/pedidos/ui";
import { mensajeError } from "@/lib/errores";
import { usePolling } from "@/lib/usePolling";

const COMO: Record<OrigenPedido, string> = {
  solicitud_voz: "pedido por nota de voz",
  solicitud_email: "pedido por email",
  stock_minimo: "reposición por stock mínimo",
  zafra: "compra de zafra",
  demo: "pedido de la demo guiada",
};

function Bajada({ p }: { p: DetallePedido }) {
  const partes = [CLIENTE[p.cliente_interno], `${COMO[p.origen]}${p.solicitante ? ` · ${p.solicitante}` : ""}`];
  partes.push(fechaHoraLarga(p.creado_en));
  if (p.necesario_desde) {
    partes.push(
      p.necesario_hasta && p.necesario_hasta !== p.necesario_desde
        ? `se necesita entre el ${fechaLarga(p.necesario_desde).slice(0, 5)} y el ${fechaLarga(p.necesario_hasta).slice(0, 5)}`
        : `se necesita para el ${fechaLarga(p.necesario_desde).slice(0, 5)}`,
    );
  }
  return <p className="text-muted-foreground">{partes.join(" · ")}</p>;
}

export default function PedidoDetalle() {
  const { pedidoId = "" } = useParams();
  const [pedido, setPedido] = useState<DetallePedido | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [accion, setAccion] = useState<"recibir" | "cerrar" | null>(null);
  const [pestana, setPestana] = useState("resumen");

  const cargar = useCallback(async () => {
    try {
      setPedido(await detallePedido(pedidoId));
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [pedidoId]);

  useEffect(() => {
    setPedido(null);
    cargar();
  }, [cargar]);
  // El pedido vivo cambia mientras trabaja el agente (cotizaciones que llegan, llamadas, órdenes).
  usePolling(cargar, 3000, !!pedido && !pedido.ejemplo && !["cerrado", "cancelado"].includes(pedido.estado));

  const marcar = async (que: "recibir" | "cerrar") => {
    if (!pedido) return;
    setAccion(que);
    setErrorAccion(null);
    try {
      setPedido(await (que === "recibir" ? recibirPedido : cerrarPedido)(pedido.id));
    } catch (e) {
      setErrorAccion(mensajeError(e));
    } finally {
      setAccion(null);
    }
  };

  if (!pedido) {
    return (
      <div className="mx-auto max-w-7xl space-y-4">
        <Migas numero={pedidoId} />
        {error ? (
          <ErrorBanner mensaje={error} onReintentar={cargar} />
        ) : (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Cargando el pedido…
          </div>
        )}
      </div>
    );
  }

  const mensajes = pedido.conversaciones.reduce((n, c) => n + c.mensajes.length, 0);

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <Migas numero={pedido.numero} />

      {/* Encabezado oscuro con las facetas de la plantilla institucional; la etapa actual va en celeste. */}
      <section className="relative isolate space-y-5 overflow-hidden rounded-2xl bg-negro px-6 py-5 text-white">
        <Facetas className="-z-10 w-2/5 opacity-60" />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-1.5 [&_p]:text-gris-oscuro">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl tracking-tight">
                {pedido.numero} · {pedido.titulo}
              </h1>
              <BadgeEstado estado={pedido.estado} />
              {pedido.ejemplo && <EtiquetaEjemplo />}
            </div>
            <Bajada p={pedido} />
          </div>
          <div className="flex flex-wrap gap-2">
            {pedido.demo && (
              <Button
                variant="outline"
                asChild
                className="rounded-full border-[#4a5053] bg-transparent text-white hover:bg-white/10 hover:text-white"
              >
                <Link to="/feed">
                  <PlayCircleIcon />
                  Ver en la demo guiada
                </Link>
              </Button>
            )}
            {pedido.acciones.includes("recibir") && (
              <Button className="rounded-full font-bold" onClick={() => marcar("recibir")} disabled={!!accion}>
                {accion === "recibir" ? <Spinner /> : <PackageCheckIcon />}
                Marcar como recibido
              </Button>
            )}
            {pedido.acciones.includes("cerrar") && (
              <Button className="rounded-full font-bold" onClick={() => marcar("cerrar")} disabled={!!accion}>
                {accion === "cerrar" ? <Spinner /> : <CheckCheckIcon />}
                Cerrar pedido
              </Button>
            )}
          </div>
        </div>
        <BarraEstados estado={pedido.estado} historial={pedido.historial_estados} oscuro />
      </section>
      {errorAccion && <ErrorBanner mensaje={errorAccion} />}
      {error && <ErrorBanner mensaje={error} onReintentar={cargar} />}

      {pedido.avisos.length > 0 && (
        <Alert>
          <AlertTriangleIcon />
          <AlertTitle>Avisos del agente</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-4">
              {pedido.avisos.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-start gap-4">
        <div className="flex min-w-0 flex-[3_1_560px] flex-col gap-4">
          <Pestanas value={pestana} onValueChange={setPestana}>
            <ListaPestanas aria-label="Secciones del pedido">
              <Pestana value="resumen">Resumen</Pestana>
              <Pestana value="cotizaciones">
                Cotizaciones{pedido.cotizaciones.length ? ` · ${pedido.cotizaciones.length}` : ""}
              </Pestana>
              <Pestana value="negociacion">Negociación</Pestana>
              <Pestana value="conversaciones">Conversaciones{mensajes ? ` · ${mensajes}` : ""}</Pestana>
            </ListaPestanas>
            <ContenidoPestana value="resumen">
              <Resumen pedido={pedido} />
            </ContenidoPestana>
            <ContenidoPestana value="cotizaciones">
              {/* RF-07: el ranking se calcula sobre las cotizaciones guardadas; los pedidos de ejemplo no las tienen. */}
              {!pedido.ejemplo && pedido.cotizaciones.length > 0 && <RankingProveedores pedidoId={pedido.id} />}
              <Cotizaciones pedido={pedido} />
            </ContenidoPestana>
            <ContenidoPestana value="negociacion">
              <Negociacion pedido={pedido} />
            </ContenidoPestana>
            <ContenidoPestana value="conversaciones">
              <Conversaciones conversaciones={pedido.conversaciones} />
            </ContenidoPestana>
          </Pestanas>
        </div>

        <aside className="flex min-w-0 flex-[1_1_280px] flex-col gap-4" aria-label="Acciones del pedido">
          <TarjetaInforme pedido={pedido} />
          <TarjetaOrdenes pedido={pedido} onCambio={cargar} />
          <TarjetaProductos pedido={pedido} />
        </aside>
      </div>
    </div>
  );
}

function Migas({ numero }: { numero: string }) {
  return (
    <nav aria-label="Migas" className="flex items-center gap-1.5 text-sm text-muted-foreground">
      <Link to="/pedidos" className="inline-flex items-center gap-1 hover:text-foreground">
        <ArrowLeftIcon className="size-3.5" aria-hidden />
        Pedidos
      </Link>
      <span aria-hidden>/</span>
      <span className="text-foreground">{numero}</span>
    </nav>
  );
}
