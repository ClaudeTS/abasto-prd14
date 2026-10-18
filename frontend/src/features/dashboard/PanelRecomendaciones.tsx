import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ClipboardCheckIcon,
  PhoneIcon,
  SparklesIcon,
  TagIcon,
  TrendingUpIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Etiqueta, type Tono } from "@/components/comunes";
import type { Recomendacion, Recomendaciones, TipoRecomendacion } from "./types";

const VISIBLES = 4; // el resto, con "Ver todas"

const TIPOS: Record<TipoRecomendacion, { etiqueta: string; tono: Tono; icono: LucideIcon }> = {
  alza_precio: { etiqueta: "Alza de precio", tono: "ambar", icono: TrendingUpIcon },
  oferta_otro_proveedor: { etiqueta: "Oferta", tono: "verde", icono: TagIcon },
  canal_mas_rapido: { etiqueta: "Canal", tono: "neutro", icono: PhoneIcon },
  pendiente_aprobacion: { etiqueta: "Aprobación", tono: "azul", icono: ClipboardCheckIcon },
};

function Item({
  r,
  onDescartar,
  descartando,
}: {
  r: Recomendacion;
  onDescartar: (id: string) => void;
  descartando: boolean;
}) {
  const tipo = TIPOS[r.tipo];
  const Icono = tipo.icono;
  return (
    <li className="flex gap-3 border-b border-ia-borde/70 py-4 first:pt-0 last:border-b-0 last:pb-0" data-testid="recomendacion">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-ia-bg text-azul">
        <Icono className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3 className="font-sans font-bold text-pretty">{r.titulo}</h3>
          <Etiqueta tono={tipo.tono}>{tipo.etiqueta}</Etiqueta>
          {r.ejemplo && <Etiqueta tono="ejemplo">Datos de ejemplo</Etiqueta>}
        </div>
        <p className="mt-1 text-sm text-pretty text-muted-foreground">{r.texto}</p>
        <dl className="mt-2.5 grid gap-x-4 gap-y-1 rounded-lg bg-white px-3 py-2 ring-1 ring-ia-borde/60 text-xs sm:grid-cols-[minmax(0,auto)_1fr]">
          {r.datos.map((d) => (
            <div key={d.etiqueta} className="contents">
              <dt className="text-muted-foreground">{d.etiqueta}</dt>
              <dd className="font-medium tabular-nums">
                {d.valor}
                {d.ejemplo && <span className="ml-1.5 font-normal text-gris-texto italic">(ejemplo)</span>}
              </dd>
            </div>
          ))}
        </dl>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to={r.enlace.ruta}>{r.enlace.etiqueta}</Link>
          </Button>
          {r.tipo !== "pendiente_aprobacion" && (
            <Button variant="ghost" size="sm" onClick={() => onDescartar(r.id)} disabled={descartando}>
              {descartando ? <Spinner /> : <XIcon />}
              Descartar
            </Button>
          )}
          {r.texto_origen === "llm" && (
            <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
              <SparklesIcon className="size-3" aria-hidden /> Redactado por la IA
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

export function PanelRecomendaciones({
  datos,
  cargando,
  onDescartar,
}: {
  datos: Recomendaciones | null;
  cargando: boolean;
  onDescartar: (id: string) => Promise<void>;
}) {
  const [descartando, setDescartando] = useState<string | null>(null);
  const [todas, setTodas] = useState(false);
  const lista = datos?.recomendaciones ?? [];
  const visibles = todas ? lista : lista.slice(0, VISIBLES);
  const descartar = async (id: string) => {
    setDescartando(id);
    try {
      await onDescartar(id);
    } finally {
      setDescartando(null);
    }
  };
  return (
    // Azul = lo hizo la IA (docs/DISENO.md): banda en azul profundo y fondo azul claro.
    <Card aria-label="Recomendaciones de la IA" className="bg-[#f2fafd] pt-0 ring-ia-borde">
      <CardHeader className="bg-azul-profundo py-4 text-white">
        <CardTitle className="flex items-center gap-2 font-bold">
          <SparklesIcon className="size-4 text-azul" aria-hidden /> Recomendaciones de la IA
        </CardTitle>
        <CardDescription className="text-white/75">
          Detectadas a partir de cotizaciones, compras y conversaciones. Cada una muestra los datos que la respaldan.
        </CardDescription>
        {datos && (
          <CardAction>
            <Etiqueta className="border-transparent bg-azul text-grafito">
              {lista.length === 1 ? "1 nueva" : `${lista.length} nuevas`}
            </Etiqueta>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {cargando && !datos ? (
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : lista.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No hay recomendaciones nuevas.
            {datos?.descartadas ? ` Descartaste ${datos.descartadas}.` : ""}
          </p>
        ) : (
          <>
            <ul>
              {visibles.map((r) => (
                <Item key={r.id} r={r} onDescartar={descartar} descartando={descartando === r.id} />
              ))}
            </ul>
            {lista.length > VISIBLES && (
              <Button variant="outline" size="sm" className="mt-4 self-start" onClick={() => setTodas((t) => !t)}>
                {todas ? "Ver menos" : `Ver todas (${lista.length})`}
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
