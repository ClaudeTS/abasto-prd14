import { useState } from "react";
import { MicIcon, SparklesIcon, SquareIcon } from "lucide-react";
import * as api from "@/api";
import { mensajeError } from "@/lib/errores";
import { useDictado } from "@/lib/dictado";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBanner } from "@/components/comunes";
import type { NuevaCorrida } from "@/types";

// Lo único que hace la persona: decir qué hay que comprar. Del resto se encarga el agente.

const PASOS_DEL_AGENTE = [
  "Entiende el pedido",
  "Revisa el inventario",
  "Pide cotizaciones",
  "Llama a quien no contesta",
  "Aclara las dudas con el proveedor",
  "Arma el plan",
  "Negocia",
  "Emite las órdenes",
];

export default function Composer({
  onComprar,
  ocupado,
  error,
}: {
  onComprar: (nueva: NuevaCorrida) => Promise<void>;
  ocupado: boolean;
  error: string | null;
}) {
  const [texto, setTexto] = useState("");
  const [piloto, setPiloto] = useState(true);
  const [llamar, setLlamar] = useState(true);
  const [negociar, setNegociar] = useState(true);
  const [cargandoEjemplo, setCargandoEjemplo] = useState(false);
  const [errorEjemplo, setErrorEjemplo] = useState<string | null>(null);
  const dictado = useDictado(setTexto);

  const usarEjemplo = async () => {
    setCargandoEjemplo(true);
    setErrorEjemplo(null);
    try {
      setTexto(await api.getEjemploAgente());
    } catch (e) {
      setErrorEjemplo(mensajeError(e));
    } finally {
      setCargandoEjemplo(false);
    }
  };

  const comprar = () =>
    onComprar({
      texto: texto.trim() || null,
      esperar_confirmacion: false,
      resolver_dudas: true,
      autonomia: piloto ? "total" : "topes",
      llamar_si_no_responde: llamar,
      negociar,
    });

  return (
    <div className="mx-auto max-w-3xl space-y-8 py-6">
      <div className="space-y-3 text-center">
        <span className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs text-muted-foreground">
          <SparklesIcon className="size-3.5" /> Agente de compras
        </span>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">¿Qué hay que comprar?</h1>
        <p className="mx-auto max-w-xl text-lg text-muted-foreground">
          Decíselo a Abasto como se lo dirías a alguien del equipo. Él hace la compra entera y te avisa cuando termina.
        </p>
      </div>

      <Card className="gap-0 py-0">
        <CardContent className="gap-0 p-0">
          <div className="flex items-start gap-3 p-4">
            {dictado.soportado && (
              <button
                type="button"
                onClick={dictado.escuchando ? dictado.parar : dictado.empezar}
                disabled={ocupado}
                aria-label={dictado.escuchando ? "Dejar de escuchar" : "Dictar el pedido"}
                className={cn(
                  "relative mt-1 flex size-12 shrink-0 items-center justify-center rounded-full transition-colors disabled:opacity-50",
                  dictado.escuchando
                    ? "bg-red-600 text-white"
                    : "bg-primary text-primary-foreground hover:bg-primary/85",
                )}
              >
                {dictado.escuchando && <span className="absolute inset-0 animate-ping rounded-full bg-red-600/40" />}
                {dictado.escuchando ? <SquareIcon className="relative size-4 fill-current" /> : <MicIcon className="size-5" />}
              </button>
            )}
            <Textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !ocupado) comprar();
              }}
              placeholder={
                dictado.escuchando
                  ? "Te escucho…"
                  : "Ej.: Armá la compra del mes. Entran diez personas nuevas el 28 y necesitan notebook…"
              }
              rows={3}
              className="min-h-24 resize-none border-0 text-base shadow-none focus-visible:ring-0"
              disabled={ocupado}
            />
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t px-4 py-3">
            <Button variant="ghost" size="sm" onClick={usarEjemplo} disabled={ocupado || cargandoEjemplo}>
              {cargandoEjemplo && <Spinner />} Usar el ejemplo
            </Button>
            <span className="text-xs text-muted-foreground">
              {texto.trim() ? "Revisá el texto antes de mandarlo." : "Vacío: repone lo de siempre."}
            </span>
            <Button className="ml-auto" size="lg" onClick={comprar} disabled={ocupado}>
              {ocupado ? <Spinner /> : <SparklesIcon />} {texto.trim() ? "Hacer la compra" : "Reponer lo de siempre"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <ErrorBanner mensaje={dictado.error ?? errorEjemplo ?? error} />

      <div className="grid gap-3 sm:grid-cols-3">
        <Opcion
          titulo="Piloto automático"
          descripcion={
            piloto
              ? "Abasto aprueba y manda todo solo, también lo que está en manual o supera su tope."
              : "Lo que está en manual o supera su tope en Inventario espera tu OK."
          }
          activo={piloto}
          onCambiar={setPiloto}
          disabled={ocupado}
        />
        <Opcion
          titulo="Llamar si no contestan"
          descripcion="A quien no respondió a tiempo, lo llama por teléfono."
          activo={llamar}
          onCambiar={setLlamar}
          disabled={ocupado}
        />
        <Opcion
          titulo="Negociar"
          descripcion="Ensaya la negociación contra un gemelo del proveedor."
          activo={negociar}
          onCambiar={setNegociar}
          disabled={ocupado}
        />
      </div>

      <ol className="flex flex-wrap justify-center gap-x-1 gap-y-2 text-sm text-muted-foreground">
        {PASOS_DEL_AGENTE.map((p, i) => (
          <li key={p} className="flex items-center gap-1">
            <span className="tabular-nums">{i + 1}.</span> {p}
            {i < PASOS_DEL_AGENTE.length - 1 && <span className="mx-1 text-muted-foreground/40">·</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Opcion({
  titulo,
  descripcion,
  activo,
  onCambiar,
  disabled,
}: {
  titulo: string;
  descripcion: string;
  activo: boolean;
  onCambiar: (v: boolean) => void;
  disabled: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 has-disabled:cursor-not-allowed has-disabled:opacity-60">
      <Switch checked={activo} onCheckedChange={onCambiar} disabled={disabled} className="mt-0.5" />
      <span className="space-y-0.5">
        <span className="block text-sm font-medium">{titulo}</span>
        <span className="block text-xs text-muted-foreground">{descripcion}</span>
      </span>
    </label>
  );
}
