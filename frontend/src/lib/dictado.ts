import { useCallback, useEffect, useRef, useState } from "react";

// Dictado del navegador (Web Speech API, docs/AGENTE.md §5). Chrome y Edge, en https o localhost.
// Sin soporte (Firefox) la pantalla muestra solo el texto.

interface ResultadoDictado {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}

interface Reconocedor {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: ResultadoDictado) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

function constructor(): (new () => Reconocedor) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  return ((w.SpeechRecognition ?? w.webkitSpeechRecognition) as (new () => Reconocedor) | undefined) ?? null;
}

/** El texto aparece mientras habla (`onTexto` con lo dictado hasta ahora) y corta solo al terminar la frase. */
export function useDictado(onTexto: (texto: string) => void) {
  const [escuchando, setEscuchando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Reconocedor | null>(null);
  const alTexto = useRef(onTexto);
  alTexto.current = onTexto;
  const soportado = constructor() !== null;

  const empezar = useCallback(() => {
    const SR = constructor();
    if (!SR) return;
    const r = new SR();
    r.lang = "es-UY";
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) =>
      alTexto.current(
        Array.from(e.results)
          .map((x) => x[0].transcript)
          .join(" ")
          .trim(),
      );
    r.onend = () => setEscuchando(false);
    r.onerror = (e) => {
      setError(
        e.error === "not-allowed"
          ? "El navegador no dio permiso para usar el micrófono."
          : e.error === "no-speech"
            ? "No escuché nada. Probá de nuevo o escribilo."
            : "No pude escuchar. Probá de nuevo o escribilo.",
      );
      setEscuchando(false);
    };
    rec.current = r;
    setError(null);
    setEscuchando(true);
    r.start();
  }, []);

  const parar = useCallback(() => rec.current?.stop(), []);

  useEffect(() => () => rec.current?.abort(), []);

  return { soportado, escuchando, error, empezar, parar };
}
