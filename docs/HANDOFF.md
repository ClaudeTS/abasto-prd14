# Estado del fork PRD 1.4 — traspaso

Última actualización: 18/10/2026. Fuente de verdad: [`PRD-1.4.md`](PRD-1.4.md). Reparto: [`PLAN_PRD14.md`](PLAN_PRD14.md).

## Qué está en `main`

Los bloques 1 a 5 del plan están integrados. Suite del backend: 214 tests en verde. El frontend compila
(`npm run build`).

| Bloque | Requisitos | Pantallas | Endpoints principales |
|---|---|---|---|
| 1. Pedidos | RF-05, 10, 12, 18, estados §6.2 | `/pedidos`, `/pedidos/:id` | `GET /pedidos`, `GET /pedidos/{id}/detalle`, `POST /pedidos/{id}/recibir`, `POST /pedidos/{id}/cerrar`, `GET /pedidos/{id}/informe.pdf` |
| 2. Agente | RF-01, 03 (UI), 05 | `/pedidos/nuevo` | los de `docs/AGENTE.md`; la corrida suma `cliente_interno` |
| 3. Reglas, configuración, ingreso | RF-02, 04, 13–15, 20, 21 | `/reglas(/:id)`, `/configuracion`, `/login`, `/registro` | `/reglas…`, `/configuracion`, `/auth/login`, `/auth/yo`, `/auth/logout`, `/auth/registro` (501) |
| 4. Proveedores | RF-07, 16, 17, 19 | `/proveedores(/:id)`; ranking en el detalle del pedido; evaluación en `/negociacion` | `/proveedores/listado`, `/proveedores/{id}/perfil`, `/proveedores/alta`, `/proveedores/alta-agente`, `/proveedores/{id}/aprobar-alta`, `/pedidos/{id}/ranking`, `/negociaciones/{id}/evaluacion` |
| 5. Dashboard y llamadas | RF-06, 09, KPI §4 | `/inicio` (home); secuencia de contacto en el panel de la llamada | `GET /dashboard`, `GET /dashboard/recomendaciones`, `POST /dashboard/recomendaciones/{id}/descartar`; `GET /llamadas/{id}` suma `secuencia` |

La demo guiada original (`/pedido`, `/feed`, `/cotizaciones`, `/plan`, `/negociacion`, `/vision`) sigue igual, en
"Demo guiada" del menú.

## Cómo correrlo

Igual que en `AGENTS.md` §5. Ingreso: `lucia` / `abasto2026` (administradora). Martín y Sofía tienen rol consulta
(ver `AGENTS.md` §11). Variables nuevas:

| Variable | Para qué | Default |
|---|---|---|
| `AUTH_SECRET` | firma de los tokens de sesión | secreto fijo de demo (definirla en Render) |
| `LLAMADA_REINTENTO_MINUTOS` | espera del reintento si el proveedor no atiende | 30 |

Sin `ANTHROPIC_API_KEY` todo funciona con respuestas fijas, salvo la negociación ensayada (como antes) y la
redacción de las recomendaciones, que usa una plantilla.

## Datos de ejemplo

Cada bloque trae su histórico, marcado "Datos de ejemplo" en la UI: `data/pedidos_historicos.json` (8 pedidos,
PED-0131 a 0138), `data/historial_compras.json` (12 meses de precios, órdenes y tiempos de respuesta) y
`data/proveedores_extra.json` (antigüedad, garantía, negociaciones pasadas). No están unificados: los números
entre pantallas pueden no cerrar entre sí.

## Colecciones que deberían sobrevivir a "Reiniciar demo" (bloque 6)

Hoy `store.reset()` las borra. Cuando exista `registrar_persistente()`: `reglas`, `historial_reglas`,
`configuracion`, `perfiles_proveedor`, `proveedores_alta`, `sesiones_revocadas` e `ingresos`. Las del inventario
(modo y tope por producto) las decide Guzmán.

## Decisiones abiertas

1. **Reglas en pedidos en curso.** El PRD dice que los pedidos en curso conservan sus reglas; el agente las relee al
   armar las órdenes y `test_el_modo_que_cambia_en_plena_compra_vale_para_las_ordenes` lo exige. Hoy el panel avisa
   que los cambios aplican desde que se guardan.
2. **`PATCH /inventario/{id}` sin sesión.** Cambia modo, mínimo y tope sin permiso y sin historial. Se cierra con
   `Depends(requiere_admin)` en `rutas_agente.py`.
3. **Ofisillas nunca "gana" en la evaluación de la negociación** (entrega en 7 días contra 2 de Distribuidora
   Oriental). Sigue la regla de RF-16; para el pitch, ajustar el dato de ejemplo o tratar la entrega solo como riesgo.
4. **Altas de proveedores:** quedan en el listado y el perfil, pero no entran al simulador ni al optimizador.
5. **El agente todavía no aplica** proveedores habilitados, plazos requeridos, sustitutos ni objetivos de negociación:
   se guardan y se ven en el panel de reglas.
6. **En el teléfono el menú lateral ocupa la primera pantalla.** Falta un menú plegable.
7. **Un solo bundle de más de 500 kB.** Conviene cargar las páginas con `lazy()`.

## Pendiente fuera del código

- Bloque 6 (Guzmán): reinicio selectivo, `vercel.json`, entorno de preview y QA con IA y llamadas reales.
- Decidir cuándo pasa el fork a `HACKATON-GRUPO-25` y qué entra a la demo del pitch.
