// Depósito: bajar el stock de a 1. Al llegar al mínimo, el agente arranca solo la compra y se ve en Nuevo pedido.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { RotateCcwIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { borrarSesion } from "@/lib/sesion";
import { Encabezado, ErrorBanner } from "@/components/comunes";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import StockPanel from "@/features/agente/Stock";

export default function Stock() {
  const navigate = useNavigate();
  const [version, setVersion] = useState(0); // remonta el panel para releer el inventario tras el reinicio
  const [reiniciando, setReiniciando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reiniciar = async () => {
    if (!window.confirm("Reinicio la demo: vuelve el stock de siempre y se borran las compras del agente. ¿Sigo?")) return;
    setReiniciando(true);
    setError(null);
    try {
      await api.reset();
      borrarSesion();
      setVersion((v) => v + 1);
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setReiniciando(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <Encabezado
        titulo="Depósito"
        bajada="Registrá las salidas del depósito. Cuando un producto llega a su stock mínimo, el agente arranca la compra solo."
      >
        <Button variant="outline" onClick={reiniciar} disabled={reiniciando}>
          {reiniciando ? <Spinner /> : <RotateCcwIcon />} Reiniciar demo
        </Button>
      </Encabezado>
      <div className="space-y-6">
        {error && <ErrorBanner mensaje={error} />}
        <StockPanel key={version} onArranco={() => navigate("/pedidos/nuevo")} />
      </div>
    </div>
  );
}
