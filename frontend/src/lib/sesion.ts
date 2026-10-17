import { useCallback, useState } from "react";

// sessionStorage para que un F5 en medio de la demo no pierda el plan ni la negociación.
// Todo con try/catch: si el navegador lo bloquea, la UI sigue andando sin persistir.

const PREFIJO = "abasto_";

export function leerSesion<T>(clave: string, inicial: T): T {
  try {
    const valor = sessionStorage.getItem(PREFIJO + clave);
    return valor ? (JSON.parse(valor) as T) : inicial;
  } catch {
    return inicial;
  }
}

export function guardarSesion(clave: string, valor: unknown): void {
  try {
    if (valor === null || valor === undefined) sessionStorage.removeItem(PREFIJO + clave);
    else sessionStorage.setItem(PREFIJO + clave, JSON.stringify(valor));
  } catch {
    /* sin persistencia */
  }
}

export function borrarSesion(): void {
  try {
    Object.keys(sessionStorage)
      .filter((k) => k.startsWith(PREFIJO))
      .forEach((k) => sessionStorage.removeItem(k));
  } catch {
    /* nada que borrar */
  }
}

export function useSesion<T>(clave: string, inicial: T) {
  const [valor, setValor] = useState<T>(() => leerSesion(clave, inicial));
  const actualizar = useCallback(
    (nuevo: T | ((previo: T) => T)) => {
      setValor((previo) => {
        const siguiente = typeof nuevo === "function" ? (nuevo as (p: T) => T)(previo) : nuevo;
        guardarSesion(clave, siguiente);
        return siguiente;
      });
    },
    [clave],
  );
  return [valor, actualizar] as const;
}
