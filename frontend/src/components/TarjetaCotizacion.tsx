import { useState } from "react";
import { ArrowRightLeftIcon, TriangleAlertIcon } from "lucide-react";
import { monedaOriginal, pesos, plazoPago, precioUnitario, unidad } from "@/lib/format";
import { CANALES, proveedor } from "@/lib/proveedores";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { Avatar, Etiqueta, Evidencia } from "@/components/comunes";
import type { Cotizacion, ItemCotizado, Producto } from "@/types";

const DUDOSOS: Record<string, string> = {
  iva: "si los precios incluyen IVA",
  unidad: "la unidad en la que cotiza",
  moneda: "la moneda",
  producto: "si el producto es el pedido",
};

export const necesitaRevision = (c: Cotizacion) => c.confianza < 0.6 || c.campos_dudosos.length > 0;

export default function TarjetaCotizacion({
  cotizacion: c,
  catalogo,
  destacada = false,
  onVerOriginal,
  onConfirmar,
}: {
  cotizacion: Cotizacion;
  catalogo: Producto[];
  destacada?: boolean;
  onVerOriginal: () => void;
  onConfirmar: (campo: string, valor: boolean) => Promise<void>;
}) {
  const p = proveedor(c.proveedor_id);
  const canal = CANALES[p.canal_preferido];
  const revisar = c.confianza < 0.6;
  const ivaDudoso = c.campos_dudosos.includes("iva");
  const [confirmando, setConfirmando] = useState<boolean | null>(null);
  const ivas = new Set(c.items.map((i) => i.incluye_iva_original));

  const confirmar = async (valor: boolean) => {
    setConfirmando(valor);
    try {
      await onConfirmar("iva", valor);
    } finally {
      setConfirmando(null);
    }
  };

  return (
    <Card
      id={c.id}
      className={cn(
        "scroll-mt-24",
        revisar && "ring-2 ring-amber-400 dark:ring-amber-600",
        destacada && "animate-destello",
      )}
    >
      <CardHeader>
        <div className="flex items-center gap-3">
          <Avatar proveedorId={c.proveedor_id} />
          <div className="min-w-0 space-y-0.5">
            <CardTitle className="flex items-center gap-2">
              {p.nombre}
              {revisar && (
                <Etiqueta tono="ambar">
                  <TriangleAlertIcon /> Revisar
                </Etiqueta>
              )}
            </CardTitle>
            <CardDescription className="flex items-center gap-1.5">
              {p.rubro} · <canal.icono className="size-3.5" /> {canal.etiqueta}
            </CardDescription>
          </div>
        </div>
        <CardAction>
          <Button variant="outline" size="sm" onClick={onVerOriginal}>
            Ver original
          </Button>
        </CardAction>
      </CardHeader>

      {(ivaDudoso || (revisar && c.campos_dudosos.length > 0)) && (
        <CardContent>
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
            <p>
              <span className="font-medium">Abasto no adivina:</span> el mensaje no deja claro{" "}
              {c.campos_dudosos.map((d) => DUDOSOS[d] ?? d).join(" ni ")}. Confianza de la lectura{" "}
              {Math.round(c.confianza * 100)} %.
            </p>
            {ivaDudoso && (
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">¿Incluyen IVA?</span>
                <Button size="sm" disabled={confirmando !== null} onClick={() => confirmar(true)}>
                  {confirmando === true && <Spinner />} Sí, IVA incluido
                </Button>
                <Button size="sm" variant="outline" disabled={confirmando !== null} onClick={() => confirmar(false)}>
                  {confirmando === false && <Spinner />} No, son más IVA
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      )}

      <CardContent className="gap-0">
        {c.items.map((item, k) => (
          <div key={k}>
            {k > 0 && <Separator className="my-4" />}
            <Item item={item} catalogo={catalogo} ivaDudoso={ivaDudoso} />
          </div>
        ))}
      </CardContent>

      <CardFooter className="flex-col items-start gap-3 border-t">
        <div className="flex flex-wrap gap-1.5">
          {ivaDudoso ? (
            <Etiqueta tono="ambar">IVA sin aclarar</Etiqueta>
          ) : ivas.size === 1 ? (
            <Etiqueta>{[...ivas][0] ? "Con IVA (descontado)" : "Precios + IVA"}</Etiqueta>
          ) : null}
          <Etiqueta>{c.costo_envio > 0 ? `Envío ${pesos(c.costo_envio)}` : "Envío sin cargo"}</Etiqueta>
          <Etiqueta>{plazoPago(c.plazo_pago_dias)}</Etiqueta>
          <Etiqueta>Entrega {c.lead_time_dias} días</Etiqueta>
          {c.pedido_minimo_total ? <Etiqueta>Mínimo {pesos(c.pedido_minimo_total)}</Etiqueta> : null}
          {c.validez_dias ? <Etiqueta tono="ambar">Validez {c.validez_dias} días</Etiqueta> : null}
          <Etiqueta title="Cumplimiento histórico de entregas (dato seedeado)">
            Cumple {Math.round(p.confiabilidad * 100)} %
          </Etiqueta>
        </div>
        {c.observaciones.length > 0 && (
          <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
            {c.observaciones.map((o, k) => (
              <li key={k}>{o}</li>
            ))}
          </ul>
        )}
      </CardFooter>
    </Card>
  );
}

function Item({ item, catalogo, ivaDudoso }: { item: ItemCotizado; catalogo: Producto[]; ivaDudoso: boolean }) {
  const producto = catalogo.find((p) => p.id === item.producto_id);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <p className="font-medium">
            {producto?.nombre ?? (
              <span className="text-amber-700">Sin mapear al catálogo: {item.descripcion_original}</span>
            )}
          </p>
          <p className="text-muted-foreground">
            Cotizó {monedaOriginal(item.precio_original, item.moneda_original)} por {item.unidad_original}
            {ivaDudoso ? " · IVA sin aclarar" : item.incluye_iva_original ? " · con IVA" : " · + IVA"}
            {item.cantidad_minima ? ` · mínimo ${item.cantidad_minima}` : ""}
          </p>
        </div>
        <div className="ml-auto text-right">
          <p
            className={cn(
              "text-xl font-semibold tracking-tight whitespace-nowrap tabular-nums",
              ivaDudoso && "text-amber-700 dark:text-amber-400",
            )}
          >
            {precioUnitario(item.precio_unitario_sin_iva)}
          </p>
          <p className="text-xs text-muted-foreground">
            por {producto ? unidad(producto.unidad_canonica, 1) : "unidad"}, sin IVA
          </p>
        </div>
      </div>
      {item.conversion_aplicada && (
        <p className="inline-flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 font-mono text-xs">
          <ArrowRightLeftIcon className="size-3" /> {item.conversion_aplicada}
        </p>
      )}
      <Evidencia texto={item.evidencia} />
    </div>
  );
}
