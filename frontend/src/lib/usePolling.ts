import { useEffect, useReducer, useRef } from "react";

/** Llama a `fn` cada `ms` mientras `activo` sea true, sin superponer llamadas. */
export function usePolling(fn: () => Promise<void>, ms: number, activo: boolean) {
  const ref = useRef(fn);
  ref.current = fn;

  useEffect(() => {
    if (!activo) return;
    let ocupado = false;
    const tick = async () => {
      if (ocupado) return;
      ocupado = true;
      try {
        await ref.current();
      } finally {
        ocupado = false;
      }
    };
    tick();
    const id = setInterval(tick, ms);
    return () => clearInterval(id);
  }, [ms, activo]);
}

/** Re-renderiza cada `ms` (para "hace 12 s" y avisos por tiempo). Devuelve Date.now(). */
export function useReloj(ms: number, activo = true): number {
  const [, tick] = useReducer((x: number) => x + 1, 0);
  useEffect(() => {
    if (!activo) return;
    const id = setInterval(tick, ms);
    return () => clearInterval(id);
  }, [ms, activo]);
  return Date.now();
}
