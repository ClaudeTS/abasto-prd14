// Llamadas del bloque 3 (reglas, configuración e ingreso). Usa http() de src/api.ts, que adjunta el token.
import { http } from "@/api";
import type { ConfigLlamadas } from "@/types";
import type { Usuario } from "@/lib/auth";
import type {
  CambioConfiguracion,
  CambioRegla,
  Configuracion,
  PropuestaReglas,
  UsuarioListado,
  VistaPrevia,
  VistaReglas,
} from "./types";

const id = (productoId: string) => encodeURIComponent(productoId);

// ─────────── Reglas por producto (RF-13, RF-14, RF-15) ───────────
export const listarReglas = () => http<VistaReglas[]>("GET", "/reglas");
export const verReglas = (productoId: string) => http<VistaReglas>("GET", `/reglas/${id(productoId)}`);
export const cambiarReglas = (productoId: string, cambio: PropuestaReglas, motivo: string) =>
  http<VistaReglas>("PATCH", `/reglas/${id(productoId)}`, { ...cambio, motivo });
export const vistaPrevia = (productoId: string, propuesta: PropuestaReglas) =>
  http<VistaPrevia>("POST", `/reglas/${id(productoId)}/vista-previa`, propuesta);
export const historialReglas = (productoId: string) =>
  http<CambioRegla[]>("GET", `/reglas/${id(productoId)}/historial`);
export const revertirCambio = (productoId: string, cambioId: string) =>
  http<VistaReglas>("POST", `/reglas/${id(productoId)}/historial/${encodeURIComponent(cambioId)}/revertir`, {});

// ─────────── Configuración (RF-20) ───────────
export const verConfiguracion = () => http<Configuracion>("GET", "/configuracion");
export const cambiarConfiguracion = (cambio: CambioConfiguracion) =>
  http<Configuracion>("PATCH", "/configuracion", cambio);
export const historialConfiguracion = () => http<CambioRegla[]>("GET", "/configuracion/historial");
export const configLlamadas = () => http<ConfigLlamadas>("GET", "/llamadas/config");

// ─────────── Ingreso (RF-21) ───────────
export const login = (usuario: string, contrasena: string) =>
  http<{ token: string; usuario: Usuario }>("POST", "/auth/login", { usuario, contrasena });
export const yo = () => http<Usuario>("GET", "/auth/yo");
export const logout = () => http<void>("POST", "/auth/logout");
export const registro = (datos: Record<string, string>) => http<void>("POST", "/auth/registro", datos);
export const listarUsuarios = () => http<UsuarioListado[]>("GET", "/auth/usuarios");
