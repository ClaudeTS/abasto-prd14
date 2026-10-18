import type { ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { ChevronDownIcon, RotateCcwIcon } from "lucide-react";
import { MODO } from "@/api";
import { formatNumero } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import type { PedidoDemo } from "@/types";

// El agente es la portada. Las vistas paso a paso quedan como detalle de lo que hizo.
const PRINCIPALES = [
  { to: "/", label: "Agente" },
  { to: "/inventario", label: "Inventario" },
];

const DETALLE = [
  { to: "/feed", label: "Respuestas de los proveedores" },
  { to: "/cotizaciones", label: "Cotizaciones con evidencia" },
  { to: "/plan", label: "Plan de compra" },
  { to: "/negociacion", label: "Negociación" },
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
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const enDetalle = ["/pedido", ...DETALLE.map((d) => d.to)].some((r) => pathname.startsWith(r));
  const enlace = ({ isActive }: { isActive: boolean }) =>
    cn(
      "whitespace-nowrap transition-colors hover:text-foreground",
      isActive ? "font-medium text-foreground" : "text-muted-foreground",
    );
  return (
    <div className="min-h-svh bg-background">
      <header className="sticky top-0 z-40 w-full border-b bg-background/80 backdrop-blur supports-backdrop-filter:bg-background/60">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
              A
            </span>
            <span className="font-semibold tracking-tight">Abasto</span>
          </NavLink>

          <nav className="flex min-w-0 items-center gap-5 text-sm">
            {PRINCIPALES.map((p) => (
              <NavLink key={p.to} to={p.to} end={p.to === "/"} className={enlace}>
                {p.label}
              </NavLink>
            ))}
            <DropdownMenu>
              <DropdownMenuTrigger
                className={cn(
                  "flex items-center gap-1 whitespace-nowrap outline-none transition-colors hover:text-foreground",
                  enDetalle ? "font-medium text-foreground" : "text-muted-foreground",
                )}
              >
                Detalle <ChevronDownIcon className="size-3.5" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuLabel>Lo que hizo el agente, paso a paso</DropdownMenuLabel>
                {DETALLE.map((d) => (
                  <DropdownMenuItem key={d.to} onSelect={() => navigate(d.to)}>
                    {d.label}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => navigate("/pedido")}>Hacer la compra a mano</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <NavLink to="/vision" className={enlace}>
              Visión
            </NavLink>
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
      <main className="mx-auto max-w-7xl px-4 py-10 sm:px-6">{children}</main>
    </div>
  );
}
