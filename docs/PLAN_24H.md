# Plan de 24 horas — Abasto

Horas relativas al arranque (H0). Pensado para **3 personas**; al final hay una variante para 2.

## Roles

| Rol | Persona | Responsable de |
|---|---|---|
| **A — IA** | | `llm.py`, prompts, extracción (Capa 1), negociación ensayada (Capa 5) |
| **C — Backend y optimización** | Claude | modelos, endpoints, simulador de proveedores, MILP (Capa 4), cache, `make reset` |
| **B — Producto y demo** | | Frontend completo, datos de demo, pantallas de visión, pitch, slides, video de respaldo |

Los tres hacen pair en los dos checkpoints de integración (H9 y H17). Nadie empieza una feature nueva después de H18.
Regla de ramas: cada uno trabaja en su rama (`ia`, `backend`, `frontend`) y mergea a `main` al menos en cada checkpoint; `main` siempre corre.

## Principios

1. **Vertical primero, ancho después.** A las 9 horas tiene que correr el recorrido completo aunque sea feo y con 2 proveedores.
2. **Todo lo que se muestre tiene evidencia.** Si no sabemos de dónde salió un número, no se muestra.
3. **La demo es el producto.** Cada decisión técnica se evalúa por "¿mejora lo que ve el jurado?".
4. **Cortar antes que trasnochar mal.** Hay un bloque de descanso. Respetarlo.

## Cronograma

### H0–H1 · Arranque
- [ ] Leer `AGENTS.md` y este plan los tres. Congelar alcance.
- [ ] Crear repo, `Makefile`, estructura de carpetas, `.env.example`.
- [ ] A: `llm.py` con helper `pedir_json(prompt, esquema)` funcionando contra la API (prueba con "hola").
- [ ] C: FastAPI con `GET /health`, `models.py` con los Pydantic de `ARQUITECTURA.md`, `store.py`, `make seed`.
- [ ] B: Vite + Tailwind + router con 6 páginas vacías.
- **Entregable:** backend responde `GET /health`, frontend abre con navegación.

### H1–H4 · Percepción (A) + simulador (C) + esqueleto de UI con datos mock (B)
- [ ] A: `extraccion.py` para **texto** primero: mensaje de WhatsApp → `Cotizacion` con evidencia y moneda. Probar con los 3 textos de `data/respuestas_fijas.json`. Después PDF con `pdfplumber` → texto → mismo extractor. Imagen → LLM con visión.
- [ ] C: reglas post-LLM (USD → UYU con `tipo_cambio_usd`, IVA, conversiones de unidades) y `POST /extraer`. Arrancar `simulador.py`: cada proveedor de `proveedores_sim.json` responde con el LLM en su canal, con demoras; guardar `MensajeCrudo` en `runtime/`.
- [ ] B: página **Pedido** (tabla precargada, botón "Cotizar"). Página **Feed** con burbujas tipo chat usando respuestas mock. Página **Cotizaciones** con tarjetas y el bloque de "evidencia" visible.
- **Entregable:** `POST /extraer` funciona con texto, PDF e imagen y convierte moneda. UI navega con mocks.

### H4–H6 · Simulador completo (C) + extracción de audio/foto (A) + Feed real (B)
- [ ] C: `POST /pedidos/{id}/cotizar` lanza el simulador en background; `GET /pedidos/{id}/mensajes` y `GET .../cotizaciones` para polling. Generar el PDF del importador y la imagen "a mano" del fabricante de sillas (PIL). Cache en `runtime/cache/`.
- [ ] A: conectar la extracción al flujo del simulador (cada mensaje nuevo → extracción automática). Marcar `campos_dudosos` y `confianza` en el mensaje ambiguo de Compuservice.
- [ ] B: Feed conectado al backend con polling. Al llegar un mensaje, mostrar "Abasto está leyendo…" y luego la tarjeta; borde amarillo "Revisar" si `confianza < 0.6`.
- **Entregable:** apretás "Cotizar" y ves llegar 6 respuestas distintas convertidas en tarjetas.

### H6–H9 · Optimización (C) + explicación (A) + Plan en UI (B)
- [ ] C: `optimizacion.py` con PuLP según `ARQUITECTURA.md`. Devuelve asignaciones, costo total, costo "baseline" (todo al habitual), ahorro total y ahorro sobre lo comparable, restricciones activas. Verificar contra `resultado_esperado_demo` de `pedido_demo.json`.
- [ ] A: explicación del plan con el LLM a partir del resultado del solver (prompt `explicar_plan`). Empezar `negociacion.py` (gemelo + negociador, una estrategia).
- [ ] B: página **Plan**: tabla producto → proveedor → cantidad → precio, resumen de ahorro grande y visible, explicación, badge "por qué no el más barato" cuando aplique.
- **Entregable:** `POST /pedidos/{id}/optimizar` + página Plan.

### H9 · CHECKPOINT 1 (30 min, los tres)
- [ ] Correr el recorrido Pedido → Cotizar → Cotizaciones → Plan de corrido.
- [ ] Lista de bugs en un solo lugar. Priorizar.
- [ ] **Decisión de corte:** si Percepción u Optimización no están, aplicar cortes (ver abajo) antes de arrancar Negociación.

### H9–H13 · Negociación ensayada (A) + endpoints y estabilidad (C) + Panel de negociación (B)
- [ ] A: `negociacion.py`: para un proveedor, 3 estrategias × 2 corridas × 3 rondas. Gemelo = persona del proveedor + perfil de concesión. Negociador = prompt `negociador`. Scoring = concesión obtenida en UYU. Elegir la mejor, redactar mensaje final.
- [ ] C: `POST /pedidos/{id}/negociar/{proveedor_id}` y `POST .../aprobar`; `asyncio.gather` para las 6 corridas; `oportunidad_negociacion` en el plan; manejo de errores visible; `make reset` en < 10 s.
- [ ] B: página **Negociación**: 3 columnas (estrategia, transcripción corta de la simulación, ganancia esperada), la elegida resaltada, mensaje propuesto editable, botón **Aprobar**. Estado "Enviado (simulado)".
- **Entregable:** negociación completa en < 40 s de espera, con feedback visual mientras corre.

### H13–H16 · Descanso (en turnos) + tareas livianas
- Dormir 2–3 h cada uno, escalonado. El que está despierto hace solo cosas de bajo riesgo:
- [ ] B: pantallas **Visión** (estáticas): perfil del proveedor, predicción de precios, índice de mercado. Con datos inventados claramente marcados como "próximamente".
- [ ] A: revisar prompts con las transcripciones reales de la negociación; ajustar tono y longitud.
- [ ] C: logs legibles, cache determinístico probado, smoke tests de los endpoints críticos.

### H16–H17 · Integración y pulido
- [ ] Transiciones del feed, loaders, números con formato `$ 12.340`.
- [ ] Audio (C): **solo si todo lo anterior está verde.** Si `ENABLE_AUDIO=1` no funciona en 45 min, se deja la transcripción precargada y el audio como archivo que se reproduce en la UI.

### H17 · CHECKPOINT 2 (30 min, los tres)
- [ ] Recorrido completo dos veces seguidas sin tocar código.
- [ ] **Congelar features.** Desde acá solo bugs y pitch.

### H17–H20 · Pitch (B) + estabilidad (A)
- [ ] B: slides (máx. 8) según `PITCH_Y_DEMO.md`. Ensayar el guion con cronómetro.
- [ ] C: `make reset` deja todo listo en < 10 s. Semillas determinísticas (mismas respuestas en cada corrida, usar `temperature` baja + `seed` si el SDK lo permite, o cachear las respuestas del simulador en `runtime/cache/`).
- [ ] A: respuestas a las preguntas técnicas del jurado (precisión, gemelo, costo por corrida).
- [ ] **Grabar video de respaldo** de la demo completa (pantalla + voz). Si en el pitch falla la red, se muestra el video.

### H20–H22 · Ensayos
- [ ] 3 ensayos completos con cronómetro: pitch + demo en vivo ≤ tiempo asignado menos 30 s.
- [ ] Preparar respuestas a las preguntas de `PITCH_Y_DEMO.md` sección "Preguntas difíciles". Decidir quién responde cuál.
- [ ] Probar en la pantalla/proyector si es posible. Zoom del navegador al 125 %.

### H22–H24 · Buffer
- Nada planificado a propósito. Bugs de último momento, descanso, llegar al pitch con el `make reset` hecho y el video a mano.

## Cortes (en orden, si vamos atrasados)

| Si en… | …no está | Cortar |
|---|---|---|
| H4 | extracción de imagen | Imagen fuera. Quedan texto + PDF. La foto se muestra "ya transcripta". |
| H6 | simulador con LLM | Respuestas precargadas en `data/respuestas_fijas.json` con demoras simuladas. Nadie lo nota. |
| H9 | solver MILP | Heurística greedy: por producto, el proveedor más barato que cumpla mínimo y plazo; penalizar >3 proveedores. Explicación igual con LLM. |
| H13 | negociación con simulación | 1 sola estrategia, 1 corrida, 2 rondas. Mostrar "ganancia estimada" en vez de comparar 3. |
| H16 | pantallas de visión | Una sola slide "Hacia dónde va" en el pitch. |
| Siempre | audio | Fuera sin discusión. |

## Riesgos y plan B

| Riesgo | Probabilidad | Plan |
|---|---|---|
| API del LLM lenta o caída en el pitch | Media | Cache de respuestas del simulador y de extracciones en `runtime/cache/`. Video de respaldo. |
| JSON inválido del LLM | Alta al principio | Esquema explícito en cada prompt + un reintento. Nunca regex. |
| MILP infactible con datos de demo | Media | Relajar restricciones en orden (ver `AGENTS.md` §9) y mostrarlo en la explicación. |
| Latencia de negociación > 60 s | Media | `asyncio.gather`, rondas cortas (≤ 80 palabras por turno), `max_tokens` bajo. |
| Nos pasamos del tiempo de pitch | Alta sin ensayo | 3 ensayos cronometrados. Cortar slides, nunca la demo. |
| Sin internet en el escenario | Baja | Video de respaldo en el disco, no en la nube. |

## Variante para 2 personas

Si alguien no puede estar, A absorbe el rol C (IA + backend) y B queda igual. En ese caso: audio fuera
desde el inicio, PDF e imagen del simulador se reemplazan por los archivos precargados de `data/`, y la
negociación se reduce a 2 estrategias × 1 corrida.
