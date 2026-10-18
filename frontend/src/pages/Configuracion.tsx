// Panel de configuración (RF-20) con usuarios y roles (RF-21) y estado de canales. Mockup: Configuracion.
import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2Icon, LockIcon } from "lucide-react";
import { MODO } from "@/api";
import { ErrorBanner, Etiqueta, type Tono } from "@/components/comunes";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import * as api from "@/features/reglas/api";
import { aNumero, aTexto } from "@/features/reglas/borrador";
import { Campo, Input, InputNumero, Select } from "@/features/reglas/campos";
import { fechaHora } from "@/features/reglas/panel";
import type { CambioConfiguracion, CambioRegla, Configuracion as Config, UsuarioListado } from "@/features/reglas/types";
import { useAuth } from "@/lib/auth";
import { ApiError, mensajeError } from "@/lib/errores";
import { fechaCorta } from "@/lib/format";
import type { ConfigLlamadas } from "@/types";

interface Borrador {
  tipo_cambio_usd: string;
  fecha_tipo_cambio: string;
  iva_pct: string;
  vigencia_dias_default: string;
  moneda_base: Config["moneda_base"];
}

const desde = (c: Config): Borrador => ({
  tipo_cambio_usd: aTexto(c.tipo_cambio_usd),
  fecha_tipo_cambio: c.fecha_tipo_cambio ?? "",
  iva_pct: aTexto(Math.round(c.iva * 10000) / 100),
  vigencia_dias_default: aTexto(c.vigencia_dias_default),
  moneda_base: c.moneda_base,
});

const fechaLarga = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;

export default function Configuracion() {
  const { esAdmin } = useAuth();
  const [config, setConfig] = useState<Config | null>(null);
  const [borrador, setBorrador] = useState<Borrador | null>(null);
  const [historial, setHistorial] = useState<CambioRegla[]>([]);
  const [usuarios, setUsuarios] = useState<UsuarioListado[] | null>(null);
  const [llamadas, setLlamadas] = useState<ConfigLlamadas | null>(null);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [guardando, setGuardando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      const [c, h] = await Promise.all([api.verConfiguracion(), api.historialConfiguracion()]);
      setConfig(c);
      setBorrador(desde(c));
      setHistorial(h);
      setError(null);
    } catch (e) {
      setError(mensajeError(e));
    }
    api.listarUsuarios().then(setUsuarios).catch(() => setUsuarios([]));
    api.configLlamadas().then(setLlamadas).catch(() => setLlamadas(null));
  }, []);

  useEffect(() => {
    if (MODO !== "mock") cargar();
  }, [cargar]);

  const { cambio, locales } = useMemo(() => {
    const cambio: CambioConfiguracion = {};
    const locales: Record<string, string> = {};
    if (!borrador || !config) return { cambio, locales };
    const tc = aNumero(borrador.tipo_cambio_usd);
    if (tc === null || tc === "invalido") locales.tipo_cambio_usd = "Tiene que ser un número.";
    else if (tc !== config.tipo_cambio_usd) cambio.tipo_cambio_usd = tc;
    const iva = aNumero(borrador.iva_pct);
    if (iva === null || iva === "invalido") locales.iva = "Tiene que ser un número.";
    else if (Math.abs(iva / 100 - config.iva) > 1e-9) cambio.iva = Math.round(iva * 100) / 10000;
    const vig = aNumero(borrador.vigencia_dias_default);
    if (vig === null || vig === "invalido" || !Number.isInteger(vig)) locales.vigencia_dias_default = "Tiene que ser un número entero.";
    else if (vig !== config.vigencia_dias_default) cambio.vigencia_dias_default = vig;
    if (borrador.moneda_base !== config.moneda_base) cambio.moneda_base = borrador.moneda_base;
    if ((borrador.fecha_tipo_cambio || null) !== config.fecha_tipo_cambio) cambio.fecha_tipo_cambio = borrador.fecha_tipo_cambio || null;
    return { cambio, locales };
  }, [borrador, config]);
  const hayCambios = Object.keys(cambio).length > 0;
  const todos = { ...errores, ...locales };
  const set = (k: keyof Borrador, v: string) => {
    setAviso(null);
    setErrores({});
    setBorrador((b) => (b ? { ...b, [k]: v } : b));
  };

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      const c = await api.cambiarConfiguracion({ ...cambio, motivo: motivo.trim() || undefined });
      setConfig(c);
      setBorrador(desde(c));
      setHistorial(await api.historialConfiguracion());
      setMotivo("");
      setAviso("Configuración guardada. Aplica a las comparaciones nuevas.");
    } catch (e) {
      setError(mensajeError(e));
      if (e instanceof ApiError && e.detalle && typeof e.detalle === "object") setErrores(e.detalle as Record<string, string>);
    } finally {
      setGuardando(false);
    }
  };

  const soloLectura = !esAdmin;
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 flex-[1_1_20rem] space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Configuración</h1>
            <Badge variant="secondary">Solo el administrador edita</Badge>
          </div>
          <p className="text-muted-foreground">Parámetros generales que usa el agente para comparar cotizaciones.</p>
        </div>
        {esAdmin && (
          <div className="flex gap-2">
            <Button variant="outline" disabled={!hayCambios || guardando} onClick={() => config && setBorrador(desde(config))}>
              Descartar
            </Button>
            <Button disabled={!hayCambios || Object.keys(locales).length > 0 || guardando} onClick={guardar}>
              {guardando && <Spinner />} Guardar
            </Button>
          </div>
        )}
      </div>

      {MODO === "mock" && (
        <Alert>
          <AlertTitle>Esta pantalla necesita el backend</AlertTitle>
          <AlertDescription>En modo mock no hay configuración guardada.</AlertDescription>
        </Alert>
      )}
      {!esAdmin && (
        <Alert>
          <LockIcon />
          <AlertTitle>Modo consulta</AlertTitle>
          <AlertDescription>Ves la configuración, pero solo el administrador de compras puede cambiarla.</AlertDescription>
        </Alert>
      )}
      {error && <ErrorBanner mensaje={error} onReintentar={config ? undefined : cargar} />}
      {MODO !== "mock" && !config && !error && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner /> Cargando…
        </div>
      )}

      {config && borrador && (
        <Card>
          <CardHeader>
            <CardTitle>Parámetros generales</CardTitle>
            <CardDescription>Los cambios aplican a las comparaciones nuevas: cotizaciones que se lean y planes que se armen después.</CardDescription>
          </CardHeader>
          <CardContent className="gap-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Campo
                id="tc"
                etiqueta="Tipo de cambio USD / UYU"
                error={todos.tipo_cambio_usd}
                ayuda={config.fecha_tipo_cambio ? `Cargado a mano · vigente desde ${fechaLarga(config.fecha_tipo_cambio)}` : "Cargado a mano · sin fecha"}
              >
                <InputNumero id="tc" valor={borrador.tipo_cambio_usd} onCambio={(v) => set("tipo_cambio_usd", v)} prefijo="$" disabled={soloLectura} error={todos.tipo_cambio_usd} />
              </Campo>
              <Campo id="iva" etiqueta="Tasa de IVA" error={todos.iva} ayuda="Uruguay · las comparaciones se hacen sin IVA">
                <InputNumero id="iva" valor={borrador.iva_pct} onCambio={(v) => set("iva_pct", v)} sufijo="%" disabled={soloLectura} error={todos.iva} />
              </Campo>
              <Campo id="vigencia" etiqueta="Vigencia por defecto" error={todos.vigencia_dias_default} ayuda="De las cotizaciones, si el proveedor no la indica">
                <InputNumero id="vigencia" valor={borrador.vigencia_dias_default} onCambio={(v) => set("vigencia_dias_default", v)} sufijo="días" disabled={soloLectura} error={todos.vigencia_dias_default} />
              </Campo>
              <Campo id="moneda-base" etiqueta="Moneda base" error={todos.moneda_base} ayuda="Monedas habilitadas: UYU y USD">
                <Select id="moneda-base" value={borrador.moneda_base} onChange={(e) => set("moneda_base", e.target.value)} disabled={soloLectura}>
                  <option value="UYU">Pesos uruguayos (UYU)</option>
                  <option value="USD" disabled>
                    Dólares (USD) · próximamente
                  </option>
                </Select>
              </Campo>
            </div>
            {esAdmin && (
              <div className="grid gap-4 sm:grid-cols-[200px_1fr]">
                <Campo id="fecha-tc" etiqueta="Fecha del tipo de cambio" ayuda="Si la dejás igual y cambiás el tipo, se pone la de hoy">
                  <Input id="fecha-tc" type="date" value={borrador.fecha_tipo_cambio} onChange={(e) => set("fecha_tipo_cambio", e.target.value)} />
                </Campo>
                <Campo id="motivo-config" etiqueta="Motivo (opcional)" ayuda="Queda en el historial">
                  <Input id="motivo-config" placeholder="Ej. cotización del BCU del día" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
                </Campo>
              </div>
            )}
            {aviso && (
              <p role="status" className="flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-400">
                <CheckCircle2Icon className="size-4" /> {aviso}
              </p>
            )}
            {historial.length > 0 && (
              <div className="border-t pt-3">
                <div className="mb-1 text-sm font-medium">Últimos cambios</div>
                <ul className="space-y-1 text-sm">
                  {historial.slice(0, 5).map((c) => (
                    <li key={c.id}>
                      <span className="font-medium">
                        {c.etiqueta}: {c.texto_anterior} → {c.texto_nuevo}
                      </span>{" "}
                      <span className="text-muted-foreground">
                        · {c.usuario} · {fechaHora(c.fecha)} · “{c.motivo}”
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {MODO !== "mock" && <Usuarios usuarios={usuarios} />}
      {MODO !== "mock" && <Integraciones llamadas={llamadas} />}
    </div>
  );
}

function Usuarios({ usuarios }: { usuarios: UsuarioListado[] | null }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Usuarios y roles <Etiqueta tono="ejemplo">Datos de ejemplo</Etiqueta>
        </CardTitle>
        <CardDescription>Los roles solo limitan la edición de reglas y configuración.</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" disabled title="Próximamente">
            Invitar usuario
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        {!usuarios ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Spinner /> Cargando…
          </div>
        ) : (
          <div className="rounded-lg border">
            <Table className="min-w-[560px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Usuario</TableHead>
                  <TableHead>Cliente interno</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead>Último ingreso</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usuarios.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="font-medium">{u.nombre}</div>
                      <div className="text-xs text-muted-foreground">{u.email}</div>
                    </TableCell>
                    <TableCell>{u.cliente_interno === "ventas" ? "Ventas" : "Personal"}</TableCell>
                    <TableCell>{u.rol === "administrador" ? <Badge>Administrador</Badge> : <Badge variant="outline">Consulta</Badge>}</TableCell>
                    <TableCell className="text-muted-foreground">{u.ultimo_ingreso ? ultimoIngreso(u.ultimo_ingreso) : "nunca"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ultimoIngreso(iso: string): string {
  const d = new Date(iso);
  const hoy = new Date();
  const hh = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (d.toDateString() === hoy.toDateString()) return `hoy ${hh}`;
  const ayer = new Date(hoy);
  ayer.setDate(hoy.getDate() - 1);
  if (d.toDateString() === ayer.toDateString()) return `ayer ${hh}`;
  return fechaCorta(iso);
}

function Integraciones({ llamadas }: { llamadas: ConfigLlamadas | null }) {
  const estadoLlamadas: [string, Tono] = !llamadas
    ? ["Sin datos", "neutro"]
    : llamadas.modo === "simulada"
      ? ["Simuladas", "ambar"]
      : llamadas.lista
        ? ["Conectado", "verde"]
        : ["Falta configurar", "rojo"];
  const filas: { titulo: string; detalle: string; estado: [string, Tono] }[] = [
    {
      titulo: "Llamadas · Twilio + ElevenLabs",
      detalle:
        "Se presenta como IA y avisa que graba · reintento a 30 min · audio 60 días, transcripción siempre" +
        (llamadas?.modo === "real" && !llamadas.lista && llamadas.faltan.length ? ` · falta: ${llamadas.faltan.join(", ")}` : ""),
      estado: estadoLlamadas,
    },
    { titulo: "WhatsApp", detalle: "Piloto simulado en la interfaz, sin la API oficial", estado: ["Simulado", "ambar"] },
    { titulo: "Email", detalle: "Solicitudes internas, cotizaciones y último paso de la secuencia de contacto · en la demo no sale", estado: ["Simulado", "ambar"] },
    {
      titulo: "ERP / base de datos",
      detalle: "Consulta de stock una vez por día, al cierre de la jornada · en la demo, inventario de ejemplo",
      estado: ["Próxima consulta 18:00", "azul"],
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Canales e integraciones</CardTitle>
      </CardHeader>
      <CardContent className="gap-0">
        <ul className="divide-y">
          {filas.map((f) => (
            <li key={f.titulo} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="font-medium">{f.titulo}</div>
                <div className="text-sm text-muted-foreground">{f.detalle}</div>
              </div>
              <Etiqueta tono={f.estado[1]}>{f.estado[0]}</Etiqueta>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
