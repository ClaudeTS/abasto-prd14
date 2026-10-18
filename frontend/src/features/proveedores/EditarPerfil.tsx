// RF-17: edición del perfil de negociación (solo administrador). Lo editado alimenta al gemelo.
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { ErrorBanner } from "@/components/comunes";
import * as api from "./api";
import { Campo, Entrada } from "./comunes";
import type { EdicionPerfil, Perfil } from "./types";

const lista = (texto: string) =>
  texto
    .split(/[;\n]/)
    .map((s) => s.trim())
    .filter(Boolean);

export default function EditarPerfil({
  perfil,
  open,
  onOpenChange,
  onGuardado,
}: {
  perfil: Perfil;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onGuardado: (p: Perfil) => void;
}) {
  const { usuario } = useAuth();
  const inicial = () => ({
    estilo: perfil.estilo,
    condiciones_habituales: perfil.condiciones_habituales,
    precio_piso_pct: perfil.precio_piso_pct === null ? "" : String(perfil.precio_piso_pct),
    sensible_a: perfil.sensible_a.join("; "),
    no_sensible_a: perfil.no_sensible_a.join("; "),
    concesion_tipica: perfil.concesion_tipica,
    motivo: "",
  });
  const [f, setF] = useState(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setF(inicial());
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, perfil.version]);

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    setGuardando(true);
    setError(null);
    const cambios: EdicionPerfil = {
      estilo: f.estilo,
      condiciones_habituales: f.condiciones_habituales,
      sensible_a: lista(f.sensible_a),
      no_sensible_a: lista(f.no_sensible_a),
      concesion_tipica: f.concesion_tipica,
      motivo: f.motivo.trim() || undefined,
      usuario: usuario?.nombre,
    };
    if (f.precio_piso_pct.trim() !== "") cambios.precio_piso_pct = Number(f.precio_piso_pct);
    try {
      onGuardado(await api.editarPerfil(perfil.proveedor.id, cambios));
      onOpenChange(false);
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Editar perfil de {perfil.proveedor.nombre}</DialogTitle>
          <DialogDescription>
            El gemelo digital usa este perfil en la próxima negociación ensayada. Cada cambio queda en el historial.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={guardar} className="flex flex-col gap-4">
          <Campo etiqueta="Estilo" ayuda="Cómo se comunica y cotiza.">
            <Textarea rows={2} value={f.estilo} onChange={(e) => setF({ ...f, estilo: e.target.value })} />
          </Campo>
          <Campo etiqueta="Condiciones habituales" ayuda="Mínimo, envío, plazos de pago y entrega, forma de cotizar.">
            <Textarea
              rows={2}
              value={f.condiciones_habituales}
              onChange={(e) => setF({ ...f, condiciones_habituales: e.target.value })}
            />
          </Campo>
          <div className="grid gap-4 sm:grid-cols-[10rem_1fr]">
            <Campo etiqueta="Precio piso (%)" ayuda="Cuánto puede bajar.">
              <Entrada
                type="number"
                min={0}
                max={50}
                step={0.5}
                value={f.precio_piso_pct}
                onChange={(e) => setF({ ...f, precio_piso_pct: e.target.value })}
              />
            </Campo>
            <Campo etiqueta="Concesión típica" ayuda="Cuánto cede con cada palanca. Los % se resumen en el listado.">
              <Textarea
                rows={2}
                value={f.concesion_tipica}
                onChange={(e) => setF({ ...f, concesion_tipica: e.target.value })}
              />
            </Campo>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta="Sensible a" ayuda="Separá con punto y coma.">
              <Entrada value={f.sensible_a} onChange={(e) => setF({ ...f, sensible_a: e.target.value })} />
            </Campo>
            <Campo etiqueta="No sensible a" ayuda="Separá con punto y coma.">
              <Entrada value={f.no_sensible_a} onChange={(e) => setF({ ...f, no_sensible_a: e.target.value })} />
            </Campo>
          </div>
          <Campo etiqueta="Motivo del cambio (opcional)">
            <Entrada
              value={f.motivo}
              onChange={(e) => setF({ ...f, motivo: e.target.value })}
              placeholder="Ej.: en la última negociación cedió más por volumen"
            />
          </Campo>
          <ErrorBanner mensaje={error} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={guardando}>
              {guardando && <Spinner />} Guardar perfil
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
