import { useState } from "react";
import { ExternalLinkIcon, FileTextIcon, MicIcon, PhoneIcon } from "lucide-react";
import { archivoUrl } from "@/api";
import { nombreProveedor } from "@/lib/proveedores";
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

  if (mensaje.canal === "llamada") return <VistaLlamada mensaje={mensaje} evidencias={evidencias} grande={grande} />;

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

interface Turno {
  abasto: boolean;
  texto: string;
}

/** "Abasto: …" / "<Proveedor>: …" por línea. Una línea sin ese prefijo continúa el turno anterior. */
export function turnosDeLlamada(texto: string, proveedorId: string): Turno[] {
  const nombre = nombreProveedor(proveedorId);
  const turnos: Turno[] = [];
  for (const linea of texto.split("\n")) {
    const abasto = linea.startsWith("Abasto:");
    const proveedor = linea.startsWith(`${nombre}:`);
    if (abasto || proveedor) {
      turnos.push({ abasto, texto: linea.slice((abasto ? "Abasto" : nombre).length + 1).trim() });
    } else if (turnos.length) {
      turnos[turnos.length - 1].texto += "\n" + linea;
    } else if (linea.trim()) {
      turnos.push({ abasto: false, texto: linea });
    }
  }
  return turnos;
}

/** Transcripción de una llamada del agente: quién habla en cada turno, con la evidencia resaltada. */
function VistaLlamada({ mensaje, evidencias, grande }: { mensaje: MensajeCrudo; evidencias: string[]; grande: boolean }) {
  const [abierto, setAbierto] = useState(grande);
  const turnos = turnosDeLlamada(mensaje.contenido_texto ?? "", mensaje.proveedor_id);
  const nombre = nombreProveedor(mensaje.proveedor_id);
  const delProveedor = turnos.filter((t) => !t.abasto).map((t) => t.texto).join(" ");
  return (
    <div className="space-y-2">
      <div className={cn("flex items-start gap-3", grande ? "w-full" : "w-72 sm:w-[28rem]")}>
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <PhoneIcon className="size-4" />
        </span>
        <div className="min-w-0 text-sm">
          <p className="font-medium">Abasto llamó a {nombre}</p>
          {!abierto && delProveedor && (
            <p className="line-clamp-2 text-muted-foreground italic">“{delProveedor}”</p>
          )}
        </div>
      </div>
      {!grande && (
        <Button variant="link" size="xs" className="h-auto px-0" onClick={() => setAbierto(!abierto)}>
          {abierto ? "Ocultar transcripción" : `Ver transcripción (${turnos.length} turnos)`}
        </Button>
      )}
      {abierto && (
        <div className="space-y-2 rounded-md bg-muted p-3 text-sm leading-relaxed">
          {turnos.map((t, k) => (
            <p key={k} className="whitespace-pre-wrap">
              <span className={cn("mr-1.5 font-medium", t.abasto ? "text-muted-foreground" : "text-foreground")}>
                {t.abasto ? "Abasto" : nombre}:
              </span>
              <TextoResaltado texto={t.texto} frases={evidencias} />
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
