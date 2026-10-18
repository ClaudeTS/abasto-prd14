import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Spinner } from "@/components/ui/spinner";

/** Sin sesión, al ingreso (RF-21). Vuelve a la página pedida después de ingresar. */
export default function RequiereSesion({ children }: { children: ReactNode }) {
  const { usuario, cargando } = useAuth();
  const ubicacion = useLocation();
  if (cargando)
    return (
      <div className="flex min-h-svh items-center justify-center gap-2 text-muted-foreground">
        <Spinner /> Cargando…
      </div>
    );
  if (!usuario) return <Navigate to="/login" replace state={{ desde: ubicacion.pathname }} />;
  return <>{children}</>;
}
