// Controles de formulario con el estilo de shadcn/ui (preset Vega). Viven en el bloque para no chocar con
// otros bloques que agreguen los suyos a components/ui.
import type { ComponentProps, ReactNode } from "react";
import { Label as LabelPrimitive, Switch as SwitchPrimitive } from "radix-ui";
import { cn } from "@/lib/utils";

const CONTROL =
  "h-9 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:bg-muted/50 disabled:opacity-70 aria-invalid:border-destructive aria-invalid:ring-destructive/20";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input data-slot="input" className={cn(CONTROL, className)} {...props} />;
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select data-slot="select" className={cn(CONTROL, "pr-8", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      data-slot="label"
      className={cn("text-sm leading-none font-medium select-none peer-disabled:opacity-50", className)}
      {...props}
    />
  );
}

export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-transparent shadow-xs transition-all outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="pointer-events-none block size-4 rounded-full bg-background shadow-sm ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0.5" />
    </SwitchPrimitive.Root>
  );
}

/** Etiqueta + control + ayuda (el dato actual que la afecta) + error. */
export function Campo({
  id,
  etiqueta,
  ayuda,
  error,
  children,
  className,
}: {
  id: string;
  etiqueta: ReactNode;
  ayuda?: ReactNode;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <Label htmlFor={id}>{etiqueta}</Label>
      {children}
      {error ? (
        <span id={`${id}-error`} className="text-xs text-destructive">
          {error}
        </span>
      ) : (
        ayuda && <span className="text-xs text-muted-foreground">{ayuda}</span>
      )}
    </div>
  );
}

/** Input numérico con sufijo de unidad ("u.", "días", "%"). Guarda el texto tal cual se tipea. */
export function InputNumero({
  id,
  valor,
  onCambio,
  sufijo,
  prefijo,
  error,
  className,
  ...props
}: Omit<ComponentProps<"input">, "value" | "onChange"> & {
  id: string;
  valor: string;
  onCambio: (v: string) => void;
  sufijo?: string;
  prefijo?: string;
  error?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      {prefijo && (
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">
          {prefijo}
        </span>
      )}
      <Input
        id={id}
        inputMode="decimal"
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cn(prefijo && (prefijo.length > 1 ? "pl-12" : "pl-7"), sufijo && "pr-14", "tabular-nums")}
        {...props}
      />
      {sufijo && (
        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-muted-foreground">
          {sufijo}
        </span>
      )}
    </div>
  );
}
