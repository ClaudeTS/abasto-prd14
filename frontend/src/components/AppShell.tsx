// Marco de la app (PRD 1.4 §7 y mockups): menú lateral + contenido. En el teléfono el menú se apila arriba.
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  ClipboardListIcon,
  HomeIcon,
  LogOutIcon,
  PlayCircleIcon,
  Settings2Icon,
  SlidersHorizontalIcon,
  TruckIcon,
  type LucideIcon,
} from "lucide-react";
import { MODO } from "@/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

interface Item {
  to: string;
  label: string;
  icon: LucideIcon;
}

const PRINCIPAL: Item[] = [
  { to: "/inicio", label: "Inicio", icon: HomeIcon },
  { to: "/pedidos", label: "Pedidos", icon: ClipboardListIcon },
  { to: "/proveedores", label: "Proveedores", icon: TruckIcon },
];
const ADMIN: Item[] = [
  { to: "/reglas", label: "Reglas por producto", icon: SlidersHorizontalIcon },
  { to: "/configuracion", label: "Configuración", icon: Settings2Icon },
];
// El recorrido guiado del pitch (pantallas de la demo original), mientras convive con las nuevas.
const DEMO: Item[] = [{ to: "/pedido", label: "Demo guiada", icon: PlayCircleIcon }];

function Enlace({ item }: { item: Item }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) =>
        cn(
          "flex min-h-9 items-center gap-2.5 rounded-md px-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
          isActive && "bg-muted font-medium text-foreground",
        )
      }
    >
      <Icon className="size-4" aria-hidden />
      {item.label}
    </NavLink>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const { usuario, salir } = useAuth();
  return (
    <div className="flex min-h-svh flex-col bg-muted/30 md:flex-row">
      <aside className="flex shrink-0 flex-col gap-1 border-b bg-background p-3 md:sticky md:top-0 md:h-svh md:w-60 md:border-r md:border-b-0">
        <NavLink to="/inicio" className="flex items-center gap-2 px-2 pt-1 pb-4">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
            A
          </span>
          <span className="font-semibold tracking-tight">Abasto</span>
          {MODO === "mock" && (
            <Badge variant="outline" className="ml-auto">
              Mock
            </Badge>
          )}
        </NavLink>
        <nav aria-label="Navegación principal" className="flex flex-col gap-0.5">
          {PRINCIPAL.map((i) => (
            <Enlace key={i.to} item={i} />
          ))}
          <div className="px-2.5 pt-4 pb-1 text-xs text-muted-foreground">Administración</div>
          {ADMIN.map((i) => (
            <Enlace key={i.to} item={i} />
          ))}
          <div className="px-2.5 pt-4 pb-1 text-xs text-muted-foreground">Pitch</div>
          {DEMO.map((i) => (
            <Enlace key={i.to} item={i} />
          ))}
        </nav>
        {usuario && (
          <div className="mt-auto flex items-center gap-2.5 border-t px-2 pt-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
              {usuario.nombre.slice(0, 2).toUpperCase()}
            </span>
            <div className="min-w-0 flex-1 text-sm leading-tight">
              <div className="truncate font-medium">{usuario.nombre}</div>
              <div className="truncate text-xs text-muted-foreground">
                {usuario.rol === "administrador" ? "Administrador" : "Consulta"}
              </div>
            </div>
            <button
              type="button"
              onClick={salir}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Salir"
              title="Salir"
            >
              <LogOutIcon className="size-4" />
            </button>
          </div>
        )}
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">{children}</main>
    </div>
  );
}
