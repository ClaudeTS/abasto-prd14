// Cómo entra el pedido (RF-01): nota de voz dictada o el texto de un email, más el cliente interno (RF-05).
import { useState } from "react";
import { MailIcon, MicIcon, RepeatIcon, SendIcon, SparklesIcon, SquareIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { mensajeError } from "@/lib/errores";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import * as agenteApi from "./api";
import type { ClienteInterno } from "./types";
import { useDictado } from "./useDictado";

export const CLIENTES: { id: ClienteInterno; etiqueta: string; bajada: string }[] = [
  { id: "personal", etiqueta: "Personal", bajada: "RR. HH., oficina, ingresos" },
  { id: "ventas", etiqueta: "Ventas", bajada: "Equipo comercial y locales" },
];

export function nombreCliente(c: ClienteInterno | undefined): string {
  return c === "ventas" ? "Ventas" : "Personal";
}

export default function Entrada({
  texto,
  setTexto,
  cliente,
  setCliente,
  enviando,
  onMandar,
}: {
  texto: string;
  setTexto: (t: string) => void;
  cliente: ClienteInterno;
  setCliente: (c: ClienteInterno) => void;
  enviando: "texto" | "reponer" | null;
  onMandar: (texto: string) => void;
}) {
  const dictado = useDictado(setTexto);
  const [cargandoEjemplo, setCargandoEjemplo] = useState(false);
  const [errorEjemplo, setErrorEjemplo] = useState<string | null>(null);
  const ocupado = enviando !== null;

  const usarEjemplo = async () => {
    setCargandoEjemplo(true);
    setErrorEjemplo(null);
    try {
      setTexto(await agenteApi.ejemplo());
    } catch (e) {
      setErrorEjemplo(mensajeError(e));
    } finally {
      setCargandoEjemplo(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">¿Qué hay que comprar?</CardTitle>
        <CardDescription>
          Dictá la nota de voz o pegá el email del cliente interno. El agente entiende qué se pidió, lo cruza con el
          inventario y te pregunta lo que falte.
        </CardDescription>
      </CardHeader>
      <CardContent className="gap-5">
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-medium">¿Para quién es?</legend>
          <div role="radiogroup" aria-label="Cliente interno" className="grid gap-2 sm:grid-cols-2">
            {CLIENTES.map((c) => {
              const activo = c.id === cliente;
              return (
                <button
                  key={c.id}
                  type="button"
                  role="radio"
                  aria-checked={activo}
                  onClick={() => setCliente(c.id)}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    activo ? "border-foreground bg-muted/60" : "hover:bg-muted/40",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "flex size-4 shrink-0 items-center justify-center rounded-full border",
                      activo ? "border-foreground" : "border-muted-foreground/40",
                    )}
                  >
                    {activo && <span className="size-2 rounded-full bg-foreground" />}
                  </span>
                  <span className="leading-tight">
                    <span className="block text-sm font-medium">{c.etiqueta}</span>
                    <span className="block text-xs text-muted-foreground">{c.bajada}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
          {dictado.disponible && (
            <div className="flex flex-col items-center gap-2 sm:w-32 sm:shrink-0">
              <button
                type="button"
                onClick={dictado.escuchando ? dictado.parar : dictado.empezar}
                disabled={ocupado}
                aria-pressed={dictado.escuchando}
                aria-label={dictado.escuchando ? "Dejar de escuchar" : "Dictar el pedido"}
                className={cn(
                  "relative flex size-20 items-center justify-center rounded-full transition-colors outline-none focus-visible:ring-4 focus-visible:ring-ring/50 disabled:opacity-50",
                  dictado.escuchando
                    ? "bg-red-600 text-white"
                    : "bg-primary text-primary-foreground hover:bg-primary/85",
                )}
              >
                {dictado.escuchando && (
                  <span className="absolute inset-0 animate-ping rounded-full bg-red-500/40" aria-hidden />
                )}
                {dictado.escuchando ? <SquareIcon className="relative size-6" /> : <MicIcon className="size-8" />}
              </button>
              <span className="text-center text-xs text-muted-foreground" aria-live="polite">
                {dictado.escuchando ? "Te escucho… tocá para cortar" : "Tocá y hablá"}
              </span>
            </div>
          )}

          <div className="min-w-0 flex-1 space-y-2">
            <label htmlFor="pedido-texto" className="flex items-center gap-1.5 text-sm font-medium">
              {dictado.disponible ? (
                <>
                  Lo que dijiste <span className="font-normal text-muted-foreground">(podés corregirlo)</span>
                </>
              ) : (
                <>
                  <MailIcon className="size-4 text-muted-foreground" /> El pedido, como te llegó
                </>
              )}
            </label>
            <Textarea
              id="pedido-texto"
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="Ej.: «Abasto, armá la compra del mes. Entran diez personas nuevas el 28…»"
              className="min-h-28 text-base"
              disabled={ocupado}
            />
            {!dictado.disponible && (
              <p className="text-xs text-muted-foreground">
                Este navegador no tiene dictado: escribilo o pegá el email. Para hablarle, abrilo en Chrome o Edge.
              </p>
            )}
            {dictado.error && <p className="text-xs text-destructive">{dictado.error}</p>}
            {errorEjemplo && <p className="text-xs text-destructive">{errorEjemplo}</p>}
          </div>
        </div>

        <div className="flex flex-col-reverse gap-2 border-t pt-4 sm:flex-row sm:items-center">
          <Button variant="outline" onClick={usarEjemplo} disabled={ocupado || cargandoEjemplo}>
            {cargandoEjemplo ? <Spinner /> : <SparklesIcon />} Usar el ejemplo de la demo
          </Button>
          <Button
            variant="ghost"
            onClick={() => onMandar("")}
            disabled={ocupado}
            title="Sin texto: el agente repone los consumibles según el inventario"
          >
            {enviando === "reponer" ? <Spinner /> : <RepeatIcon />} Reponer lo de siempre
          </Button>
          <Button
            size="lg"
            className="sm:ml-auto"
            onClick={() => onMandar(texto)}
            disabled={ocupado || !texto.trim() || dictado.escuchando}
          >
            {enviando === "texto" ? <Spinner /> : <SendIcon />} Mandar al agente
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
