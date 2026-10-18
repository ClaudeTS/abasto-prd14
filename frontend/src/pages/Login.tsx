// Ingreso con usuario y contraseña (RF-21). Mockup: Login. Fuera del marco de la app.
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { AlertCircleIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Input, Label } from "@/features/reglas/campos";
import { useAuth } from "@/lib/auth";
import { mensajeError } from "@/lib/errores";

/** Columna oscura de presentación, compartida con el registro. */
export function MarcoIngreso({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-svh flex-col bg-muted/30 md:flex-row">
      <section
        aria-label="Presentación"
        className="flex flex-col justify-between gap-10 bg-primary p-8 text-primary-foreground md:min-h-svh md:flex-1 md:p-12"
      >
        <div className="flex items-center gap-2.5 text-base font-semibold">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary-foreground text-sm font-bold text-primary">A</span>
          Abasto
        </div>
        <div className="max-w-md">
          <p className="text-3xl leading-tight font-semibold tracking-tight">Tu director de compras con IA.</p>
          <p className="mt-3 text-primary-foreground/75">
            Recibe los pedidos, cotiza con tus proveedores, compara en una base común y negocia por vos. Vos aprobás lo que
            importa.
          </p>
        </div>
        <p className="text-sm text-primary-foreground/60">Tecnova S.A. · build 101 AI Hackathon</p>
      </section>
      <section aria-label="Ingreso" className="flex flex-1 items-center justify-center px-6 py-12">
        {children}
      </section>
    </div>
  );
}

const DEMO = { usuario: "lucia@tecnova.com.uy", contrasena: "abasto2026" };

export default function Login() {
  const { usuario, cargando, ingresar } = useAuth();
  const navigate = useNavigate();
  const ubicacion = useLocation();
  const desde = (ubicacion.state as { desde?: string } | null)?.desde;
  const destino = desde && desde !== "/login" && desde !== "/registro" ? desde : "/inicio";
  const [u, setU] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!cargando && usuario) return <Navigate to={destino} replace />;

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!u.trim() || !contrasena) {
      setError("Completá el usuario y la contraseña.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await ingresar(u.trim(), contrasena);
      navigate(destino, { replace: true });
    } catch (err) {
      setError(mensajeError(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <MarcoIngreso>
      <form onSubmit={enviar} className="flex w-full max-w-sm flex-col gap-5" noValidate>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ingresá a tu cuenta</h1>
          <p className="mt-1 text-muted-foreground">Usá tu usuario y contraseña de la empresa.</p>
        </div>
        {error && (
          <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" /> {error}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="usuario">Usuario</Label>
          <Input
            id="usuario"
            className="h-10"
            autoComplete="username"
            placeholder="lucia@tecnova.com.uy"
            value={u}
            onChange={(e) => setU(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label htmlFor="contrasena">Contraseña</Label>
            <span className="text-sm text-muted-foreground" title="Pedísela al administrador de compras">
              ¿La olvidaste?
            </span>
          </div>
          <Input
            id="contrasena"
            type="password"
            className="h-10"
            autoComplete="current-password"
            value={contrasena}
            onChange={(e) => setContrasena(e.target.value)}
          />
        </div>
        <Button type="submit" size="lg" className="h-10 w-full" disabled={enviando}>
          {enviando && <Spinner />} Ingresar
        </Button>
        <button
          type="button"
          className="-mt-2 self-center text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          onClick={() => {
            setU(DEMO.usuario);
            setContrasena(DEMO.contrasena);
          }}
        >
          Datos de ejemplo: completar con Lucía (administradora)
        </button>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="h-px flex-1 bg-border" /> o <span className="h-px flex-1 bg-border" />
        </div>
        <div className="flex flex-col items-center gap-2 text-center">
          <span className="text-muted-foreground">
            ¿No tenés cuenta?{" "}
            <Link to="/registro" className="text-foreground underline underline-offset-4">
              Registrate
            </Link>
          </span>
          <Badge variant="secondary">Registro disponible próximamente</Badge>
        </div>
      </form>
    </MarcoIngreso>
  );
}
