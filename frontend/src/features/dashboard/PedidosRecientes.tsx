import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Etiqueta, type Tono } from "@/components/comunes";
import { fechaHora } from "./formato";
import type { PedidoReciente } from "./types";

const ORIGENES: Record<string, string> = {
  solicitud_interna: "Solicitud interna",
  stock_minimo: "Stock mínimo",
  zafra: "Zafra",
  nota_de_voz: "Nota de voz",
  email: "Email",
};

function legible(valor: string | null): string {
  if (!valor) return "—";
  const t = ORIGENES[valor] ?? valor.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function tonoEstado(estado: string | null): Tono {
  if (!estado) return "neutro";
  if (/incomplet|pendiente_de_aprob|aprobaci/.test(estado)) return "ambar";
  if (/negoci|cotiz/.test(estado)) return "azul";
  if (/recibid|cerrad|aprobado/.test(estado)) return "verde";
  if (/cancel/.test(estado)) return "rojo";
  return "neutro";
}

export function PedidosRecientes({ pedidos }: { pedidos: PedidoReciente[] }) {
  return (
    <section aria-label="Pedidos recientes">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-base font-medium">Pedidos recientes</h2>
        <Button asChild variant="outline" size="sm">
          <Link to="/pedidos">Ver todos</Link>
        </Button>
      </div>
      {pedidos.length === 0 ? (
        <p className="rounded-xl border bg-background p-4 text-sm text-muted-foreground">Todavía no hay pedidos.</p>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-background">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pedido</TableHead>
                <TableHead>Cliente interno</TableHead>
                <TableHead>Origen</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Actualizado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pedidos.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-medium">
                    <Link to={`/pedidos/${p.id}`} className="underline-offset-4 hover:underline">
                      {p.titulo}
                    </Link>
                  </TableCell>
                  <TableCell>{legible(p.cliente)}</TableCell>
                  <TableCell>{legible(p.origen)}</TableCell>
                  <TableCell>{p.estado ? <Etiqueta tono={tonoEstado(p.estado)}>{legible(p.estado)}</Etiqueta> : "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{p.actualizado ? fechaHora(p.actualizado) : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  );
}
