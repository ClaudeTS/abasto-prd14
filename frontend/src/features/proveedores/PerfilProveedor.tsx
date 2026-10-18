// RF-17: perfil completo de un proveedor (fila seleccionada del listado).
import { useCallback, useEffect, useState } from "react";
import { BotIcon, CheckIcon, PencilIcon } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";
import { formatNumero } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { ErrorBanner, Etiqueta } from "@/components/comunes";
import * as api from "./api";
import { ConversacionAlta } from "./AltaProveedor";
import EditarPerfil from "./EditarPerfil";
import { BadgeConfianza, DatosEjemplo, Dato, duracion, fecha, garantia, nombreCanal, pp } from "./comunes";
import type { Perfil, TiempoRespuesta } from "./types";

const ESTRATEGIA: Record<string, string> = { competencia: "competencia", volumen: "volumen", plazo: "contado" };

export default function PerfilProveedor({ proveedorId, onCambio }: { proveedorId: string; onCambio?: () => void }) {
  const { esAdmin, usuario } = useAuth();
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [aprobando, setAprobando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setError(null);
      setPerfil(await api.obtenerPerfil(proveedorId));
    } catch (e) {
      setError(mensajeError(e));
    }
  }, [proveedorId]);

  useEffect(() => {
    setPerfil(null);
    cargar();
  }, [cargar]);

  if (error) return <ErrorBanner mensaje={error} onReintentar={cargar} />;
  if (!perfil)
    return (
      <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
        <Skeleton className="h-96 rounded-xl" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );

  const p = perfil.proveedor;
  const nuevo = p.alta_por === "agente" || !p.datos_ejemplo;
  const aprobar = async () => {
    setAprobando(true);
    try {
      await api.aprobarAlta(p.id, usuario?.nombre);
      await cargar();
      onCambio?.();
    } catch (e) {
      setError(mensajeError(e));
    } finally {
      setAprobando(false);
    }
  };

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[3fr_2fr]">
      <Card aria-label={`Perfil de negociación de ${p.nombre}`}>
        <CardHeader>
          <CardTitle className="text-base">{p.nombre} · perfil de negociación</CardTitle>
          <CardDescription>
            Alimenta al gemelo digital ·{" "}
            {perfil.editado
              ? `actualizado el ${fecha(perfil.actualizado_el)} por ${perfil.actualizado_por}`
              : "perfil inicial, sin ediciones"}
          </CardDescription>
          {esAdmin && (
            <CardAction>
              <Button variant="outline" size="sm" onClick={() => setEditando(true)}>
                <PencilIcon /> Editar perfil
              </Button>
            </CardAction>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {p.estado === "en_revision" && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
              <span className="flex items-center gap-2">
                <BotIcon className="size-4" aria-hidden /> Alta hecha por el agente: revisá los datos antes de usarlo.
              </span>
              {esAdmin && (
                <Button size="sm" onClick={aprobar} disabled={aprobando}>
                  {aprobando ? <Spinner /> : <CheckIcon />} Aprobar alta
                </Button>
              )}
            </div>
          )}
          <div>
            <Dato etiqueta="Estilo">{perfil.estilo || "—"}</Dato>
            <Dato etiqueta="Condiciones habituales">{perfil.condiciones_habituales || "—"}</Dato>
            <Dato etiqueta="Precio piso estimado">
              {perfil.precio_piso_pct !== null ? `hasta ${formatNumero(perfil.precio_piso_pct, 0)} % bajo lo cotizado` : "s/d"}
            </Dato>
            <Dato etiqueta="Sensible a">{perfil.sensible_a.join("; ") || "—"}</Dato>
            <Dato etiqueta="No sensible a">{perfil.no_sensible_a.join("; ") || "—"}</Dato>
            <Dato etiqueta="Concesión típica">
              {perfil.concesion_tipica_rango && <span className="font-medium">{perfil.concesion_tipica_rango} · </span>}
              {perfil.concesion_tipica || "—"}
            </Dato>
            <Dato etiqueta="Negociaciones observadas">{perfil.negociaciones_observadas}</Dato>
            <Dato etiqueta="Confianza del gemelo">
              <span className="inline-flex flex-wrap items-center justify-end gap-2">
                <BadgeConfianza c={perfil.confianza} />
                <span className="text-muted-foreground">{perfil.confianza.motivo}</span>
              </span>
            </Dato>
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-1 text-sm">
            <Dato etiqueta="Antigüedad">{p.antiguedad.texto}</Dato>
            <Dato etiqueta="Cumplimiento histórico">
              {p.cumplimiento_historico_pct !== null ? `${formatNumero(p.cumplimiento_historico_pct)} %` : "—"}
            </Dato>
            <Dato etiqueta="Garantía">{garantia(p.garantia_meses)}</Dato>
            <Dato etiqueta="Contacto">
              {[p.email, p.whatsapp ? "WhatsApp" : null].filter(Boolean).join(" · ") || "—"}
            </Dato>
          </div>
          {p.datos_ejemplo && (
            <DatosEjemplo>Antigüedad, cumplimiento, garantía y contacto todavía no vienen de un sistema real.</DatosEjemplo>
          )}
          {perfil.historial_ediciones.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">
                Historial de cambios ({perfil.historial_ediciones.length})
              </summary>
              <ul className="mt-2 flex flex-col gap-2">
                {[...perfil.historial_ediciones].reverse().map((h, k) => (
                  <li key={k} className="rounded-md border px-3 py-2">
                    <div className="text-xs text-muted-foreground">
                      {fecha(h.fecha)} · {h.usuario}
                      {h.motivo && ` · ${h.motivo}`}
                    </div>
                    {Object.entries(h.cambios).map(([campo, c]) => (
                      <div key={campo}>
                        <span className="font-medium">{campo.replace(/_/g, " ")}</span>:{" "}
                        <span className="text-muted-foreground line-through">{texto(c.antes)}</span> → {texto(c.despues)}
                      </div>
                    ))}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {!esAdmin && <p className="text-xs text-muted-foreground">Solo el administrador puede editar el perfil.</p>}
        </CardContent>
      </Card>

      <div className="flex min-w-0 flex-col gap-4">
        <TiemposRespuesta t={perfil.tiempo_respuesta} nombre={p.nombre} />
        <GemeloVsReal perfil={perfil} nuevo={nuevo && perfil.historial_negociaciones.length === 0} />
        {perfil.alta && perfil.alta.conversacion.length > 0 && (
          <Card size="sm">
            <CardHeader>
              <CardTitle>Conversación del alta</CardTitle>
              <CardDescription>
                El agente le pidió razón social, contacto, canales, condiciones y productos
                {perfil.alta.simulada ? " · simulada" : ""}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ConversacionAlta alta={perfil.alta} />
            </CardContent>
          </Card>
        )}
      </div>

      <EditarPerfil
        perfil={perfil}
        open={editando}
        onOpenChange={setEditando}
        onGuardado={(nuevoPerfil) => {
          setPerfil(nuevoPerfil);
          onCambio?.();
        }}
      />
    </div>
  );
}

function texto(v: unknown): string {
  if (Array.isArray(v)) return v.join("; ") || "—";
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

function TiemposRespuesta({ t, nombre }: { t: TiempoRespuesta; nombre: string }) {
  const max = Math.max(...t.canales.map((c) => c.promedio_segundos), 1);
  const vacio = t.canales.length === 0 && !t.llamadas;
  return (
    <Card size="sm" aria-label="Tiempo de respuesta por canal">
      <CardHeader>
        <CardTitle>Tiempo de respuesta por canal</CardTitle>
        <CardDescription>{nombre} · solicitudes de cotización registradas en Abasto</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3.5">
        {vacio && (
          <p className="text-sm text-muted-foreground">
            Sin datos todavía: aparecen cuando el proveedor responde una solicitud de cotización o atiende una llamada.
          </p>
        )}
        {t.canales.map((c) => (
          <div key={c.canal}>
            <div className="flex justify-between gap-2 text-sm">
              <span>
                {nombreCanal(c.canal)}
                {t.mas_rapido === c.canal && t.canales.length > 1 && (
                  <Etiqueta tono="verde" className="ml-2">
                    más rápido
                  </Etiqueta>
                )}
              </span>
              <span className="text-muted-foreground tabular-nums">
                {duracion(c.promedio_segundos)}
                {c.respuestas > 1 && ` · ${c.respuestas} respuestas`}
              </span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
              <div className="h-2 rounded-full bg-primary" style={{ width: `${Math.max(6, (c.promedio_segundos / max) * 100)}%` }} />
            </div>
          </div>
        ))}
        {t.llamadas && (
          <div>
            <div className="flex justify-between gap-2 text-sm">
              <span>Llamada</span>
              <span className="text-muted-foreground tabular-nums">
                atiende {t.llamadas.atendidas} de {t.llamadas.realizadas}
                {t.llamadas.duracion_promedio_segundos && ` · ${duracion(t.llamadas.duracion_promedio_segundos)}`}
              </span>
            </div>
            <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-2 rounded-full bg-muted-foreground"
                style={{ width: `${(t.llamadas.atendidas / Math.max(t.llamadas.realizadas, 1)) * 100}%` }}
              />
            </div>
          </div>
        )}
        {!vacio && <p className="text-xs text-muted-foreground">En la demo, los tiempos son los del simulador de proveedores.</p>}
      </CardContent>
    </Card>
  );
}

function GemeloVsReal({ perfil, nuevo }: { perfil: Perfil; nuevo: boolean }) {
  const filas = perfil.historial_negociaciones;
  const conEjemplo = filas.some((f) => f.ejemplo);
  return (
    <Card size="sm" aria-label="Gemelo contra negociación real">
      <CardHeader>
        <CardTitle>Gemelo contra negociación real</CardTitle>
        <CardDescription>Concesión simulada · concesión real · desvío</CardDescription>
      </CardHeader>
      <CardContent>
        {filas.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {nuevo ? "Proveedor nuevo: todavía no hay negociaciones." : "Todavía no hay negociaciones con este proveedor."}
          </p>
        ) : (
          <ul className="flex flex-col">
            {filas.map((f, k) => (
              <li key={k} className="flex flex-col gap-0.5 border-b py-2 text-sm last:border-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5">
                    <span className="font-medium">{f.pedido_id}</span>
                    <span className="text-muted-foreground">· {ESTRATEGIA[f.estrategia ?? ""] ?? f.estrategia}</span>
                    {f.ejemplo ? <Etiqueta>ejemplo</Etiqueta> : <Etiqueta tono="azul">este pedido</Etiqueta>}
                  </span>
                  <span className="tabular-nums">
                    {porc(f.concesion_simulada_pct)} simulado · {porc(f.concesion_real_pct)} real
                    {f.desvio_pp !== null && <span className="ml-1.5 text-muted-foreground">({pp(f.desvio_pp)})</span>}
                  </span>
                </div>
                {f.nota && <span className="text-xs text-muted-foreground">{f.nota}</span>}
              </li>
            ))}
          </ul>
        )}
        {conEjemplo && <DatosEjemplo className="mt-3">Las negociaciones anteriores a esta demo son ilustrativas.</DatosEjemplo>}
      </CardContent>
    </Card>
  );
}

const porc = (v: number | null) => (v === null ? "—" : `${formatNumero(v, Number.isInteger(v) ? 0 : 1)} %`);
