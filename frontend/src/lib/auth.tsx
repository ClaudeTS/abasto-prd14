// Sesión del usuario (RF-21). INTERFAZ ESTABLE: el resto de la app usa solo useAuth().
// Con backend: token en localStorage (clave CLAVE_TOKEN de src/api.ts, que lo adjunta en cada pedido) y
// GET /auth/yo al cargar. En modo mock no hay backend: entra Lucía, administradora, como antes.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { CLAVE_TOKEN, MODO } from "@/api";
import * as api from "@/features/reglas/api";

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

const MOCK: Auth = {
  usuario: LUCIA,
  esAdmin: true,
  cargando: false,
  ingresar: async () => {},
  salir: () => {},
};

const Ctx = createContext<Auth>(MOCK);

function leerToken(): string | null {
  try {
    return localStorage.getItem(CLAVE_TOKEN);
  } catch {
    return null;
  }
}

function guardarToken(token: string | null) {
  try {
    if (token) localStorage.setItem(CLAVE_TOKEN, token);
    else localStorage.removeItem(CLAVE_TOKEN);
  } catch {
    /* sin storage: la sesión dura lo que la pestaña */
  }
}

/** Errores de conexión: el token puede seguir siendo bueno (el backend estaba dormido). */
const esDeConexion = (e: unknown) => e instanceof Error && /No se pudo conectar|no responde/.test(e.message);

function AuthReal({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(() => leerToken() !== null);

  useEffect(() => {
    if (!leerToken()) return;
    let vivo = true;
    api
      .yo()
      .then((u) => vivo && setUsuario(u))
      .catch((e) => {
        if (!esDeConexion(e)) guardarToken(null); // vencido, revocado o trucho
      })
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, []);

  const ingresar = useCallback(async (u: string, contrasena: string) => {
    const sesion = await api.login(u, contrasena);
    guardarToken(sesion.token);
    setUsuario(sesion.usuario);
  }, []);

  const salir = useCallback(() => {
    if (leerToken()) api.logout().catch(() => {}); // el token se borra igual
    guardarToken(null);
    setUsuario(null);
  }, []);

  const valor = useMemo<Auth>(
    () => ({ usuario, esAdmin: usuario?.rol === "administrador", cargando, ingresar, salir }),
    [usuario, cargando, ingresar, salir],
  );
  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  if (MODO === "mock") return <Ctx.Provider value={MOCK}>{children}</Ctx.Provider>;
  return <AuthReal>{children}</AuthReal>;
}

export function useAuth(): Auth {
  return useContext(Ctx);
}
