// Dictado del navegador (Web Speech API, docs/AGENTE.md §5). Sin soporte (Firefox): `disponible` es false
// y la pantalla muestra solo el textarea.
import { useEffect, useRef, useState } from "react";

type Reconocedor = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

function constructor(): (new () => Reconocedor) | null {
  if (typeof window === "undefined") return null;
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const ERRORES: Record<string, string> = {
  "not-allowed": "El navegador no dio permiso para usar el micrófono.",
  "service-not-allowed": "El navegador no dio permiso para usar el micrófono.",
  "no-speech": "No escuché nada. Probá de nuevo, más cerca del micrófono.",
  "audio-capture": "No encontré un micrófono.",
  network: "El dictado necesita conexión a internet.",
};

export function useDictado(onTexto: (texto: string) => void) {
  const SR = constructor();
  const [escuchando, setEscuchando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = useRef<Reconocedor | null>(null);
  const cb = useRef(onTexto);
  cb.current = onTexto;

  useEffect(() => () => rec.current?.abort(), []);

  const empezar = () => {
    if (!SR || escuchando) return;
    setError(null);
    const r = new SR();
    r.lang = navigator.language?.toLowerCase().startsWith("es-ar") ? "es-AR" : "es-UY";
    r.interimResults = true; // el texto aparece mientras habla
    r.continuous = false; // corta solo al terminar la frase
    r.onresult = (e: any) =>
      cb.current(
        Array.from(e.results as ArrayLike<any>)
          .map((res: any) => res[0].transcript)
          .join(" ")
          .replace(/\s+/g, " ")
          .trim(),
      );
    r.onerror = (e: any) => {
      if (e?.error !== "aborted") setError(ERRORES[e?.error] ?? "No pude usar el dictado. Escribilo abajo.");
    };
    r.onend = () => setEscuchando(false);
    rec.current = r;
    try {
      r.start();
      setEscuchando(true);
    } catch {
      setError("No pude usar el dictado. Escribilo abajo.");
    }
  };

  const parar = () => rec.current?.stop();

  return { disponible: !!SR, escuchando, error, empezar, parar };
}
