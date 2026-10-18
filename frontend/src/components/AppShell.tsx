// Marco de la app (PRD 1.4 §7 y mockups): menú lateral + contenido. En el teléfono el menú se apila arriba.
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  ClipboardListIcon,
  HomeIcon,
  LogOutIcon,
  PackageIcon,
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
  { to: "/stock", label: "Depósito", icon: PackageIcon },
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
          "flex min-h-9 items-center gap-2.5 rounded-full border border-transparent px-3 text-sm text-gris-oscuro transition-colors hover:bg-negro-2 hover:text-white",
          isActive && "border-negro-3 bg-negro-2 font-medium text-white [&_svg]:text-celeste",
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
    <div className="flex min-h-svh flex-col bg-background md:flex-row">
      {/* Marco oscuro como las slides de sección de la plantilla; el contenido va sobre #F7F7F7. */}
      <div className="shrink-0 bg-negro md:w-60">
        <aside className="flex flex-col gap-1 bg-negro p-3 text-gris-oscuro md:sticky md:top-0 md:h-svh md:w-60">
          <NavLink to="/inicio" className="flex items-center gap-2 px-2 pt-1 pb-4">
            <span className="flex size-7 items-center justify-center rounded-md bg-celeste font-heading text-sm font-bold text-grafito">
              A
            </span>
            <span className="font-heading text-lg font-bold text-white">Abasto</span>
            {MODO === "mock" && (
              <Badge variant="outline" className="ml-auto border-negro-3 text-gris-oscuro">
                Mock
              </Badge>
            )}
          </NavLink>
          <nav aria-label="Navegación principal" className="flex flex-col gap-0.5">
            {PRINCIPAL.map((i) => (
              <Enlace key={i.to} item={i} />
            ))}
            <div className="px-3 pt-4 pb-1 text-[11px] font-bold tracking-[0.12em] text-gris-texto uppercase">Administración</div>
            {ADMIN.map((i) => (
              <Enlace key={i.to} item={i} />
            ))}
            <div className="px-3 pt-4 pb-1 text-[11px] font-bold tracking-[0.12em] text-gris-texto uppercase">Pitch</div>
            {DEMO.map((i) => (
              <Enlace key={i.to} item={i} />
            ))}
          </nav>
          {usuario && (
            <div className="mt-auto flex items-center gap-2.5 border-t border-negro-2 px-2 pt-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-celeste text-xs font-bold text-grafito">
                {usuario.nombre.slice(0, 2).toUpperCase()}
              </span>
              <div className="min-w-0 flex-1 text-sm leading-tight">
                <div className="truncate font-medium text-white">{usuario.nombre}</div>
                <div className="truncate text-xs text-gris-oscuro">
                  {usuario.rol === "administrador" ? "Administrador" : "Consulta"}
                </div>
              </div>
              <button
                type="button"
                onClick={salir}
                className="rounded-md p-1.5 text-gris-oscuro hover:bg-negro-2 hover:text-white"
                aria-label="Salir"
                title="Salir"
              >
                <LogOutIcon className="size-4" />
              </button>
            </div>
          )}
        </aside>
      </div>
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">{children}</main>
    </div>
  );
}
