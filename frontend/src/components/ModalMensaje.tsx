import { hora } from "@/lib/format";
import { CANALES, nombreProveedor } from "@/lib/proveedores";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Avatar, Evidencia } from "@/components/comunes";
import VistaMensaje from "@/components/VistaMensaje";
import type { MensajeCrudo } from "@/types";

/** Mensaje original al lado de lo extraído: la evidencia aparece resaltada. */
export default function ModalMensaje({
  mensaje,
  evidencias,
  onCerrar,
}: {
  mensaje: MensajeCrudo | null;
  evidencias: string[];
  onCerrar: () => void;
}) {
  const canal = mensaje ? CANALES[mensaje.canal] : null;
  return (
    <Dialog open={!!mensaje} onOpenChange={(abierto) => !abierto && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        {mensaje && (
          <>
            <DialogHeader className="flex-row items-center gap-3">
              <Avatar proveedorId={mensaje.proveedor_id} />
              <div className="space-y-1">
                <DialogTitle>{nombreProveedor(mensaje.proveedor_id)}</DialogTitle>
                <DialogDescription className="flex items-center gap-1.5">
                  {canal && <canal.icono className="size-3.5" />}
                  Mensaje original · {canal?.etiqueta} · {hora(mensaje.recibido_en)}
                </DialogDescription>
              </div>
            </DialogHeader>
            <div className="space-y-3">
              <VistaMensaje mensaje={mensaje} evidencias={evidencias} grande />
              {mensaje.canal !== "foto" && evidencias.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  <mark className="rounded-sm bg-yellow-200/80 px-1 dark:bg-yellow-500/30">Resaltado</mark>: fragmentos de
                  donde Abasto sacó cada precio.
                </p>
              )}
              {mensaje.canal === "foto" && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">Lo que Abasto leyó en la foto</p>
                  {evidencias.map((e, k) => (
                    <Evidencia key={k} texto={e} />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
