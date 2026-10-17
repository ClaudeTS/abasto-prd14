import { CameraIcon, FileTextIcon, MessageSquareIcon, MicIcon, type LucideIcon } from "lucide-react";
import sim from "../../../data/proveedores_sim.json";
import type { Canal, Proveedor } from "../types";

// Datos públicos de los proveedores (nombre, rubro, canal, confiabilidad). Son datos seedeados
// y estáticos: se leen de data/proveedores_sim.json (solo el bloque "publico").
export const PROVEEDORES: Proveedor[] = sim.proveedores.map((p) => p.publico as Proveedor);

const POR_ID: Record<string, Proveedor> = Object.fromEntries(PROVEEDORES.map((p) => [p.id, p]));

export function proveedor(id: string): Proveedor {
  return (
    POR_ID[id] ?? { id, nombre: id, rubro: "", canal_preferido: "whatsapp_texto", confiabilidad: 0 }
  );
}

export function nombreProveedor(id: string): string {
  return proveedor(id).nombre;
}

export function iniciales(nombre: string): string {
  return nombre
    .replace(/S\.A\.?/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

export const CANALES: Record<Canal, { icono: LucideIcon; etiqueta: string }> = {
  whatsapp_texto: { icono: MessageSquareIcon, etiqueta: "WhatsApp" },
  whatsapp_audio: { icono: MicIcon, etiqueta: "Audio de WhatsApp" },
  pdf: { icono: FileTextIcon, etiqueta: "PDF" },
  foto: { icono: CameraIcon, etiqueta: "Foto" },
};
