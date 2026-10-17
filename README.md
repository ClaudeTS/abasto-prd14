# Abasto — Director de compras con IA para empresas

> Cargás lo que la empresa necesita comprar. Abasto lo cotiza con tus proveedores, entiende lo que
> te responden por WhatsApp, PDF, foto o audio (en pesos o en dólares), arma el plan de compra que
> más conviene y ensaya la negociación antes de que mandes un solo mensaje.

Proyecto de hackatón (24 h). Demo: la empresa ficticia **Tecnova S.A.** (servicios, 80 personas,
Montevideo) hace su compra de octubre: notebooks, sillas para 15 puestos nuevos, papel, tóner y
limpieza, con 6 proveedores simulados.

## Por qué existe

Cualquier empresa compra decenas de cosas por mes a decenas de proveedores: equipamiento, insumos,
servicios. La persona que compra pide cotizaciones por WhatsApp y mail, recibe un PDF en dólares más
IVA, un audio, una foto de un presupuesto escrito a mano y un mensaje que no aclara si incluye IVA.
Comparar bien lleva horas, así que se le compra "al de siempre". El jefe no sabe si está pagando de
más, no se entera cuando un proveedor sube los precios y, si la persona que compra se va, el
conocimiento se va con ella.

**Sin IA no funciona:** no hay forma de entender cotizaciones desordenadas, de modelar cómo se
comporta cada proveedor ni de ensayar una negociación sin un modelo de lenguaje.

## Qué hace (MVP de la hackatón)

1. **Entiende** cotizaciones en cualquier formato y las normaliza (moneda, IVA, unidades, envío, mínimos, plazos), con evidencia de dónde salió cada número.
2. **Optimiza** la compra con un solver matemático: reparte el pedido entre proveedores minimizando el costo total con mínimos de pedido, plazos de entrega, envío y riesgo de depender de uno solo.
3. **Ensaya la negociación** contra un gemelo digital de cada proveedor, compara estrategias y propone el mensaje con mayor ganancia esperada. Quien compra aprueba antes de enviar.

Visión (no implementada, solo pantallas): perfil de comportamiento por proveedor, predicción de precios y consumo, índice de precios de mercado entre todas las empresas, negociación agente-a-agente.

## Quick start (5 minutos)

Requisitos: Python 3.11, Node 20, una API key de Anthropic.

```bash
git clone https://github.com/Emontone21/HACKATON-GRUPO-25 abasto && cd abasto

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # poné tu ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000

# Frontend (otra terminal)
cd frontend
npm install && npm run dev      # abre http://localhost:5173
```

Con `make dev` se levantan los dos. `make reset` vuelve al estado inicial de la demo.

## Recorrido de la demo

1. **Pedido** → Tecnova carga su compra de octubre (precargada, 5 líneas).
2. **Cotizar** → Abasto escribe a los 6 proveedores. El feed muestra las respuestas llegando: un PDF en dólares, un audio, una foto de un presupuesto a mano, tres mensajes de texto (uno ambiguo).
3. **Cotizaciones** → cada respuesta se convierte en una tarjeta estructurada con evidencia y conversiones (USD → UYU, caja de 5 → unidad, con IVA → sin IVA).
4. **Plan** → el solver reparte la compra y explica por qué; muestra el ahorro frente a "comprar todo al habitual" y el caso donde no eligió al más barato.
5. **Negociar** → para el proveedor con más margen de mejora, Abasto ensaya 3 estrategias, muestra la ganancia esperada de cada una y propone un mensaje. Botón **Aprobar**.
6. **Visión** → pantallas de las capas futuras.

Guion completo y preguntas del jurado en [`docs/PITCH_Y_DEMO.md`](docs/PITCH_Y_DEMO.md).

## Documentación

| Archivo | Para qué |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Reglas para agentes de código y para el equipo: alcance, stack, convenciones, definición de terminado. |
| [`docs/PLAN_24H.md`](docs/PLAN_24H.md) | Cronograma hora a hora, roles, checkpoints y cortes si vamos atrasados. |
| [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) | Modelo de datos, endpoints, modelo MILP, flujo de negociación. |
| [`docs/PROMPTS.md`](docs/PROMPTS.md) | Prompts canónicos de extracción, proveedores simulados, negociador y explicador. |
| [`docs/PITCH_Y_DEMO.md`](docs/PITCH_Y_DEMO.md) | Guion de 3 minutos, demo paso a paso, respuestas a preguntas difíciles. |
| [`data/`](data/) | Proveedores simulados, pedido de la demo y respuestas crudas de ejemplo. |

## Stack

FastAPI + Python 3.11 · SDK de Anthropic · PuLP (MILP) · pdfplumber · React + Vite + Tailwind.
Detalle en `AGENTS.md`.

## Equipo — Grupo 25

| Rol | Persona |
|---|---|
| A — IA (extracción, negociación, prompts) | |
| C — Backend y optimización (endpoints, simulador, MILP) | Claude |
| B — Producto y demo (frontend, datos, pitch) | |

Repo: https://github.com/Emontone21/HACKATON-GRUPO-25
