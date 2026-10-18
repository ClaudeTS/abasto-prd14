# Implementación del PRD 1.4 en el fork

Fuente de verdad: [`docs/PRD-1.4.md`](PRD-1.4.md). Mockups de referencia: el lienzo "Abasto — Mockups PRD 1.4"
(pantallas Dashboard, Pedidos, Detalle, Negociación, Proveedores, Reglas, Configuración, Ingreso).

Ya existe y se reutiliza (no se reescribe): el agente de compras de Guzmán (`app/agente.py`,
`app/inventario.py`, `app/interpretacion.py`, `app/rutas_agente.py`, contrato en `docs/AGENTE.md`), el
pipeline de cotizaciones, la normalización, el optimizador, la negociación con gemelo y las llamadas.

## Reparto (un bloque por rama)

| Bloque | Rama | Requisitos | Backend (archivos propios) | Frontend (archivos propios) |
|---|---|---|---|---|
| 1. Pedidos | `prd/pedidos` | RF-05, RF-10, RF-12, RF-18, estados §6.2 | `app/rutas_pedidos.py`, `app/historial_pedidos.py`, `app/informe_pdf.py`, `data/pedidos_historicos.json` | `pages/Pedidos.tsx`, `pages/PedidoDetalle.tsx`, `features/pedidos/*` |
| 2. Agente (nuevo pedido) | `prd/agente` | RF-01, RF-03 (UI), §6.1 | — (usa `docs/AGENTE.md`) | `pages/NuevoPedido.tsx`, `features/agente/*` |
| 3. Reglas, configuración e ingreso | `prd/reglas` | RF-02, RF-04, RF-13, RF-14, RF-15, RF-20, RF-21 | `app/rutas_reglas.py`, `app/rutas_auth.py`, `app/reglas.py`, `app/auth.py` | `pages/Reglas.tsx`, `pages/Configuracion.tsx`, `pages/Login.tsx`, `pages/Registro.tsx`, `lib/auth.tsx`, `features/reglas/*` |
| 4. Proveedores y negociación | `prd/proveedores` | RF-07, RF-16, RF-17, RF-19 | `app/rutas_proveedores.py`, `app/ranking.py`, `app/perfiles.py` | `pages/Proveedores.tsx`, `features/proveedores/*` |
| 5. Dashboard y llamadas | `prd/dashboard` | RF-06, RF-09, vigencia 30 días, KPI §4 | `app/rutas_dashboard.py`, `app/kpi.py`, `app/recomendaciones.py`, cambios acotados en `app/llamadas.py` | `pages/Inicio.tsx`, `features/dashboard/*` |
| 6. Infraestructura y QA (Guzmán) | `prd/infra` | Reinicio selectivo, deploy de preview, QA real | `app/store.py`, `render.yaml`, `scripts/smoke_prd14.py` | `frontend/vercel.json` |

### Bloque 6 — Infraestructura, persistencia y QA real (Guzmán)

Rama `prd/infra`. No toca código de pantallas ni endpoints de los bloques 1–5.

Archivos propios: `backend/app/store.py`, `render.yaml`, `frontend/vercel.json`, `docs/DEPLOY_PRD14.md`,
`docs/QA_PRD14.md`, `scripts/smoke_prd14.py`, `backend/tests/test_store_reset.py`.

1. **Reinicio selectivo.** Hoy `store.reset()` borra todos los documentos, así que "Reiniciar demo" también
   borraría las reglas por producto, su historial, la configuración (tipo de cambio, IVA, vigencia), los perfiles
   de proveedores, las altas y las sesiones. Agregar en `store.py` un registro de colecciones que sobreviven al
   reinicio (por ejemplo `registrar_persistente(nombre)`) y que `reset()` borre solo las operativas, en Postgres y
   en JSON. Con test. Al integrar, cada bloque registra sus colecciones de configuración.
2. **Rutas profundas en Vercel.** Agregar `frontend/vercel.json` con el rewrite de SPA a `index.html`, para que
   recargar `/pedidos/<id>` o `/reglas/<id>` no dé 404.
3. **Entorno de preview del fork**, separado del de la demo del pitch: otro servicio en Render, otro proyecto en
   Vercel y otra base (no compartir la de la demo). `CORS_ORIGINS` con la URL de preview. Documentar en
   `docs/DEPLOY_PRD14.md`.
4. **QA con IA y llamadas reales** (cuando esté integrado `main` del fork): recorrer todas las pantallas nuevas
   con `ANTHROPIC_API_KEY`, una llamada real solo a teléfonos del equipo, persistencia tras reiniciar el servicio
   (sesión, reglas, historial) y arranque en frío. `scripts/smoke_prd14.py` contra la URL de preview. Hallazgos en
   `docs/QA_PRD14.md`; los arreglos en archivos de otros bloques se coordinan antes.
5. **Camino al repo del equipo:** proponer cómo y cuándo pasa el fork a `HACKATON-GRUPO-25` y qué entra a la demo.

## Reglas para no pisarse

- **Cada bloque toca solo sus archivos.** Si necesita cambiar un archivo compartido (`app/models.py`,
  `app/main.py`, `app/store.py`, `app/pipeline.py`, `app/negociacion.py`, `app/inventario.py`,
  `frontend/src/api.ts`, `frontend/src/types.ts`, `App.tsx`, `AppShell.tsx`), que el cambio sea mínimo,
  aditivo y explicado en el commit.
- **Modelos nuevos** en el módulo propio del bloque, no en `models.py`.
- **Endpoints nuevos** en el `rutas_<area>.py` del bloque (ya incluidos en `main.py`).
- **Frontend:** llamadas y tipos del bloque en `src/features/<area>/api.ts` y `types.ts`, usando
  `http()` exportado de `src/api.ts` (acepta GET/POST/PATCH/PUT/DELETE y adjunta el token de sesión).
  Las rutas ya están registradas en `App.tsx`; cada bloque reemplaza solo sus páginas provisorias.
- **Sesión:** usar `useAuth()` de `src/lib/auth.tsx` (interfaz estable: `usuario`, `esAdmin`, `cargando`,
  `ingresar`, `salir`). El bloque 3 implementa el real sin cambiar esa interfaz.
- **Estilo:** shadcn/ui ya instalado (`components/ui/*`), español rioplatense en la interfaz, sin datos
  inventados presentados como reales: lo de ejemplo dice "Datos de ejemplo".
- **No romper la demo guiada** (rutas `/pedido`, `/feed`, `/cotizaciones`, `/plan`, `/negociacion`,
  `/vision`) ni los tests existentes.
- **Tests:** cada bloque agrega `backend/tests/test_<area>.py`; toda la suite tiene que pasar
  (`python -m pytest -q`) y el frontend tiene que compilar (`npm run build`).
