import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { RotateCcwIcon } from "lucide-react";
import { MODO } from "@/api";
import { formatNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import type { PedidoDemo } from "@/types";

const PASOS = [
  { to: "/pedido", label: "Pedido" },
  { to: "/feed", label: "Respuestas" },
  { to: "/cotizaciones", label: "Cotizaciones" },
  { to: "/plan", label: "Plan" },
  { to: "/negociacion", label: "Negociación" },
  { to: "/vision", label: "Visión" },
];

export default function Layout({
  demo,
  onReset,
  reseteando,
  children,
}: {
  demo: PedidoDemo | null;
  onReset: () => void;
  reseteando: boolean;
  children: ReactNode;
}) {
  return (
    // Dentro del AppShell (PRD 1.4): la barra de pasos del recorrido guiado del pitch.
    <div className="mx-auto max-w-7xl">
      <header className="mb-8 rounded-xl border bg-background">
        <div className="flex min-h-12 flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">

          <nav className="flex min-w-0 items-center gap-5 overflow-x-auto text-sm">
            {PASOS.map((p, i) => (
              <NavLink
                key={p.to}
                to={p.to}
                className={({ isActive }) =>
                  cn(
                    "whitespace-nowrap transition-colors hover:text-foreground",
                    isActive ? "font-medium text-foreground" : "text-muted-foreground",
                  )
                }
              >
                {i < 5 && <span className="mr-1 text-muted-foreground/60 tabular-nums">{i + 1}.</span>}
                {p.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {demo && (
              <div className="hidden items-center gap-3 text-sm whitespace-nowrap xl:flex">
                <span className="font-medium">{demo.pedido.negocio}</span>
                <Separator orientation="vertical" className="h-4" />
                <span className="text-muted-foreground tabular-nums" title="Tipo de cambio usado para convertir USD → UYU">
                  USD 1 = $ {formatNumero(demo.config.tipo_cambio_usd, 2)}
                </span>
              </div>
            )}
            {MODO === "mock" && (
              <Badge variant="outline" title="La UI corre con data/*.json, sin backend. Cambiar con ?modo=backend">
                Mock
              </Badge>
            )}
            <Button variant="ghost" size="sm" onClick={onReset} disabled={reseteando} title="Vuelve la demo al estado inicial">
              <RotateCcwIcon />
              <span className="hidden sm:inline">{reseteando ? "Reiniciando…" : "Reiniciar"}</span>
            </Button>
          </div>
        </div>
      </header>
      <div>{children}</div>
    </div>
  );
}
