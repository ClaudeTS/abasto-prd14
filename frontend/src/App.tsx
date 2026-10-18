import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import * as api from "./api";
import AppShell from "./components/AppShell";
import Layout from "./components/Layout";
import RequiereSesion from "./components/RequiereSesion";
import { ErrorBanner } from "./components/comunes";
import { Spinner } from "./components/ui/spinner";
import { mensajeError } from "./lib/errores";
import { borrarSesion, useSesion } from "./lib/sesion";
import Cotizaciones from "./pages/Cotizaciones";
import Feed from "./pages/Feed";
import NegociacionPage from "./pages/Negociacion";
import PedidoPage from "./pages/Pedido";
import PlanPage from "./pages/Plan";
import Vision from "./pages/Vision";
import Configuracion from "./pages/Configuracion";
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";
import NuevoPedido from "./pages/NuevoPedido";
import PedidoDetalle from "./pages/PedidoDetalle";
import Pedidos from "./pages/Pedidos";
import Proveedores from "./pages/Proveedores";
import Registro from "./pages/Registro";
import Reglas from "./pages/Reglas";
import Stock from "./pages/Stock";
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

  const reset = async () => {
    if (!window.confirm("¿Reiniciar la demo? Se borran respuestas, plan y negociaciones.")) return;
    setReseteando(true);
    try {
      await api.reset();
      borrarSesion();
      setCotizarEn(null);
      setPlan(null);
      setNegociaciones({});
      setNegociando({});
      await recargarPedido();
      navigate("/pedido");
    } catch (e) {
      setErrorCarga(mensajeError(e));
    } finally {
      setReseteando(false);
    }
  };

  // Recorrido guiado del pitch: necesita el pedido demo cargado y muestra la barra de pasos.
  const enDemo = (contenido: (d: PedidoDemo) => ReactNode) => (
    <Layout demo={demo} onReset={reset} reseteando={reseteando}>
      {errorCarga && (
        <div className="mb-6">
          <ErrorBanner mensaje={errorCarga} onReintentar={recargarPedido} />
        </div>
      )}
      {!demo
        ? !errorCarga && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner /> Cargando el pedido…
            </div>
          )
        : contenido(demo)}
    </Layout>
  );

  return (
    <Routes>
      {/* Fuera del marco: ingreso y registro (RF-21). */}
      <Route path="/login" element={<Login />} />
      <Route path="/registro" element={<Registro />} />
      <Route
        path="*"
        element={
          <RequiereSesion>
            <AppShell>
              <Routes>
                <Route path="/" element={<Navigate to="/inicio" replace />} />
                {/* PRD 1.4 — una página por área (docs/PRD-1.4.md §7). */}
                <Route path="/inicio" element={<Inicio />} />
                <Route path="/pedidos" element={<Pedidos />} />
                <Route path="/pedidos/nuevo" element={<NuevoPedido />} />
                <Route path="/stock" element={<Stock />} />
                <Route path="/pedidos/:pedidoId" element={<PedidoDetalle />} />
                <Route path="/proveedores" element={<Proveedores />} />
                <Route path="/proveedores/:proveedorId" element={<Proveedores />} />
                <Route path="/reglas" element={<Reglas />} />
                <Route path="/reglas/:productoId" element={<Reglas />} />
                <Route path="/configuracion" element={<Configuracion />} />

                {/* Recorrido guiado del pitch (pantallas originales). */}
                <Route
                  path="/pedido"
                  element={enDemo((d) => (
                    <PedidoPage
                      demo={d}
                      onCotizado={async () => {
                        setCotizarEn(Date.now());
                        await recargarPedido();
                      }}
                    />
                  ))}
                />
                <Route path="/feed" element={enDemo((d) => <Feed demo={d} cotizarEn={cotizarEn} recargarPedido={recargarPedido} />)} />
                <Route path="/cotizaciones" element={enDemo((d) => <Cotizaciones demo={d} />)} />
                <Route
                  path="/plan"
                  element={enDemo((d) => (
                    <PlanPage
                      demo={d}
                      plan={plan}
                      onPlan={(p) => {
                        setPlan(p);
                        recargarPedido();
                      }}
                      iniciarNegociacion={iniciarNegociacion}
                      negociando={negociando}
                    />
                  ))}
                />
                {["/negociacion", "/negociacion/:proveedorId"].map((ruta) => (
                  <Route
                    key={ruta}
                    path={ruta}
                    element={enDemo((d) => (
                      <NegociacionPage
                        demo={d}
                        plan={plan}
                        negociaciones={negociaciones}
                        negociando={negociando}
                        iniciarNegociacion={iniciarNegociacion}
                        onAprobada={(neg) => {
                          setNegociaciones((n) => ({ ...n, [neg.proveedor_id]: neg }));
                          recargarPedido();
                        }}
                      />
                    ))}
                  />
                ))}
                <Route path="/vision" element={enDemo(() => <Vision />)} />
                <Route path="*" element={<Navigate to="/inicio" replace />} />
              </Routes>
            </AppShell>
          </RequiereSesion>
        }
      />
    </Routes>
  );
}
