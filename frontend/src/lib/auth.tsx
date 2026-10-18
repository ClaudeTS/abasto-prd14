// Sesión del usuario (RF-21). INTERFAZ ESTABLE: el resto de la app usa solo useAuth().
// Hoy es un stub (siempre Lucía, administradora); el bloque de auth lo reemplaza por el real sin cambiar
// la forma de Usuario ni de useAuth().
import { createContext, useContext, type ReactNode } from "react";

export type Rol = "administrador" | "consulta";
export type ClienteInterno = "ventas" | "personal";

export interface Usuario {
  id: string;
  nombre: string;
  email: string;
  rol: Rol;
  cliente_interno: ClienteInterno;
}

export interface Auth {
  usuario: Usuario | null;
  esAdmin: boolean;
  cargando: boolean;
  ingresar: (usuario: string, contrasena: string) => Promise<void>;
  salir: () => void;
}

const LUCIA: Usuario = {
  id: "u_lucia",
  nombre: "Lucía",
  email: "lucia@tecnova.com.uy",
  rol: "administrador",
  cliente_interno: "personal",
};

const STUB: Auth = {
  usuario: LUCIA,
  esAdmin: true,
  cargando: false,
  ingresar: async () => {},
  salir: () => {},
};

const Ctx = createContext<Auth>(STUB);

export function AuthProvider({ children }: { children: ReactNode }) {
  return <Ctx.Provider value={STUB}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  return useContext(Ctx);
}
