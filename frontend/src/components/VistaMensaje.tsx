import { useState } from "react";
import { ExternalLinkIcon, FileTextIcon, MicIcon } from "lucide-react";
import { archivoUrl } from "@/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { TextoResaltado } from "@/components/comunes";
import type { MensajeCrudo } from "@/types";

/** Muestra el mensaje crudo tal como llegó: texto, audio (transcripto), PDF o foto. */
export default function VistaMensaje({
  mensaje,
  evidencias = [],
  grande = false,
}: {
  mensaje: MensajeCrudo;
  evidencias?: string[];
  grande?: boolean;
}) {
  const texto = mensaje.contenido_texto ?? "";

  if (mensaje.canal === "whatsapp_audio") return <Audio mensaje={mensaje} evidencias={evidencias} grande={grande} />;

  if (mensaje.canal === "pdf") {
    const url = mensaje.archivo ? archivoUrl(mensaje.archivo) : "";
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2">
          <FileTextIcon className="size-4 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{nombreArchivo(mensaje)}</span>
          {url && (
            <Button asChild variant="link" size="xs" className="ml-auto">
              <a href={url} target="_blank" rel="noreferrer">
                Abrir <ExternalLinkIcon />
              </a>
            </Button>
          )}
        </div>
        {url ? (
          // Sin sandbox: Chrome no abre su visor de PDF en iframes con sandbox. El archivo es de nuestro backend.
          <iframe
            title={`PDF de ${mensaje.proveedor_id}`}
            src={url.startsWith("data:") ? url : `${url}#toolbar=0&navpanes=0&view=FitH`}
            className={cn("max-w-full rounded-md border bg-white", grande ? "h-[420px] w-full" : "h-64 w-[32rem]")}
          />
        ) : (
          <p className="text-sm whitespace-pre-wrap">{texto}</p>
        )}
        {grande && texto && (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">Texto extraído del PDF</summary>
            <p className="mt-2 rounded-md bg-muted p-3 whitespace-pre-wrap">
              <TextoResaltado texto={texto} frases={evidencias} />
            </p>
          </details>
        )}
      </div>
    );
  }

  if (mensaje.canal === "foto") {
    const url = mensaje.archivo ? archivoUrl(mensaje.archivo) : "";
    return url ? (
      <img
        src={url}
        alt="Foto de un presupuesto escrito a mano"
        className={cn("rounded-md border shadow-xs", grande ? "w-full" : "w-72")}
      />
    ) : (
      <p className="text-sm whitespace-pre-wrap italic">{texto || "(foto sin archivo)"}</p>
    );
  }

  return (
    <p className={cn("leading-relaxed whitespace-pre-wrap", grande ? "text-base" : "text-sm")}>
      <TextoResaltado texto={texto} frases={evidencias} />
    </p>
  );
}

function nombreArchivo(m: MensajeCrudo): string {
  if (m.archivo && !m.archivo.startsWith("mock:")) return m.archivo.split(/[\\/]/).pop() ?? m.archivo;
  return `cotizacion-${m.proveedor_id}.pdf`;
}

function Audio({ mensaje, evidencias, grande }: { mensaje: MensajeCrudo; evidencias: string[]; grande: boolean }) {
  const [abierto, setAbierto] = useState(grande);
  const texto = mensaje.contenido_texto ?? "";
  const url = mensaje.archivo ? archivoUrl(mensaje.archivo) : "";
  const segundos = Math.max(8, Math.round(texto.split(/\s+/).length / 2.4));
  return (
    <div className="space-y-2">
      {url ? (
        <audio controls src={url} className="w-72" />
      ) : (
        // Sin archivo de audio (solo transcripción): nada de botón de play; el clic abre la transcripción.
        <button
          type="button"
          onClick={() => setAbierto(!abierto)}
          title="Audio transcripto por Abasto"
          className="flex w-72 items-center gap-3 rounded-md text-left"
        >
          <span className="flex size-8 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <MicIcon className="size-4" />
          </span>
          <span className="flex h-7 flex-1 items-center gap-[3px]" aria-hidden>
            {Array.from({ length: 28 }, (_, i) => (
              <span
                key={i}
                className="w-[3px] rounded-full bg-muted-foreground/40"
                style={{ height: `${25 + Math.abs(Math.sin(i * 1.7)) * 75}%` }}
              />
            ))}
          </span>
          <span className="text-xs text-muted-foreground tabular-nums">0:{String(segundos).padStart(2, "0")}</span>
        </button>
      )}
      <Button variant="link" size="xs" className="h-auto px-0" onClick={() => setAbierto(!abierto)}>
        {abierto ? "Ocultar transcripción" : "Ver transcripción"}
      </Button>
      {abierto && (
        <p className="rounded-md bg-muted p-3 text-sm leading-relaxed whitespace-pre-wrap italic">
          <TextoResaltado texto={texto} frases={evidencias} />
        </p>
      )}
    </div>
  );
}
