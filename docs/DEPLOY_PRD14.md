# Deploy de preview del PRD 1.4

Entorno para probar el fork (`ClaudeTS/abasto-prd14`) con IA, base y llamadas reales **sin tocar la demo del pitch**.
La demo sigue en `hacktaon.vercel.app` + `abasto-backend.onrender.com` + su base de Supabase, y sale de la copia
`Namzug/hacktaon`; nada de lo de abajo la cambia.

| | Demo del pitch (no se toca) | Preview del fork |
|---|---|---|
| Frontend | Vercel `hacktaon` → https://hacktaon.vercel.app | Vercel `abasto-prd14` → URL: _a completar al crear_ |
| Backend | Render `abasto-backend` (Blueprint `render.yaml`) | Render `abasto-prd14-backend`, creado a mano → URL: _a completar_ |
| Base | Supabase, proyecto de la demo | Supabase, **otro proyecto** |
| Código | `Namzug/hacktaon` (copia de `main` del equipo) | `Namzug/abasto-prd14-preview` (copia de `main` del fork) |

Las URLs se completan acá cuando se crean los servicios; los valores de las variables, nunca.

## 1. De dónde sale el código: una copia en la cuenta Namzug

El proyecto de Vercel está en el equipo HAIRBOX, plan Hobby: Vercel bloquea el deploy de un commit cuyo autor no es
Namzug. Además, Render y Vercel solo ven los repos donde está instalada su app de GitHub, y en `ClaudeTS/abasto-prd14`
no lo está. Por eso el preview hace lo mismo que la demo: lee una copia en la cuenta Namzug.

Para actualizarla cuando Claude integra `main` del fork:

```bash
git fetch https://github.com/ClaudeTS/abasto-prd14 main
base=$(git rev-parse FETCH_HEAD)
# commit vacío con autor Namzug encima de main (sin él, Vercel Hobby no publica)
vacio=$(GIT_AUTHOR_NAME=Namzug GIT_AUTHOR_EMAIL=63017782+Namzug@users.noreply.github.com \
        GIT_COMMITTER_NAME=Namzug GIT_COMMITTER_EMAIL=63017782+Namzug@users.noreply.github.com \
        git commit-tree "$base^{tree}" -p "$base" -m "deploy: preview del fork en $(git rev-parse --short $base)")
git push --force-with-lease=refs/heads/main:<sha actual de la copia> \
  https://github.com/Namzug/abasto-prd14-preview "$vacio:refs/heads/main"
```

El push es forzado porque el commit vacío anterior queda fuera de la historia nueva; `--force-with-lease` evita pisar
algo que no sea ese commit. **Solo a la copia de preview, nunca al fork ni al repo del equipo.**

Alternativa sin copia: `npx vercel deploy --prod` desde `frontend/` y, en Render, "Public Git repository" con el URL
del fork. Funciona, pero los dos deploys pasan a ser manuales en cada integración.

## 2. Base: proyecto nuevo de Supabase

1. Supabase → New project, región **us-west-2** (la misma que Render Oregon: cada consulta va y viene).
2. Connect → **Session pooler** (puerto 5432) → esa cadena es `DATABASE_URL` del backend de preview.
3. No hace falta crear tablas: `store.py` crea `documentos`, `archivos` y `cache` al conectarse, con RLS activado y
   sin políticas, así que la clave pública de Supabase no ve nada.

No se comparte la base con la demo: el store no tiene espacios de nombres, así que un "Reiniciar demo" en el preview
borraría los pedidos de la demo. El plan Free de Supabase permite dos proyectos activos por organización; si ya hay
dos, crear el de preview en otra organización.

## 3. Backend: servicio nuevo en Render (a mano)

Render → New → **Web Service** (no Blueprint) → repo `Namzug/abasto-prd14-preview`, rama `main`. No se agrega a
`render.yaml`: el día que el fork pase al repo del equipo, el Blueprint crearía un segundo servicio.

| Campo | Valor |
|---|---|
| Name | `abasto-prd14-backend` |
| Region | Oregon |
| Plan | Free |
| Build command | `pip install -r backend/requirements.txt` |
| Start command | `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |

Un solo proceso, igual que la demo: el simulador, las llamadas y el agente corren tareas en memoria.

Variables (las mismas de `render.yaml`; solo los nombres):

| Variable | Valor o de dónde sale |
|---|---|
| `PYTHON_VERSION` | `3.12.10` |
| `TZ` | `America/Montevideo` (los timestamps son `datetime.now()` sin zona) |
| `SIM_MODE` | `fijo` |
| `EXTRACCION_MODE` | `auto` |
| `DATABASE_URL` | Session pooler del proyecto de Supabase **de preview** |
| `ANTHROPIC_API_KEY` | secreto, solo en el panel |
| `ANTHROPIC_CUSTOM_HEADERS` | secreto (`anthropic-workspace-id: …`), solo en el panel |
| `CORS_ORIGINS` | la URL de producción del Vercel de preview |
| `LLAMADAS_MODO` | `simulada`; `real` solo para la prueba de llamadas del QA |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_AGENT_ID`, `ELEVENLABS_PHONE_NUMBER_ID` | secretos; los mismos que la demo (el agente "Abasto compras" no usa webhooks, ver `docs/LLAMADAS.md`) |
| `TELEFONOS_PROVEEDORES` | `proveedor_id:+598…`, **solo celulares del equipo** |
| Las que sumen los bloques al integrar | por ejemplo `LLAMADA_REINTENTO_MINUTOS` (bloque 5); revisar `config.py` después de cada integración |

`LLM_MODEL`, `SIM_DELAY_SECONDS` y `ENABLE_AUDIO` tienen default en `config.py`; cargarlas solo para cambiarlas.

El plan Free de Render reparte 750 horas por mes entre los servicios del workspace. Dos servicios que se duermen a
los 15 minutos sin uso entran de sobra, pero el preview no conviene dejarlo despierto con un monitor.

## 4. Frontend: proyecto nuevo en Vercel

Vercel (equipo HAIRBOX) → Add New → Project → `Namzug/abasto-prd14-preview`.

| Campo | Valor |
|---|---|
| Project name | `abasto-prd14` |
| Root Directory | `frontend` |
| Framework preset | Vite (build `npm run build`, salida `dist`) |
| `VITE_API_URL` | URL del backend de preview, en Production y Preview |

`VITE_API_URL` se fija al compilar: después de cambiarla hay que volver a publicar. `VITE_MOCK` no se carga (el modo
mock queda opcional con `?modo=mock`).

Orden para no tener un huevo y una gallina: (1) Supabase, (2) Render con `CORS_ORIGINS` provisoria, (3) Vercel con
`VITE_API_URL` = URL de Render, (4) volver a Render y poner en `CORS_ORIGINS` la URL de producción de Vercel.
Los deploys de preview de Vercel (URLs con hash, una por rama) no están en `CORS_ORIGINS` y no llegan al backend:
para el QA se usa la URL de producción del proyecto.

### Rutas profundas

`frontend/vercel.json` reescribe a `/index.html` toda ruta que no sea un archivo, menos `/assets/`. Vercel busca
primero el archivo estático y recién después aplica el rewrite, así que `/assets/*.js` y el favicon se sirven igual;
recargar `/inicio`, `/pedidos/<id>`, `/reglas/<id>`, `/proveedores/<id>`, `/configuracion` o `/login` devuelve la SPA
y React Router muestra la pantalla. Un chunk que ya no existe (pestaña abierta durante un redeploy) da 404 en vez de
devolver HTML como JavaScript.

La demo del pitch no tiene `vercel.json`: lo resuelve una ruta cargada a mano en el proyecto `hacktaon`
(`^/(?!assets/)[^.]*$` → `/index.html`). En el proyecto nuevo no hace falta cargarla: alcanza con el archivo.

`vite preview` no lee `vercel.json` (tiene su propio fallback de SPA); con él se verificó que el build sirve esas rutas
a cualquier profundidad, porque los assets van con ruta absoluta (`/assets/…`). La prueba real es recargar esas
rutas en el Vercel de preview.

## 5. Reiniciar

| Qué | Cómo | Qué borra |
|---|---|---|
| "Reiniciar demo" (botón de la UI) | `POST /reset` | lo operativo: pedidos, mensajes, cotizaciones, planes, negociaciones, llamadas, corridas del agente, inventario tocado, PDFs y fotos. Conserva las colecciones registradas con `store.registrar_persistente()` (reglas e historial, configuración, perfiles y altas de proveedores, sesiones) y el cache |
| Reinicio con cache | `POST /reset?hard=true` | lo mismo más el cache de respuestas simuladas y extracciones (la próxima corrida vuelve a gastar LLM) |
| Borrado total | hoy no tiene endpoint: `store.reset(total=True)` desde una consola del servicio, o en Supabase → SQL editor `delete from documentos; delete from archivos;` | todo, también las colecciones persistentes |
| Reiniciar el proceso | Render → servicio → Manual Deploy → Restart service | nada: la base está en Supabase y los PDFs se vuelven a bajar de la tabla `archivos`; se pierden solo las tareas en memoria (simulaciones o llamadas en curso) |

Si hace falta el borrado total desde la UI, se agrega `total` a `POST /reset` en `main.py` (no es archivo del
bloque 6: lo coordina Claude).

## 6. Redeployar

- **Código nuevo:** actualizar la copia `Namzug/abasto-prd14-preview` (sección 1). Render y Vercel publican solos al
  recibir el push a `main`. El estado se ve sin entrar a los paneles:
  `gh api repos/Namzug/abasto-prd14-preview/commits/<sha>/status` (Vercel) y `.../deployments?sha=<sha>` (Render).
- **Cambio de variable en Render:** se aplica con un redeploy (Render lo ofrece al guardar).
- **Cambio de `VITE_API_URL` en Vercel:** Deployments → último → Redeploy (sin cache de build).
- **Antes de probar:** abrir `<backend de preview>/health` para despertar el servicio (arranque en frío del plan Free).
