import sim from "../../../data/proveedores_sim.json";
import { formatNumero } from "../lib/format";
import type {
  EstrategiaNegociacion,
  NombreEstrategia,
  TurnoNegociacion,
} from "../types";

// Ensayo de negociación simulado (lo que devolvería negociacion.py). Para Ofisillas, el caso del
// guion de demo, las transcripciones están escritas a mano siguiendo su perfil de concesión
// (insensible a competencia, cede por contado y más por volumen). Para el resto se arman con
// plantillas a partir de "sensible_a" / "insensible_a" de data/proveedores_sim.json.

type Base = Omit<EstrategiaNegociacion, "ganancia_esperada_uyu">;

const OFISILLAS: Base[] = [
  {
    nombre: "competencia",
    descripcion: "Mencionar la mejor cotización alternativa real: Mueblería Rivera a $ 9.800 + IVA.",
    concesion_obtenida_pct: 0,
    riesgo: "medio",
    transcripcion: [
      {
        rol: "abasto",
        texto:
          "Hola! Gracias por la cotización. Tenemos otra propuesta de Mueblería Rivera a $9.800 + IVA por silla. ¿Podés acercarte a ese precio para las 15?",
      },
      {
        rol: "proveedor",
        texto:
          "Buenas! Conozco a Rivera, trabajan bien, pero fabrican por lote y te piden mínimo 20. Por 15 sillas no te lo hacen. La Prime a $10.900 ya está ajustada.",
      },
      { rol: "abasto", texto: "Entiendo. ¿Hay algo de margen si cerramos esta semana?" },
      {
        rol: "proveedor",
        texto: "Te sostengo el precio 15 días, pero bajarlo por eso no puedo.",
      },
    ],
  },
  {
    nombre: "volumen",
    descripcion: "Comprometer el equipamiento de los próximos puestos a cambio de mejor precio.",
    concesion_obtenida_pct: 5,
    riesgo: "bajo",
    transcripcion: [
      {
        rol: "abasto",
        texto:
          "Hola! Estas 15 sillas son para los puestos nuevos y el próximo trimestre vamos a equipar 10 puestos más. Si cerramos con ustedes todo ese equipamiento, ¿qué precio nos hacés?",
      },
      {
        rol: "proveedor",
        texto: "Buenas! Eso me interesa. Si me asegurás los próximos puestos te hago un 4 % en estas 15.",
      },
      { rol: "abasto", texto: "Buenísimo. Si lo dejamos por escrito, ¿llegás a un 6 %?" },
      {
        rol: "proveedor",
        texto:
          "6 % no llego, pero 5 % sí: $10.355 + IVA c/u, y te mantengo ese precio para los próximos puestos.",
      },
    ],
  },
  {
    nombre: "plazo",
    descripcion: "Ofrecer pago contado contra entrega en vez de 30 días.",
    concesion_obtenida_pct: 3,
    riesgo: "bajo",
    transcripcion: [
      {
        rol: "abasto",
        texto:
          "Hola! Si en vez de a 30 días te pagamos contado contra entrega, ¿podés mejorar el precio de las 15 sillas?",
      },
      { rol: "proveedor", texto: "Buenas! Por contado te puedo hacer un 2 %, quedaría en $10.680 + IVA." },
      { rol: "abasto", texto: "¿Llegás a un 4 %? Es pago el mismo día de la entrega." },
      { rol: "proveedor", texto: "Te hago 3 %: $10.573 + IVA c/u, contado contra entrega. Más no puedo." },
    ],
  },
];

const MENSAJE_OFISILLAS =
  "Hola! Gracias por la cotización de las sillas Prime. Estas 15 son para los puestos nuevos y el próximo trimestre vamos a equipar más puestos. Si cerramos con ustedes todo ese equipamiento, ¿nos dejás la silla en $10.355 + IVA c/u y nos mantenés ese precio para las próximas compras?";

const CLAVES: Record<NombreEstrategia, string[]> = {
  competencia: ["competidor", "competencia"],
  volumen: ["recurrente", "mensual", "futura", "puestos", "lote", "sumar"],
  plazo: ["contado", "anticipado", "anticipo", "cierre inmediato"],
};

const DESCRIPCIONES: Record<NombreEstrategia, string> = {
  competencia: "Mencionar con nombre y precio la mejor cotización alternativa real.",
  volumen: "Comprometer compras futuras (pedido mensual o más puestos) a cambio de mejor precio.",
  plazo: "Ofrecer pago contado o anticipado a cambio de descuento.",
};

export interface Alternativa {
  proveedor: string;
  producto: string;
  precio: number;
}

function generica(
  nombre: NombreEstrategia,
  proveedorId: string,
  alternativa: Alternativa | null,
): Base {
  const prov = sim.proveedores.find((p) => p.publico.id === proveedorId)!;
  const sensible = prov.privado.sensible_a.join(" ").toLowerCase();
  const insensible = prov.privado.insensible_a.join(" ").toLowerCase();
  const toca = CLAVES[nombre].some((k) => sensible.includes(k));
  const ofende =
    !toca && CLAVES[nombre].some((k) => insensible.includes(k)) && insensible.includes("ofende");
  const pct = toca ? Math.round(Math.min(prov.privado.precio_piso_pct * 0.6, 4) * 10) / 10 : 0;

  const pedido: Record<NombreEstrategia, string> = {
    competencia: alternativa
      ? `Hola! Tenemos ${alternativa.producto} de ${alternativa.proveedor} a $${formatNumero(alternativa.precio)} sin IVA. ¿Podés mejorar tu precio?`
      : "Hola! Estamos comparando varias cotizaciones. ¿Podés mejorar tu precio?",
    volumen:
      "Hola! Si te aseguramos el pedido todos los meses durante el próximo semestre, ¿qué precio nos podés hacer?",
    plazo: "Hola! Si te pagamos contado contra entrega, ¿podés hacernos un descuento?",
  };
  const respuesta = toca
    ? `Dale, por eso te puedo hacer un ${formatNumero(pct, 1)} %.`
    : ofende
      ? "Mirá, si ya tenés otro precio comprale a ese. Yo te paso el precio que es."
      : "Te entiendo, pero el precio ya está bastante ajustado.";

  const transcripcion: TurnoNegociacion[] = [
    { rol: "abasto", texto: pedido[nombre] },
    { rol: "proveedor", texto: respuesta },
    {
      rol: "abasto",
      texto: toca ? "Gracias, ¿lo podemos dejar así para este pedido?" : "¿Habría algún margen si cerramos hoy?",
    },
    {
      rol: "proveedor",
      texto: toca ? "Sí, lo dejamos así." : ofende ? "No, gracias." : "Por ahora no, el precio queda como está.",
    },
  ];
  return {
    nombre,
    descripcion: DESCRIPCIONES[nombre],
    concesion_obtenida_pct: pct,
    riesgo: ofende ? "alto" : toca ? "bajo" : "medio",
    transcripcion,
  };
}

export function ensayarEstrategias(proveedorId: string, alternativa: Alternativa | null): Base[] {
  if (proveedorId === "ofisillas") return OFISILLAS;
  return (["competencia", "volumen", "plazo"] as NombreEstrategia[]).map((n) =>
    generica(n, proveedorId, alternativa),
  );
}

export function mensajePropuesto(
  proveedorId: string,
  elegida: Base,
  base: number,
  alternativa: Alternativa | null,
): string {
  if (proveedorId === "ofisillas" && elegida.nombre === "volumen") return MENSAJE_OFISILLAS;
  const pct = formatNumero(elegida.concesion_obtenida_pct, 1);
  const total = formatNumero(Math.round(base));
  const argumento: Record<NombreEstrategia, string> = {
    competencia: alternativa
      ? `Tenemos ${alternativa.producto} de ${alternativa.proveedor} a $${formatNumero(alternativa.precio)} sin IVA, pero nos gusta trabajar con ustedes.`
      : "Estamos comparando cotizaciones y nos gustaría seguir con ustedes.",
    volumen: "Queremos asegurarte el pedido todos los meses durante el próximo semestre.",
    plazo: "Te podemos pagar contado contra entrega en vez de a plazo.",
  };
  return `Hola! Gracias por la cotización (unos $${total} sin IVA en este pedido). ${argumento[elegida.nombre]} ¿Nos podés hacer un ${pct} % sobre lo cotizado?`;
}
