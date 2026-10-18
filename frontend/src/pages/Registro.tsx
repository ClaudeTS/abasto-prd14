// Registro de usuarios (RF-21): la pantalla existe pero no está operativa en el MVP.
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { InfoIcon } from "lucide-react";
import { MODO } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import * as api from "@/features/reglas/api";
import { Input, Label, Select } from "@/features/reglas/campos";
import { mensajeError } from "@/lib/errores";
import { MarcoIngreso } from "./Login";

const NO_DISPONIBLE = "El registro todavía no está disponible";

export default function Registro() {
  const [datos, setDatos] = useState({ nombre: "", email: "", cliente_interno: "personal", contrasena: "" });
  const [enviando, setEnviando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const campo = (k: keyof typeof datos) => ({
    id: `registro-${k}`,
    value: datos[k],
    onChange: (e: { target: { value: string } }) => setDatos((d) => ({ ...d, [k]: e.target.value })),
  });

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    try {
      if (MODO === "mock") throw new Error(NO_DISPONIBLE);
      await api.registro(datos);
      setAviso(NO_DISPONIBLE);
    } catch (err) {
      setAviso(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <MarcoIngreso>
      <form onSubmit={enviar} className="flex w-full max-w-sm flex-col gap-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Creá tu cuenta</h1>
            <Badge variant="secondary">Próximamente</Badge>
          </div>
          <p className="mt-1 text-muted-foreground">
            Por ahora los usuarios los da de alta el administrador de compras. Esta pantalla todavía no crea cuentas.
          </p>
        </div>
        {aviso && (
          <div role="status" className="flex items-start gap-2 rounded-md border bg-muted px-3 py-2 text-sm">
            <InfoIcon className="mt-0.5 size-4 shrink-0" /> {aviso}. Pedile acceso al administrador de compras.
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="registro-nombre">Nombre</Label>
          <Input className="h-10" autoComplete="name" {...campo("nombre")} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="registro-email">Email de la empresa</Label>
          <Input className="h-10" type="email" autoComplete="email" placeholder="nombre@tecnova.com.uy" {...campo("email")} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="registro-cliente_interno">Área</Label>
          <Select className="h-10" {...campo("cliente_interno")}>
            <option value="personal">Personal (consumo interno)</option>
            <option value="ventas">Ventas (productos para vender)</option>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="registro-contrasena">Contraseña</Label>
          <Input className="h-10" type="password" autoComplete="new-password" {...campo("contrasena")} />
        </div>
        <Button type="submit" size="lg" className="h-10 w-full" disabled={enviando}>
          {enviando && <Spinner />} Crear cuenta
        </Button>
        <p className="text-center text-muted-foreground">
          ¿Ya tenés cuenta?{" "}
          <Link to="/login" className="text-foreground underline underline-offset-4">
            Ingresá
          </Link>
        </p>
      </form>
    </MarcoIngreso>
  );
}
