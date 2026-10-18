import type { ReactNode } from "react";
import { CheckIcon, LightbulbIcon } from "lucide-react";
import { formatNumero } from "@/lib/format";
import { proveedor } from "@/lib/proveedores";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Avatar, Encabezado } from "@/components/comunes";

// Pantallas estáticas de las capas 2, 3, 6 y 7 (fuera del MVP). Todo número acá es ilustrativo y
// está marcado como tal, salvo la confiabilidad de Ofisillas (dato seedeado).

const CAPAS = [
  { n: 1, nombre: "Percepción", detalle: "Entiende texto, PDF, foto y audio", hecha: true },
  { n: 2, nombre: "Perfil del proveedor", detalle: "Aprende cuánto cede y cuándo sube", hecha: false },
  { n: 3, nombre: "Predicción", detalle: "Consumo: ya en Inventario. Precios: próximamente", hecha: false, parcial: true },
  { n: 4, nombre: "Optimización", detalle: "Solver MILP", hecha: true },
  { n: 5, nombre: "Negociación ensayada", detalle: "Gemelo digital del proveedor", hecha: true },
  { n: 6, nombre: "Índice de mercado", detalle: "Precios anonimizados entre empresas", hecha: false },
  { n: 7, nombre: "Agente a agente", detalle: "Proveedores conectan su agente", hecha: false },
];

export default function Vision() {
  return (
    <div className="space-y-8">
      <Encabezado
        titulo="Hacia dónde va Abasto"
        bajada="Lo que viste son 3 de 7 capas, y la mitad de otra: el pronóstico de consumo ya funciona. Con cada compra Abasto aprende cómo se comporta cada proveedor; con muchas empresas, arma un índice de precios que nadie puede copiar sin los datos."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-7">
        {CAPAS.map((c) => (
          <div
            key={c.n}
            className={cn(
              "flex flex-col gap-1 rounded-xl p-3 text-sm",
              c.hecha
                ? "bg-primary text-primary-foreground"
                : "parcial" in c
                  ? "border-2 border-primary/60 text-muted-foreground"
                  : "border border-dashed text-muted-foreground",
            )}
          >
            <span className="text-xs opacity-70">Capa {c.n}</span>
            <span className={cn("leading-tight font-medium", !c.hecha && "text-foreground")}>{c.nombre}</span>
            <span className="text-xs opacity-80">{c.detalle}</span>
            <span className="mt-auto flex items-center gap-1 pt-2 text-xs font-medium">
              {c.hecha ? (
                <>
                  <CheckIcon className="size-3" /> En la demo
                </>
              ) : "parcial" in c ? (
                "A medias"
              ) : (
                "Próximamente"
              )}
            </span>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <PerfilProveedor />
        <Prediccion />
        <IndiceMercado />
      </div>
    </div>
  );
}

function Tarjeta({ capa, titulo, children }: { capa: number; titulo: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>Capa {capa}</CardDescription>
        <CardTitle className="text-lg">{titulo}</CardTitle>
        <CardAction>
          <Badge variant="secondary">Próximamente</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex-1 gap-4">{children}</CardContent>
      <CardFooter className="border-t text-xs text-muted-foreground">Datos ilustrativos · pantalla de diseño, no conectada</CardFooter>
    </Card>
  );
}

function PerfilProveedor() {
  const ofisillas = proveedor("ofisillas");
  const argumentos = [
    { nombre: "Compra futura de puestos", pct: 5.1 },
    { nombre: "Pago contado", pct: 2.8 },
    { nombre: "Competencia", pct: 0.3 },
  ];
  const max = 6;
  return (
    <Tarjeta capa={2} titulo="Perfil del proveedor">
      <div className="flex items-center gap-3">
        <Avatar proveedorId="ofisillas" />
        <div>
          <p className="font-medium">{ofisillas.nombre}</p>
          <p className="text-muted-foreground">aprendido de 12 negociaciones</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Cede en promedio</p>
          <p className="text-2xl font-semibold tabular-nums">4,2 %</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Cumple entregas</p>
          <p className="text-2xl font-semibold tabular-nums">{Math.round(ofisillas.confiabilidad * 100)} %</p>
        </div>
      </div>
      <div className="space-y-3">
        <p className="font-medium">Concesión promedio por argumento</p>
        {argumentos.map((a) => (
          <div key={a.nombre} className="space-y-1.5" title={`${a.nombre}: ${formatNumero(a.pct, 1)} % de concesión promedio`}>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{a.nombre}</span>
              <span className="font-medium tabular-nums">{formatNumero(a.pct, 1)} %</span>
            </div>
            <Progress value={Math.max(2, (a.pct / max) * 100)} />
          </div>
        ))}
      </div>
      <p className="rounded-lg bg-muted p-3 text-muted-foreground">
        “Con Ofisillas no sirve mencionar a la competencia: cede por volumen comprometido.”
      </p>
    </Tarjeta>
  );
}

function Prediccion() {
  const reales = [88, 89, 91, 92, 93, 95];
  const prevision = [95, 97, 99];
  const meses = ["may", "jun", "jul", "ago", "set", "oct", "nov", "dic"];
  const W = 300;
  const H = 150;
  const pad = { l: 30, r: 10, t: 12, b: 22 };
  const min = 85;
  const max = 101;
  const x = (i: number) => pad.l + (i / (meses.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min)) * (H - pad.t - pad.b);
  const linea = (vals: number[], desde: number) => vals.map((v, i) => `${i ? "L" : "M"}${x(desde + i)},${y(v)}`).join(" ");

  return (
    <Tarjeta capa={3} titulo="Predicción de precios y consumo">
      <div>
        <p className="font-medium">Tóner HP 85A · precio del importador (USD)</p>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="mt-2 w-full text-foreground"
          role="img"
          aria-label="Precio del tóner en dólares, de mayo a octubre, y previsión hasta diciembre"
        >
          {[88, 94, 100].map((v) => (
            <g key={v}>
              <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="stroke-border" strokeWidth="1" />
              <text x={pad.l - 6} y={y(v) + 3} textAnchor="end" fontSize="9" className="fill-muted-foreground">
                {v}
              </text>
            </g>
          ))}
          {meses.map((m, i) => (
            <text key={m} x={x(i)} y={H - 6} textAnchor="middle" fontSize="9" className="fill-muted-foreground">
              {m}
            </text>
          ))}
          <path d={linea(prevision, 5)} fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" opacity="0.5" />
          <path d={linea(reales, 0)} fill="none" stroke="currentColor" strokeWidth="2" />
          {reales.map((v, i) => (
            <circle key={i} cx={x(i)} cy={y(v)} r="4" fill="currentColor" className="stroke-background" strokeWidth="2">
              <title>{`${meses[i]}: USD ${v}`}</title>
            </circle>
          ))}
          {prevision.slice(1).map((v, i) => (
            <circle key={i} cx={x(6 + i)} cy={y(v)} r="4" className="fill-background" stroke="currentColor" strokeWidth="2">
              <title>{`${meses[6 + i]} (previsión): USD ${v}`}</title>
            </circle>
          ))}
        </svg>
        <p className="text-xs text-muted-foreground">Línea punteada: previsión según el dólar y el historial del proveedor.</p>
      </div>
      <div className="flex gap-2 rounded-lg border p-3">
        <LightbulbIcon className="mt-0.5 size-4 shrink-0" />
        <div>
          <p className="font-medium">Comprá el tóner del trimestre ahora</p>
          <p className="text-muted-foreground">El importador sube cuando sube el dólar. Adelantar 16 unidades evita ~4 % de aumento.</p>
        </div>
      </div>
      <p className="text-muted-foreground">
        Consumo previsto de resmas en noviembre: <span className="font-medium text-foreground">160</span> (puestos nuevos + cierre
        de año).
      </p>
    </Tarjeta>
  );
}

function IndiceMercado() {
  const p25 = 189;
  const mediana = 206;
  const p75 = 228;
  const vos = 235;
  const min = 170;
  const max = 250;
  const pos = (v: number) => `${((v - min) / (max - min)) * 100}%`;
  return (
    <Tarjeta capa={6} titulo="Índice de precios de mercado">
      <div>
        <p className="font-medium">Resma A4 75 g · lo que pagan 140 empresas</p>
        <p className="mt-3 text-5xl font-semibold tracking-tight tabular-nums">+14 %</p>
        <p className="text-muted-foreground">sobre la mediana, comprándole al habitual</p>
      </div>

      <div
        className="relative mt-4 h-14"
        role="img"
        aria-label={`Mediana $ ${mediana}, rango típico $ ${p25} a $ ${p75}, tu precio $ ${vos}`}
      >
        <div className="absolute inset-x-0 top-6 h-1.5 rounded-full bg-muted" />
        <div
          className="absolute top-5 h-3.5 rounded-full bg-muted-foreground/30"
          style={{ left: pos(p25), width: `calc(${pos(p75)} - ${pos(p25)})` }}
          title={`Rango típico (p25–p75): $ ${p25} a $ ${p75}`}
        />
        <div className="absolute top-3 h-7 w-0.5 bg-foreground" style={{ left: pos(mediana) }} title={`Mediana: $ ${mediana}`} />
        <span className="absolute -top-2 -translate-x-1/2 text-xs whitespace-nowrap text-muted-foreground" style={{ left: pos(mediana) }}>
          mediana $ {mediana}
        </span>
        <div
          className="absolute top-4 size-4 -translate-x-1/2 rounded-full border-2 border-background bg-destructive shadow"
          style={{ left: pos(vos) }}
          title={`Tu precio: $ ${vos}`}
        />
        <span className="absolute top-9 -translate-x-1/2 text-xs font-medium whitespace-nowrap" style={{ left: pos(vos) }}>
          vos $ {vos}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">Barra gris: rango típico (p25–p75). Precios sin IVA, por resma.</p>

      <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
        <li>Se construye solo con precios anonimizados y agregados.</li>
        <li>Cada empresa elige participar a cambio de ver el índice.</li>
      </ul>
    </Tarjeta>
  );
}
