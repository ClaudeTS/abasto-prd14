// RF-19: alta de proveedor, manual o por el agente (conversación simulada que queda en revisión).
import { useEffect, useState, type FormEvent } from "react";
import { BotIcon, CheckIcon, ClipboardPenIcon, SparklesIcon } from "lucide-react";
import pedidoJson from "../../../../data/pedido_demo.json";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";
import { cn } from "@/lib/utils";
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
import { ErrorBanner, Etiqueta } from "@/components/comunes";
import * as api from "./api";
import { Campo, Dato, Entrada, Selector, dias, garantia, nombreCanal, pago } from "./comunes";
import type { Alta, AltaAgente } from "./types";

const CATALOGO = pedidoJson.catalogo as { id: string; nombre: string }[];

export interface InicialAlta {
  productos?: string[];
  pedidoId?: string;
  motivo?: string;
}

type Modo = "agente" | "manual";

export default function AltaProveedor({
  open,
  onOpenChange,
  onCreado,
  inicial,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreado?: (alta: Alta) => void;
  inicial?: InicialAlta;
}) {
  const [modo, setModo] = useState<Modo>("agente");
  const [resultado, setResultado] = useState<Alta | null>(null);

  useEffect(() => {
    if (open) {
      setModo("agente");
      setResultado(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{resultado ? `Alta de ${resultado.nombre}` : "Alta de proveedor"}</DialogTitle>
          <DialogDescription>
            {resultado
              ? resultado.alta_por === "agente"
                ? "El agente contactó al proveedor y cargó sus datos. Queda en revisión hasta que un administrador la apruebe."
                : "Proveedor cargado y activo."
              : "Cargalo vos o dejá que el agente lo contacte y le pida los datos (simulado en el MVP)."}
          </DialogDescription>
        </DialogHeader>

        {resultado ? (
          <ResultadoAlta
            alta={resultado}
            onAprobada={(a) => {
              setResultado(a);
              onCreado?.(a);
            }}
          />
        ) : (
          <>
            <div role="tablist" className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
              {(
                [
                  ["agente", "Que el agente lo dé de alta", BotIcon],
                  ["manual", "Carga manual", ClipboardPenIcon],
                ] as const
              ).map(([m, texto, Icono]) => (
                <button
                  key={m}
                  type="button"
                  role="tab"
                  aria-selected={modo === m}
                  onClick={() => setModo(m)}
                  className={cn(
                    "flex h-8 items-center justify-center gap-1.5 rounded-md text-sm text-muted-foreground transition-colors",
                    modo === m && "bg-background font-medium text-foreground shadow-xs",
                  )}
                >
                  <Icono className="size-4" aria-hidden /> {texto}
                </button>
              ))}
            </div>
            {modo === "agente" ? (
              <FormAgente
                inicial={inicial}
                onListo={(a) => {
                  setResultado(a);
                  onCreado?.(a);
                }}
              />
            ) : (
              <FormManual
                inicial={inicial}
                onListo={(a) => {
                  setResultado(a);
                  onCreado?.(a);
                }}
              />
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Productos({ valor, onChange }: { valor: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="flex flex-col gap-1.5 text-sm">
      <legend className="mb-1.5 font-medium">Productos que ofrece</legend>
      <div className="flex flex-wrap gap-1.5">
        {CATALOGO.map((p) => {
          const activo = valor.includes(p.id);
          return (
            <button
              key={p.id}
              type="button"
              aria-pressed={activo}
              onClick={() => onChange(activo ? valor.filter((v) => v !== p.id) : [...valor, p.id])}
              className={cn(
                "inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs transition-colors",
                activo ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted",
              )}
            >
              {activo && <CheckIcon className="size-3" aria-hidden />}
              {p.nombre}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function FormAgente({ inicial, onListo }: { inicial?: InicialAlta; onListo: (a: Alta) => void }) {
  const [datos, setDatos] = useState<AltaAgente>({
    nombre: "",
    canal: "whatsapp",
    telefono: "",
    email: "",
    productos: inicial?.productos ?? [],
    pedido_id: inicial?.pedidoId,
    motivo: inicial?.motivo ?? "",
  });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      onListo(
        await api.altaPorAgente({
          ...datos,
          nombre: datos.nombre.trim(),
          telefono: datos.telefono?.trim() || undefined,
          email: datos.email?.trim() || undefined,
          motivo: datos.motivo?.trim() || undefined,
        }),
      );
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form onSubmit={enviar} className="flex flex-col gap-4">
      <p className="rounded-lg border border-dashed bg-muted/40 p-3 text-sm text-muted-foreground">
        El agente le escribe al proveedor, le pide <b className="font-medium text-foreground">razón social, contacto, canales,
        condiciones y productos</b>, y lo carga en revisión. En el MVP la conversación es simulada: no sale ningún mensaje.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Nombre del proveedor" className="sm:col-span-2">
          <Entrada
            required
            minLength={2}
            value={datos.nombre}
            onChange={(e) => setDatos({ ...datos, nombre: e.target.value })}
            placeholder="Ej.: Distribuidora Norte"
          />
        </Campo>
        <Campo etiqueta="Teléfono o WhatsApp">
          <Entrada
            type="tel"
            value={datos.telefono}
            onChange={(e) => setDatos({ ...datos, telefono: e.target.value })}
            placeholder="+598 9…"
          />
        </Campo>
        <Campo etiqueta="Canal para contactarlo">
          <Selector value={datos.canal} onChange={(e) => setDatos({ ...datos, canal: e.target.value as AltaAgente["canal"] })}>
            <option value="whatsapp">WhatsApp</option>
            <option value="email">Email</option>
            <option value="llamada">Llamada</option>
          </Selector>
        </Campo>
        <Campo etiqueta="Email (opcional)" className="sm:col-span-2">
          <Entrada type="email" value={datos.email} onChange={(e) => setDatos({ ...datos, email: e.target.value })} />
        </Campo>
      </div>
      <Productos valor={datos.productos ?? []} onChange={(productos) => setDatos({ ...datos, productos })} />
      <Campo etiqueta="Por qué lo contactamos (opcional)" ayuda="El agente lo menciona al presentarse.">
        <Textarea
          rows={2}
          value={datos.motivo}
          onChange={(e) => setDatos({ ...datos, motivo: e.target.value })}
          placeholder="Ej.: Necesitamos más cotizaciones de sillas para este pedido."
        />
      </Campo>
      <ErrorBanner mensaje={error} />
      <DialogFooter>
        <Button type="submit" disabled={enviando || datos.nombre.trim().length < 2}>
          {enviando ? <Spinner /> : <SparklesIcon />} Que el agente lo contacte
        </Button>
      </DialogFooter>
    </form>
  );
}

function FormManual({ inicial, onListo }: { inicial?: InicialAlta; onListo: (a: Alta) => void }) {
  const { usuario } = useAuth();
  const [f, setF] = useState({
    nombre: "",
    razon_social: "",
    rubro: "",
    email: "",
    telefono: "",
    whatsapp: true,
    canal_preferido: "whatsapp_texto",
    plazo_pago_dias: "30",
    plazo_entrega_dias: "",
    garantia_meses: "",
    productos: inicial?.productos ?? [],
  });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entero = (v: string) => (v.trim() === "" ? null : Math.max(0, Math.round(Number(v))));

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      onListo(
        await api.altaManual({
          nombre: f.nombre.trim(),
          razon_social: f.razon_social.trim() || undefined,
          rubro: f.rubro.trim(),
          contacto: { email: f.email.trim() || undefined, telefono: f.telefono.trim() || undefined },
          whatsapp: f.whatsapp,
          canal_preferido: f.canal_preferido,
          condiciones: {
            plazo_pago_dias: entero(f.plazo_pago_dias),
            plazo_entrega_dias: entero(f.plazo_entrega_dias),
            garantia_meses: entero(f.garantia_meses),
          },
          productos: f.productos,
          usuario: usuario?.nombre,
        }),
      );
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form onSubmit={enviar} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Nombre">
          <Entrada required minLength={2} value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} />
        </Campo>
        <Campo etiqueta="Razón social">
          <Entrada value={f.razon_social} onChange={(e) => setF({ ...f, razon_social: e.target.value })} />
        </Campo>
        <Campo etiqueta="Rubro" className="sm:col-span-2">
          <Entrada
            value={f.rubro}
            onChange={(e) => setF({ ...f, rubro: e.target.value })}
            placeholder="Ej.: mobiliario de oficina / distribuidor"
          />
        </Campo>
        <Campo etiqueta="Email">
          <Entrada type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </Campo>
        <Campo etiqueta="Teléfono">
          <Entrada type="tel" value={f.telefono} onChange={(e) => setF({ ...f, telefono: e.target.value })} />
        </Campo>
        <Campo etiqueta="Canal preferido">
          <Selector value={f.canal_preferido} onChange={(e) => setF({ ...f, canal_preferido: e.target.value })}>
            <option value="whatsapp_texto">WhatsApp</option>
            <option value="pdf">Email</option>
            <option value="llamada">Llamada</option>
          </Selector>
        </Campo>
        <label className="flex items-center gap-2 self-end pb-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={f.whatsapp}
            onChange={(e) => setF({ ...f, whatsapp: e.target.checked })}
          />
          Tiene WhatsApp
        </label>
        <Campo etiqueta="Plazo de pago (días)" ayuda="0 = contado">
          <Entrada type="number" min={0} value={f.plazo_pago_dias} onChange={(e) => setF({ ...f, plazo_pago_dias: e.target.value })} />
        </Campo>
        <Campo etiqueta="Plazo de entrega (días)">
          <Entrada
            type="number"
            min={0}
            value={f.plazo_entrega_dias}
            onChange={(e) => setF({ ...f, plazo_entrega_dias: e.target.value })}
          />
        </Campo>
        <Campo etiqueta="Garantía (meses)">
          <Entrada type="number" min={0} value={f.garantia_meses} onChange={(e) => setF({ ...f, garantia_meses: e.target.value })} />
        </Campo>
      </div>
      <Productos valor={f.productos} onChange={(productos) => setF({ ...f, productos })} />
      <ErrorBanner mensaje={error} />
      <DialogFooter>
        <Button type="submit" disabled={enviando || f.nombre.trim().length < 2}>
          {enviando && <Spinner />} Dar de alta
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ConversacionAlta({ alta }: { alta: Alta }) {
  return (
    <div className="flex flex-col gap-2">
      {alta.conversacion.map((t, k) => (
        <div
          key={k}
          className={cn(
            "max-w-[85%] rounded-xl px-3 py-2 text-sm leading-relaxed",
            t.rol === "abasto" ? "self-end bg-primary text-primary-foreground" : "self-start bg-muted",
          )}
        >
          <div className="mb-0.5 text-[11px] font-semibold tracking-wide uppercase opacity-70">
            {t.rol === "abasto" ? "Agente de Abasto" : alta.nombre}
          </div>
          {t.texto}
        </div>
      ))}
    </div>
  );
}

function ResultadoAlta({ alta, onAprobada }: { alta: Alta; onAprobada: (a: Alta) => void }) {
  const { esAdmin, usuario } = useAuth();
  const [aprobando, setAprobando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const c = alta.condiciones;

  const aprobar = async () => {
    setAprobando(true);
    setError(null);
    try {
      onAprobada(await api.aprobarAlta(alta.id, usuario?.nombre));
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setAprobando(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <Etiqueta tono={alta.estado === "activo" ? "verde" : "ambar"}>
          {alta.estado === "activo" ? "Activo" : "En revisión"}
        </Etiqueta>
        <Etiqueta tono="azul">{alta.alta_por === "agente" ? "Alta por el agente" : "Alta manual"}</Etiqueta>
        {alta.simulada && <Etiqueta>Conversación simulada</Etiqueta>}
      </div>
      {alta.conversacion.length > 0 && (
        <div className="rounded-xl border bg-muted/20 p-3">
          <p className="mb-3 text-xs text-muted-foreground">Conversación por {nombreCanal(alta.conversacion[0].canal)}</p>
          <ConversacionAlta alta={alta} />
        </div>
      )}
      <div className="rounded-xl border px-4 py-1 text-sm">
        <Dato etiqueta="Razón social">{alta.razon_social}</Dato>
        <Dato etiqueta="Contacto">
          {[alta.contacto.nombre, alta.contacto.email, alta.contacto.telefono].filter(Boolean).join(" · ") || "—"}
        </Dato>
        <Dato etiqueta="Canales">{alta.canales.map(nombreCanal).join(", ")}</Dato>
        <Dato etiqueta="Condiciones">
          {[
            c.plazo_pago_dias !== null && `pago ${pago(c.plazo_pago_dias)}`,
            c.plazo_entrega_dias !== null && `entrega ${dias(c.plazo_entrega_dias)}`,
            c.pedido_minimo,
            c.envio && `envío ${c.envio}`,
            c.garantia_meses && `garantía ${garantia(c.garantia_meses)}`,
          ]
            .filter(Boolean)
            .join(" · ") || "—"}
        </Dato>
        <Dato etiqueta="Productos">
          {alta.productos.map((p) => CATALOGO.find((x) => x.id === p)?.nombre ?? p).join(", ") || "—"}
        </Dato>
      </div>
      <ErrorBanner mensaje={error} />
      {alta.estado === "en_revision" && (
        <DialogFooter>
          {esAdmin ? (
            <Button onClick={aprobar} disabled={aprobando}>
              {aprobando ? <Spinner /> : <CheckIcon />} Aprobar alta
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">Un administrador tiene que aprobar el alta.</p>
          )}
        </DialogFooter>
      )}
    </div>
  );
}
