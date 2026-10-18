// Llamadas del bloque 4 al backend (usa http() de src/api.ts, que adjunta la sesión).
import { http } from "@/api";
import type { Alta, AltaAgente, AltaManual, EdicionPerfil, Evaluacion, Listado, Perfil, Ranking } from "./types";

const id = encodeURIComponent;

export const listarProveedores = () => http<Listado>("GET", "/proveedores/listado");

export const obtenerPerfil = (proveedorId: string) => http<Perfil>("GET", `/proveedores/${id(proveedorId)}/perfil`);

export const editarPerfil = (proveedorId: string, cambios: EdicionPerfil) =>
  http<Perfil>("PATCH", `/proveedores/${id(proveedorId)}/perfil`, cambios);

export const altaManual = (datos: AltaManual) => http<Alta>("POST", "/proveedores/alta", datos);

export const altaPorAgente = (datos: AltaAgente) => http<Alta>("POST", "/proveedores/alta-agente", datos);

export const aprobarAlta = (proveedorId: string, usuario?: string, aprobar = true) =>
  http<Alta>("POST", `/proveedores/${id(proveedorId)}/aprobar-alta`, { usuario, aprobar });

export const obtenerRanking = (pedidoId: string, productoId?: string) =>
  http<Ranking>(
    "GET",
    `/pedidos/${id(pedidoId)}/ranking${productoId ? `?producto_id=${id(productoId)}` : ""}`,
  );

export const obtenerEvaluacion = (negociacionId: string) =>
  http<Evaluacion>("GET", `/negociaciones/${id(negociacionId)}/evaluacion`);
