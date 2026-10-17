export class ApiError extends Error {
  detalle?: unknown;

  constructor(mensaje: string, detalle?: unknown) {
    super(mensaje);
    this.name = "ApiError";
    this.detalle = detalle;
  }
}

export function mensajeError(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}
