import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import * as api from "./api";
import Layout from "./components/Layout";
import { ErrorBanner } from "./components/comunes";
import { Spinner } from "./components/ui/spinner";
import { mensajeError } from "./lib/errores";
import { borrarSesion, useSesion } from "./lib/sesion";
import Agente from "./pages/Agente";
import Cotizaciones from "./pages/Cotizaciones";
import Feed from "./pages/Feed";
import InventarioPage from "./pages/Inventario";
import NegociacionPage from "./pages/Negociacion";
import PedidoPage from "./pages/Pedido";
import PlanPage from "./pages/Plan";
import Vision from "./pages/Vision";
import type { Negociacion, PedidoDemo, Plan } from "./types";

export interface EnCurso {
  desde: number;
  error?: string;
}

export default function App() {
  const navigate = useNavigate();
  const [demo, setDemo] = useState<PedidoDemo | null>(null);
  const [errorCarga, setErrorCarga] = useState<string | null>(null);
  const [reseteando, setReseteando] = useState(false);

  // Estado de la demo que sobrevive a la navegación (y a un F5, vía sessionStorage).
  const [cotizarEn, setCotizarEn] = useSesion<number | null>("cotizar_en", null);
  const [plan, setPlan] = useSesion<Plan | null>("plan", null);
  const [negociaciones, setNegociaciones] = useSesion<Record<string, Negociacion>>("negociaciones", {});
  const [negociando, setNegociando] = useState<Record<string, EnCurso>>({});

  const recargarPedido = useCallback(async () => {
    try {
      setDemo(await api.getPedidoDemo());
      setErrorCarga(null);
    } catch (e) {
      setErrorCarga(mensajeError(e));
    }
  }, []);

  useEffect(() => {
    recargarPedido();
  }, [recargarPedido]);

  const iniciarNegociacion = useCallback(
    async (proveedorId: string) => {
      if (!demo) return;
      setNegociando((n) => ({ ...n, [proveedorId]: { desde: Date.now() } }));
      try {
        const neg = await api.negociar(demo.pedido.id, proveedorId);
        setNegociaciones((n) => ({ ...n, [proveedorId]: neg }));
        setNegociando((n) => {
          const resto = { ...n };
          delete resto[proveedorId];
          return resto;
        });
        recargarPedido();
      } catch (e) {
        setNegociando((n) => ({
          ...n,
          [proveedorId]: { desde: n[proveedorId]?.desde ?? Date.now(), error: mensajeError(e) },
        }));
      }
    },
    [demo, recargarPedido, setNegociaciones],
  );

  /** Lo que la app guarda de la demo, en blanco (después de un POST /reset). */
  const limpiar = useCallback(async () => {
    borrarSesion();
    setCotizarEn(null);
    setPlan(null);
    setNegociaciones({});
    setNegociando({});
    await recargarPedido();
  }, [recargarPedido, setCotizarEn, setPlan, setNegociaciones]);

  /** Lo que hizo el agente, para que Plan y Negociación (las vistas de detalle) muestren lo mismo. */
  const sincronizar = useCallback(
    (nuevoPlan: Plan | null, negociacion: Negociacion | null) => {
      if (nuevoPlan) setPlan((p) => (JSON.stringify(p) === JSON.stringify(nuevoPlan) ? p : nuevoPlan));
      if (negociacion)
        setNegociaciones((n) =>
          JSON.stringify(n[negociacion.proveedor_id]) === JSON.stringify(negociacion)
            ? n
            : { ...n, [negociacion.proveedor_id]: negociacion },
        );
    },
    [setPlan, setNegociaciones],
  );

  const reset = async () => {
    if (!window.confirm("¿Reiniciar la demo? Se borran la compra del agente, las respuestas, el plan y las negociaciones."))
      return;
    setReseteando(true);
    try {
      await api.reset();
      await limpiar();
      navigate("/");
    } catch (e) {
      setErrorCarga(mensajeError(e));
    } finally {
      setReseteando(false);
    }
  };

  return (
    <Layout demo={demo} onReset={reset} reseteando={reseteando}>
      {errorCarga && (
        <div className="mb-6">
          <ErrorBanner mensaje={errorCarga} onReintentar={recargarPedido} />
        </div>
      )}
      {!demo ? (
        !errorCarga && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Cargando el pedido…
          </div>
        )
      ) : (
        <Routes>
          <Route path="/" element={<Agente onReseteado={limpiar} onSincronizar={sincronizar} />} />
          <Route path="/agente" element={<Navigate to="/" replace />} />
          <Route path="/inventario" element={<InventarioPage />} />
          <Route
            path="/pedido"
            element={
              <PedidoPage
                demo={demo}
                onCotizado={async () => {
                  setCotizarEn(Date.now());
                  await recargarPedido();
                }}
              />
            }
          />
          <Route path="/feed" element={<Feed demo={demo} cotizarEn={cotizarEn} recargarPedido={recargarPedido} />} />
          <Route path="/cotizaciones" element={<Cotizaciones demo={demo} />} />
          <Route
            path="/plan"
            element={
              <PlanPage
                demo={demo}
                plan={plan}
                onPlan={(p) => {
                  setPlan(p);
                  recargarPedido();
                }}
                iniciarNegociacion={iniciarNegociacion}
                negociando={negociando}
              />
            }
          />
          {["/negociacion", "/negociacion/:proveedorId"].map((ruta) => (
            <Route
              key={ruta}
              path={ruta}
              element={
                <NegociacionPage
                  demo={demo}
                  plan={plan}
                  negociaciones={negociaciones}
                  negociando={negociando}
                  iniciarNegociacion={iniciarNegociacion}
                  onAprobada={(neg) => {
                    setNegociaciones((n) => ({ ...n, [neg.proveedor_id]: neg }));
                    recargarPedido();
                  }}
                />
              }
            />
          ))}
          <Route path="/vision" element={<Vision />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
    </Layout>
  );
}
