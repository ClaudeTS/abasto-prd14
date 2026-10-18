**Documento de Requisitos de Producto (PRD) — Aplicación "Abasto"**

| **Control del documento**   |                                                                                                         |
|-----------------------------|---------------------------------------------------------------------------------------------------------|
| **Versión**                 | 1.4 — cerrada para revisión del equipo                                                                  |
| **Fecha**                   | 17/10/2026                                                                                              |
| **Estado**                  | Borrador de MVP                                                                                         |
| **Autor**                   | Equipo shAI — Grupo 25 (build 101 AI Hackathon, Montevideo)                                             |
| **Responsable de producto** | A completar                                                                                             |
| **Aprobadores**             | A completar                                                                                             |
| **Fuentes**                 | Audio de definición del producto (fragmentos \[1\]–\[5\]) y decisiones del equipo \[E\] del 17/10/2026. |

Convención: los superíndices \[1\]–\[5\] indican el fragmento del audio que respalda el texto; \[E\] indica una decisión del equipo. Los términos técnicos se definen en la sección 15 (Glosario).

**Historial de versiones**

| **Versión** | **Fecha**  | **Cambios**                                                                                                                                                                                                                                                                                                                                                                                |
|-------------|------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **1.0**     | 17/10/2026 | Primera versión generada a partir del audio de definición.                                                                                                                                                                                                                                                                                                                                 |
| **1.1**     | 17/10/2026 | Listado de pedidos en curso e inspección de conversaciones con su canal.                                                                                                                                                                                                                                                                                                                   |
| **1.2**     | 17/10/2026 | Tablas de reglas de negocio y panel de reglas por producto.                                                                                                                                                                                                                                                                                                                                |
| **1.3**     | 17/10/2026 | Negociación ensayada contra el gemelo digital y perfil de negociación del proveedor.                                                                                                                                                                                                                                                                                                       |
| **1.4**     | 17/10/2026 | Decisiones del equipo: compra automática por producto, tope de precio unitario, ranking de proveedores, secuencia de contacto, dashboard con recomendaciones de IA, listado de pedidos con buscador y exportación a PDF, estados del pedido, tablas operativas, configuración, autenticación, alta de proveedores por el agente, KPI y glosario. Se descarta la sugerencia de liquidación. |

**1. Resumen ejecutivo**

**Abasto** es un agente de compras con inteligencia artificial que gestiona las adquisiciones de una empresa<sup>\[1\]</sup>. Atiende a dos clientes internos —**Ventas** (productos para vender) y **Personal** (productos de consumo interno)— que le envían solicitudes por nota de voz o email, y además repone por sí mismo los productos que tienen activada la compra automática, ya sea al llegar al stock mínimo o al comenzar una zafra<sup>\[1\]\[2\]\[E\]</sup>.

Para cada pedido, el agente consulta las reglas del producto, pide cotizaciones, las compara en una base común (IVA, moneda y unidades), clasifica a los proveedores, ensaya la negociación contra un gemelo digital de cada proveedor y negocia por llamada telefónica, WhatsApp o email<sup>\[4\]\[5\]\[E\]</sup>. Si el producto tiene compra automática y el precio respeta el tope definido, emite la orden de compra; en caso contrario, la deja para aprobación del administrador de compras<sup>\[2\]\[E\]</sup>.

**2. Problema y contexto**

El proyecto surge en el marco de una hackatón, con el objetivo de construir un agente que gestione las compras empresariales de forma automatizada<sup>\[1\]</sup>. Hoy la compra presenta estos problemas:

- **Procesos manuales y fragmentados:** las solicitudes llegan por llamadas, correos o mensajes, sin un canal unificado de entrada<sup>\[1\]\[2\]</sup>.

- **Riesgo de desabastecimiento:** no hay un mecanismo que dispare la reposición cuando un producto alcanza su nivel crítico de inventario<sup>\[1\]\[2\]</sup>.

- **Comparación difícil entre proveedores:** las cotizaciones llegan en monedas, unidades y condiciones distintas, con o sin IVA, y no se pueden comparar de forma directa<sup>\[E\]</sup>.

- **Mezcla de necesidades:** no se distingue operativamente entre lo que compra Ventas para revender y lo que consume el personal<sup>\[3\]</sup>.

**3. Usuarios y roles**

| **Usuario**                    | **Descripción**                                                                                                                                                                  |
|--------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Cliente interno — Ventas**   | Solicita productos destinados a la venta<sup>\[2\]\[3\]</sup>.                                                                                                                   |
| **Cliente interno — Personal** | Todo el personal; solicita productos de consumo interno (papel, artículos de oficina, limpieza, etc.)<sup>\[2\]\[3\]</sup>.                                                      |
| **Administrador de compras**   | Supervisa la aplicación, aprueba las compras que no son automáticas y es el único rol que puede editar el panel de reglas y el panel de configuración<sup>\[3\]\[4\]\[E\]</sup>. |
| **Proveedores**                | Reciben solicitudes de cotización, cotizan y negocian con el agente por llamada, WhatsApp o email<sup>\[2\]</sup>. El agente puede dar de alta proveedores nuevos (RF-19).       |

Todos los usuarios ingresan con usuario y contraseña. Los permisos por rol aplican solo sobre el panel de reglas y el panel de configuración; el resto de la aplicación es de consulta para todos los usuarios autenticados<sup>\[E\]</sup>.

**4. Objetivos y métricas de éxito**

**Objetivos**

- Reponer de forma automática los productos con compra automática activada, sin intervención humana dentro del tope de precio<sup>\[1\]\[2\]\[E\]</sup>.

- Recibir y completar las solicitudes internas por nota de voz o email, pidiendo al solicitante los datos que falten<sup>\[1\]\[E\]</sup>.

- Obtener mejores condiciones de compra comparando cotizaciones y negociando con los proveedores<sup>\[5\]</sup>.

- Dejar trazabilidad completa de cada pedido y de cada conversación con su canal<sup>\[3\]\[E\]</sup>.

**KPI (se muestran en el Dashboard, RF-09)**

| **KPI**                                         | **Cómo se calcula**                                                                                                                                                             | **Meta**                                    |
|-------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------|
| **Tasa de compras automáticas**                 | Órdenes emitidas por compra automática ÷ órdenes totales del período.                                                                                                           | A definir con la línea base del primer mes. |
| **Ahorro contra la cotización inicial**         | (Costo comparable de la primera cotización − costo final acordado) ÷ costo de la primera cotización, ponderado por monto.                                                       | A definir.                                  |
| **Tiempo del pedido a la orden**                | Promedio de horas entre la creación del pedido y la emisión de la orden de compra.                                                                                              | A definir.                                  |
| **Cotizaciones leídas sin corrección**          | Cotizaciones que no requirieron corrección humana ÷ cotizaciones recibidas.                                                                                                     | A definir.                                  |
| **Precisión del gemelo digital**                | Diferencia promedio, en puntos porcentuales, entre la concesión simulada y la concesión real obtenida.                                                                          | ±2 puntos porcentuales.                     |
| **Efectividad de negociación**                  | Negociaciones con mejora de precio o condiciones ÷ negociaciones realizadas<sup>\[5\]</sup>.                                                                                    | A definir.                                  |
| **Tasa de respuesta de proveedores**            | Proveedores que responden a la solicitud de cotización ÷ proveedores contactados.                                                                                               | A definir.                                  |
| **Tiempo de respuesta del proveedor por canal** | Promedio del tiempo que tarda cada proveedor en responder, separado por canal (llamada, WhatsApp, email). Indica cuál es el canal más efectivo para contactar a cada proveedor. | Indicador de consulta.                      |
| **Tiempo de respuesta a pedidos internos**      | Promedio entre la recepción de la nota de voz o email y la creación del pedido completo<sup>\[1\]</sup>.                                                                        | A definir.                                  |

**5. Alcance**

**Dentro del MVP**

- **Solicitudes internas** por nota de voz y email, con pedido de datos faltantes al solicitante<sup>\[1\]\[E\]</sup>.

- **Consulta diaria de stock** en el ERP o base de datos, al cierre de la jornada<sup>\[1\]\[2\]\[E\]</sup>.

- **Compra automática por producto:** reposición por stock mínimo hasta stock base y reposición por inicio de zafra<sup>\[2\]\[E\]</sup>.

- **Tope de precio unitario** por producto, consultado por el agente al recibir cada solicitud<sup>\[E\]</sup>.

- **Comparación y ranking de proveedores** con criterio de desempate<sup>\[4\]\[5\]\[E\]</sup>.

- **Negociación ensayada contra el gemelo digital** y perfil de negociación de cada proveedor<sup>\[E\]</sup>.

- **Contacto con proveedores** por llamada telefónica (Twilio y ElevenLabs), WhatsApp simulado y email, con secuencia de reintentos<sup>\[2\]\[5\]\[E\]</sup>.

- **Alta y autogestión de proveedores por el agente**, simulada dentro de una negociación<sup>\[E\]</sup>.

- **Dashboard (home)** con KPI y recomendaciones generadas por IA<sup>\[3\]\[4\]\[E\]</sup>.

- **Listado de pedidos** con buscador, filtros, detalle de la negociación por canal y exportación a PDF<sup>\[3\]\[E\]</sup>.

- **Panel de reglas por producto** y **panel de configuración** (tipo de cambio y parámetros generales)<sup>\[E\]</sup>.

- **Autenticación** con usuario y contraseña; pantalla de registro visible pero no funcional<sup>\[E\]</sup>.

- **Gestión separada** por cliente interno: Ventas y Personal<sup>\[3\]</sup>.

**Fuera del MVP**

- **API oficial de WhatsApp:** el canal funciona como piloto simulado en la interfaz<sup>\[2\]\[3\]</sup>.

- **Lectura de documentos adjuntos** (PDF, fotos u otros archivos enviados por proveedores o clientes internos)<sup>\[E\]</sup>.

- **Llamadas entrantes**<sup>\[1\]</sup>.

- **Sugerencia de stock similar y liquidación** antes de comprar: descartada<sup>\[E\]</sup>.

- **Registro funcional de usuarios:** solo existe la pantalla<sup>\[E\]</sup>.

- **Controles de resiliencia y costo:** tratamiento de fallas de las API externas y límites de consumo de llamadas e IA (ver riesgos, sección 13)<sup>\[E\]</sup>.

**6. Flujo principal**

**6.1 Del pedido a la mercadería recibida**

1.  **Origen del pedido.** *Vía A — solicitud interna:* un cliente interno envía una nota de voz o un email; el agente identifica si es Ventas o Personal, extrae producto, cantidad, fecha requerida y condiciones, y **solicita al cliente interno los datos que falten** por el mismo canal<sup>\[1\]\[E\]</sup>. *Vía B — compra automática:* al cierre de cada jornada el sistema consulta el stock; para cada producto con compra automática activada evalúa si llegó al stock mínimo o si comienza su zafra, y **rectifica la cantidad** con el stock actual y los pedidos en curso antes de generar el pedido<sup>\[1\]\[2\]\[E\]</sup>.

2.  **Validación contra reglas.** El agente consulta las reglas del producto: tope de precio unitario, condiciones requeridas (plazo de entrega y de pago), proveedores habilitados y sustitutos aceptados<sup>\[2\]\[E\]</sup>.

3.  **Cotización.** Solicita cotización a los proveedores habilitados por su canal preferido. Cada cotización registra su vigencia (30 días si no la indica) y se normaliza a costo comparable: sin IVA, en pesos uruguayos y en la unidad del producto<sup>\[E\]</sup>.

4.  **Ranking de proveedores.** Clasifica a los proveedores según la regla de la sección 11.1 y explica el motivo de la posición de cada uno<sup>\[4\]\[5\]\[E\]</sup>. Si no hay proveedores suficientes, el agente puede contactar y dar de alta uno nuevo (RF-19).

5.  **Negociación.** Ensaya la negociación contra el gemelo digital del proveedor elegido (sección 11.5) y la ejecuta por llamada telefónica; si no atiende, sigue la secuencia de contacto de la sección 11.1<sup>\[5\]\[E\]</sup>.

6.  **Decisión.** Si el producto tiene compra automática y el precio acordado no supera el tope de precio unitario, el agente **emite la orden de compra**. En cualquier otro caso, el pedido queda **pendiente de aprobación** del administrador de compras<sup>\[2\]\[E\]</sup>.

7.  **Seguimiento.** La orden pasa a pendiente de entrega y luego a recibido. Todo el recorrido, con cada conversación, su canal y las transcripciones de las llamadas, queda disponible en el listado de pedidos<sup>\[3\]\[E\]</sup>.

**6.2 Estados del pedido**

| **Estado**                  | **Significado**                                                                                          | **Pasa a**                                    |
|-----------------------------|----------------------------------------------------------------------------------------------------------|-----------------------------------------------|
| **Nuevo**                   | El pedido se creó (solicitud interna o compra automática).                                               | Datos incompletos, Cotizando                  |
| **Datos incompletos**       | El agente pidió al cliente interno información que falta y espera la respuesta.                          | Cotizando, Cancelado                          |
| **Cotizando**               | Se pidieron cotizaciones y se están recibiendo respuestas.                                               | Cotizado, Cancelado                           |
| **Cotizado**                | Hay cotizaciones normalizadas y el ranking de proveedores está listo.                                    | Negociando, Pendiente de aprobación, Aprobado |
| **Negociando**              | El agente ensayó y está ejecutando la negociación con el proveedor.                                      | Pendiente de aprobación, Aprobado             |
| **Pendiente de aprobación** | El producto no tiene compra automática o el precio supera el tope; espera la decisión del administrador. | Aprobado, Cancelado                           |
| **Aprobado**                | Se emitió la orden de compra (por el agente o por aprobación del administrador).                         | Pendiente de entrega                          |
| **Pendiente de entrega**    | La orden fue enviada al proveedor y se espera la mercadería.                                             | Recibido, Cancelado                           |
| **Recibido**                | La mercadería ingresó.                                                                                   | Cerrado                                       |
| **Cerrado**                 | El pedido terminó y queda solo para consulta.                                                            | —                                             |
| **Cancelado**               | El pedido se anuló; se registra el motivo.                                                               | —                                             |

**7. Pantallas**

| **Pantalla**                     | **Contenido**                                                                                                     | **Requisitos**      |
|----------------------------------|-------------------------------------------------------------------------------------------------------------------|---------------------|
| **Ingreso y registro**           | Ingreso con usuario y contraseña. La pantalla de registro existe pero no está operativa en el MVP.                | RF-21               |
| **Dashboard (home)**             | KPI de la sección 4 y recomendaciones generadas por IA a partir del proceso de compra.                            | RF-09               |
| **Listado de pedidos**           | Pedidos en trámite y pedidos ya procesados con mercadería recibida, con buscador y filtros.                       | RF-12               |
| **Detalle del pedido**           | Datos del pedido, cotizaciones, ranking, negociación del agente y conversaciones con su canal; exportación a PDF. | RF-10, RF-18        |
| **Listado de proveedores**       | Proveedores con su resumen de perfil de negociación y su historial.                                               | RF-17, RF-19        |
| **Panel de reglas por producto** | Consulta y edición de las reglas de un producto.                                                                  | RF-13, RF-14, RF-15 |
| **Panel de configuración**       | Tipo de cambio, tasa de IVA, vigencia por defecto de las cotizaciones y moneda base.                              | RF-20               |

**8. Requisitos funcionales**

| **ID**    | **Requisito**                                      | **Prioridad** | **Criterio de aceptación**                                                                                                                                                                                                                                                                                                                                                                                                                   | **Fuente**               |
|-----------|----------------------------------------------------|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------|
| **RF-01** | Solicitudes internas por voz y email               | Must          | El agente interpreta una nota de voz o un email, identifica al cliente interno (Ventas o Personal) y extrae producto, cantidad, fecha requerida y condiciones. Si falta un dato obligatorio, lo solicita al cliente interno por el mismo canal y el pedido queda en "Datos incompletos" hasta completarlo.                                                                                                                                   | Audio \[1\]; Equipo      |
| **RF-02** | Consulta diaria de stock                           | Must          | Una vez por día, al cierre de la jornada, el sistema consulta el stock en el ERP o base de datos. Antes de pedir una reposición rectifica la cantidad con el stock actual y los pedidos en curso.                                                                                                                                                                                                                                            | Audio \[1\]\[2\]; Equipo |
| **RF-03** | Compra automática por producto                     | Must          | Si el producto tiene activada la compra automática, el agente genera el pedido sin consultar: (a) al llegar al stock mínimo, repone hasta el stock base; (b) al comenzar la zafra, pide la cantidad de zafra definida (ej. antigripales en invierno). Si no la tiene activada, el pedido pasa a "Pendiente de aprobación" antes de emitir la orden.                                                                                          | Audio \[2\]; Equipo      |
| **RF-04** | Tope de precio unitario por producto               | Must          | Cada producto puede tener un precio unitario máximo, sin IVA y en la moneda indicada. El agente lo consulta al recibir la solicitud. Si el mejor precio obtenido lo supera, no hay compra automática y el pedido pasa a "Pendiente de aprobación".                                                                                                                                                                                           | Audio \[2\]; Equipo      |
| **RF-05** | Gestión separada por cliente interno               | Must          | Cada pedido indica su cliente interno (Ventas o Personal). El listado de pedidos y el dashboard permiten filtrar por cliente interno.                                                                                                                                                                                                                                                                                                        | Audio \[2\]\[3\]         |
| **RF-06** | Llamadas a proveedores                             | Must          | Las llamadas usan Twilio y ElevenLabs. Al iniciar, el agente se identifica como inteligencia artificial y avisa que la llamada se graba. No hay duración máxima. Si el proveedor no atiende, reintenta a los 30 minutos; si tampoco atiende, le escribe por WhatsApp con el motivo del llamado y, si no tiene WhatsApp, le envía un email con la solicitud de cotización. Se guarda la transcripción completa; el audio se conserva 60 días. | Audio \[5\]; Equipo      |
| **RF-07** | Ranking de proveedores                             | Must          | El agente clasifica a los proveedores con la regla de la sección 11.1: primero el costo comparable; si hay empate en precio, el cumplimiento de los demás atributos; si persiste el empate, la antigüedad y el cumplimiento histórico del proveedor. Para cada proveedor muestra la posición y el motivo.                                                                                                                                    | Audio \[4\]\[5\]; Equipo |
| **RF-08** | Sugerencia de stock similar y liquidación          | Descartado    | Fuera del MVP por decisión del equipo.                                                                                                                                                                                                                                                                                                                                                                                                       | Equipo                   |
| **RF-09** | Dashboard (home)                                   | Must          | Muestra los KPI de la sección 4 y recomendaciones generadas por IA a partir del proceso de compra, por ejemplo: "el producto X aumentó su precio por encima de su promedio histórico" o "el producto X, que se compra regularmente al proveedor A, está en oferta en el proveedor B". Cada recomendación indica los datos que la respaldan y enlaza al producto o al pedido.                                                                 | Audio \[3\]\[4\]; Equipo |
| **RF-10** | Detalle del pedido: negociación y conversaciones   | Must          | Al seleccionar un pedido se ven sus datos, cotizaciones, ranking y la negociación que realizó el agente. Cada conversación y cada mensaje indica el canal (llamada telefónica, WhatsApp, email o nota de voz), fecha y hora, sentido (enviado o recibido) y participante. Las llamadas muestran la transcripción completa.                                                                                                                   | Audio \[3\]; Equipo      |
| **RF-11** | WhatsApp simulado                                  | Must          | La interacción por WhatsApp se simula en la interfaz, sin integración con la API oficial. Se usa en la secuencia de contacto de RF-06.                                                                                                                                                                                                                                                                                                       | Audio \[2\]\[3\]; Equipo |
| **RF-12** | Listado de pedidos                                 | Must          | Lista los pedidos en trámite y los ya procesados con mercadería recibida. Incluye un buscador por producto, proveedor y orden de compra asociada, y filtros por rango de fechas, estado y cliente interno.                                                                                                                                                                                                                                   | Equipo                   |
| **RF-13** | Tablas de reglas de negocio                        | Must          | Las reglas se guardan en las tablas de la sección 11.2, no en el código. Cada decisión automática registra qué reglas aplicó.                                                                                                                                                                                                                                                                                                                | Equipo                   |
| **RF-14** | Panel de reglas por producto                       | Must          | El administrador elige un producto, ve todas sus reglas con el dato actual que las afecta y las modifica con validación y vista previa del efecto. El cambio aplica a los pedidos nuevos sin desplegar código.                                                                                                                                                                                                                               | Equipo                   |
| **RF-15** | Historial de cambios de reglas                     | Should        | Cada cambio queda registrado con valor anterior y nuevo, usuario, fecha y hora y motivo, y se puede revertir desde el panel.                                                                                                                                                                                                                                                                                                                 | Equipo                   |
| **RF-16** | Negociación ensayada contra el gemelo digital      | Must          | Antes de negociar, el sistema ensaya 3 estrategias (competencia, volumen y plazo de pago), con 2 corridas de hasta 3 rondas cada una, y muestra por estrategia la transcripción, la ganancia esperada y el riesgo (sección 11.5). Si el producto tiene compra automática, el agente ejecuta la estrategia recomendada; si no, la estrategia y el mensaje quedan para aprobación del administrador.                                           | Equipo                   |
| **RF-17** | Perfil de negociación en el listado de proveedores | Must          | El perfil de cada proveedor se guarda en la tabla perfil_negociacion_proveedor. El listado de proveedores muestra un resumen y, al abrir uno, el perfil completo con su indicador de confianza y sus simulaciones y negociaciones reales. Todos los usuarios lo consultan; solo el administrador lo edita.                                                                                                                                   | Equipo                   |
| **RF-18** | Exportación a PDF                                  | Must          | Desde el detalle del pedido se exporta un informe en PDF con los datos del pedido, con el diálogo del agente (mensajes y transcripciones, con su canal) o con ambos.                                                                                                                                                                                                                                                                         | Equipo                   |
| **RF-19** | Alta y autogestión de proveedores por el agente    | Must          | El agente puede dar de alta un proveedor nuevo: lo contacta, le solicita los datos necesarios (razón social, contacto, canales, condiciones y productos que ofrece) y los ingresa al sistema. También mantiene actualizados los datos de los proveedores existentes. En el MVP se demuestra de forma simulada dentro de una negociación.                                                                                                     | Equipo                   |
| **RF-20** | Panel de configuración                             | Must          | El administrador define el tipo de cambio USD/UYU, la tasa de IVA (22 %), la vigencia por defecto de las cotizaciones (30 días) y la moneda base. Los cambios aplican a las comparaciones nuevas.                                                                                                                                                                                                                                            | Equipo                   |
| **RF-21** | Autenticación                                      | Must          | Ingreso con usuario y contraseña. Existe una pantalla de registro de usuarios, visible pero no funcional en el MVP.                                                                                                                                                                                                                                                                                                                          | Equipo                   |

**9. Requisitos no funcionales**

- **Trazabilidad:** toda interacción registra el canal, la fecha y hora y el pedido al que pertenece. Las transcripciones de las llamadas se conservan; el audio se elimina a los 60 días<sup>\[3\]\[E\]</sup>.

- **Aprobación humana:** las compras de productos sin compra automática, o cuyo precio supera el tope unitario, requieren aprobación del administrador de compras<sup>\[2\]\[E\]</sup>.

- **Identificación del agente:** en llamadas y mensajes, el agente se presenta como inteligencia artificial y, en las llamadas, avisa que se graban<sup>\[E\]</sup>.

- **Integración de telefonía y voz:** Twilio para la conectividad telefónica y ElevenLabs para la voz conversacional<sup>\[5\]</sup>.

- **Idioma:** español rioplatense, tanto en la interfaz como en las conversaciones del agente<sup>\[E\]</sup>.

- **Seguridad:** autenticación con usuario y contraseña; los permisos por rol aplican solo al panel de reglas y al panel de configuración<sup>\[E\]</sup>.

**10. Canales e integraciones**

| **Canal o sistema**     | **Uso**                                                                                                                                 |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| **Nota de voz**         | Entrada de solicitudes de los clientes internos<sup>\[1\]</sup>.                                                                        |
| **Email**               | Entrada de solicitudes internas, comunicación con proveedores y último paso de la secuencia de contacto<sup>\[1\]\[2\]\[3\]\[E\]</sup>. |
| **Llamada telefónica**  | Cotización y negociación con proveedores mediante Twilio y ElevenLabs<sup>\[5\]</sup>.                                                  |
| **WhatsApp**            | Piloto simulado en la interfaz, sin API oficial; segundo paso de la secuencia de contacto<sup>\[2\]\[3\]\[E\]</sup>.                    |
| **ERP / base de datos** | Consulta diaria de stock y datos de productos y proveedores<sup>\[1\]\[2\]\[E\]</sup>.                                                  |
| **Exportación PDF**     | Informe del pedido y del diálogo del agente (salida)<sup>\[E\]</sup>.                                                                   |
| **Documentos adjuntos** | Fuera del MVP: no se leen PDF, fotos ni otros archivos<sup>\[E\]</sup>.                                                                 |

**11. Reglas de negocio**

**11.1 Reglas**

- **Compra automática por producto:** cada producto tiene o no activada la compra automática. Si la tiene, el agente genera el pedido para cubrir la condición que lo disparó: llegar al stock mínimo (repone hasta el stock base) o comenzar la zafra (pide la cantidad de zafra definida para ese período). Si no la tiene, el pedido requiere aprobación<sup>\[2\]\[E\]</sup>.

- **Rectificación de stock:** antes de pedir una reposición, la cantidad se recalcula con el stock al cierre de la jornada y los pedidos en curso<sup>\[E\]</sup>.

- **Tope de precio unitario:** precio máximo que se pretende pagar por unidad de un producto, sin IVA y en la moneda indicada. Superarlo anula la compra automática<sup>\[E\]</sup>.

- **Condiciones del pedido:** si la solicitud exige un plazo de entrega o de pago, solo se consideran los proveedores que lo garantizan<sup>\[5\]</sup>.

- **Ranking de proveedores:** (1) menor costo comparable; (2) ante empate en precio, mejor cumplimiento de los demás atributos: plazo de entrega, condiciones de pago, garantía y especificaciones; (3) ante empate en atributos, mayor antigüedad y mejor cumplimiento histórico del proveedor<sup>\[4\]\[5\]\[E\]</sup>.

- **Sustitutos:** solo se ofrecen los productos sustitutos cargados expresamente para cada producto (tabla producto_sustituto)<sup>\[4\]\[E\]</sup>.

- **IVA:** 22 % (Uruguay). Las comparaciones se hacen sin IVA<sup>\[E\]</sup>.

- **Monedas:** pesos uruguayos (UYU) y dólares (USD). El tipo de cambio se define en el panel de configuración y se compara en la moneda base<sup>\[E\]</sup>.

- **Unidades:** los precios se convierten a la unidad del producto antes de compararse<sup>\[E\]</sup>.

- **Vigencia de las cotizaciones:** la que indica el proveedor; si no la indica, 30 días<sup>\[E\]</sup>.

- **Secuencia de contacto con el proveedor:** llamada → reintento a los 30 minutos → WhatsApp con el motivo del llamado → email con la solicitud de cotización, si no tiene WhatsApp<sup>\[E\]</sup>.

**11.2 Tablas de reglas**

Las reglas se guardan en tablas de la base de datos, no en el código. El agente las consulta antes de cada decisión y registra cuáles aplicó.

| **Tabla**                        | **Para qué sirve**                                                                  | **Campos principales**                                                                                                                                                                                                                                                 |
|----------------------------------|-------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **producto**                     | Catálogo de lo que se compra.                                                       | id, SKU, nombre, cliente interno (Ventas / Personal), unidad de medida, marca y modelo, moneda, activo.                                                                                                                                                                |
| **regla_producto**               | Reglas de reposición y compra de cada producto.                                     | producto_id, compra automática (sí / no), stock mínimo, stock base, cantidad de zafra, inicio y fin de zafra, tope de precio unitario (sin IVA), moneda del tope, plazo de entrega máximo, plazo de pago requerido, admite sustitutos, vigente desde, actualizado por. |
| **proveedor**                    | Datos y condiciones de cada proveedor.                                              | id, razón social, email, teléfono, WhatsApp (sí / no), canal preferido, plazo de pago habitual, plazo de entrega habitual, garantía, fecha de alta (antigüedad), cumplimiento histórico (%), alta realizada por (agente / usuario), activo.                            |
| **producto_proveedor**           | Qué proveedores venden cada producto y en qué condiciones.                          | producto_id, proveedor_id, precio de referencia, mínimo de compra, unidad de venta, factor de conversión, prioridad.                                                                                                                                                   |
| **producto_sustituto**           | Sustitutos aceptados para cada producto.                                            | producto_id, sustituto_id, aprobado por.                                                                                                                                                                                                                               |
| **regla_negociacion**            | Margen que el agente puede pedir y ceder al negociar.                               | producto_id o proveedor_id, descuento objetivo (%), concesión máxima (%). Valores a definir (pregunta abierta 1).                                                                                                                                                      |
| **configuracion**                | Parámetros generales del panel de configuración.                                    | tipo de cambio USD/UYU, fecha del tipo de cambio, tasa de IVA (22 %), vigencia por defecto de cotizaciones (30 días), moneda base, actualizado por.                                                                                                                    |
| **perfil_negociacion_proveedor** | Perfil de negociación de cada proveedor; alimenta al gemelo digital (sección 11.6). | proveedor_id, estilo, precio piso estimado (%), palancas a las que es sensible, argumentos a los que no es sensible, concesión típica por palanca, condiciones habituales, confianza, negociaciones observadas, actualizado el.                                        |
| **simulacion_negociacion**       | Resultado de cada ensayo contra el gemelo y su comparación con la negociación real. | id, pedido_id, proveedor_id, versión del perfil, estrategia, corrida, transcripción ensayada, ganancia esperada, riesgo, estrategia elegida, aprobado por, resultado real, desvío simulado contra real (puntos porcentuales).                                          |
| **historial_regla**              | Auditoría de cada cambio de regla o configuración.                                  | tabla, registro, campo, valor anterior, valor nuevo, usuario, fecha y hora, motivo.                                                                                                                                                                                    |

**11.3 Tablas operativas**

Estas tablas registran lo que ocurre en cada compra. La columna "Cómo la usa el agente" explica su propósito para que el agente, y cualquier modelo que trabaje sobre la base, sepa cuándo leerlas o escribirlas.

| **Tabla**             | **Cómo la usa el agente**                                                                                                                                               | **Campos principales**                                                                                                                                                                              | **Se relaciona con**                                |
|-----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------|
| **usuario**           | Identifica quién ingresa y quién aprueba. El rol decide quién puede editar los paneles; el cliente interno indica a qué flujo pertenecen sus solicitudes.               | id, nombre, email, contraseña (hash), rol (administrador / consulta), cliente interno (Ventas / Personal), activo.                                                                                  | pedido, historial_regla                             |
| **inventario**        | Fuente del stock. Se actualiza al cierre de cada jornada; el agente la lee para detectar stock mínimo y para rectificar cantidades antes de reponer.                    | producto_id, stock actual, stock en pedidos en curso, fecha y hora del corte.                                                                                                                       | producto                                            |
| **pedido**            | Unidad de trabajo del agente: una necesidad de compra con su estado. Todo lo demás (cotizaciones, conversaciones, orden) cuelga de un pedido.                           | id, origen (solicitud interna / stock mínimo / zafra), cliente interno, solicitante, estado (sección 6.2), fecha de creación, fecha requerida, motivo de cancelación.                               | pedido_item, cotizacion, conversacion, orden_compra |
| **pedido_item**       | Qué se pide y cuánto. El agente completa estos datos o los pide al solicitante.                                                                                         | pedido_id, producto_id, cantidad, unidad, condiciones requeridas (entrega, pago).                                                                                                                   | pedido, producto                                    |
| **cotizacion**        | Oferta de un proveedor para un pedido. El agente la normaliza, verifica su vigencia y la usa para el ranking.                                                           | id, pedido_id, proveedor_id, fecha, vigencia (30 días si no se indica), moneda, incluye IVA, plazo de entrega, condiciones de pago, garantía, mensaje de origen, posición en el ranking y motivo.   | pedido, proveedor, cotizacion_item                  |
| **cotizacion_item**   | Precio por producto de una cotización, tal como vino y ya normalizado. Es la base del costo comparable y del historial de precios que usa el dashboard.                 | cotizacion_id, producto_id, precio original, unidad original, bonificación, mínimo de compra, precio comparable (sin IVA, moneda base, unidad del producto).                                        | cotizacion, producto                                |
| **orden_compra**      | Compra emitida. El agente la crea si hay compra automática dentro del tope; si no, la crea al aprobarse. Es el número que se busca en el listado de pedidos.            | número, pedido_id, proveedor_id, fecha de emisión, total, moneda, emitida por (agente / usuario), aprobada por, estado (emitida / pendiente de entrega / recibida / cancelada), fecha de recepción. | pedido, proveedor, orden_compra_item                |
| **orden_compra_item** | Líneas de la orden.                                                                                                                                                     | orden_compra_id, producto_id, cantidad, precio unitario acordado.                                                                                                                                   | orden_compra, producto                              |
| **conversacion**      | Agrupa los mensajes de un mismo intercambio con un proveedor o un cliente interno, con su propósito. Es lo que se ve en el detalle del pedido.                          | id, pedido_id, contraparte (proveedor o cliente interno), canal, propósito (solicitud de datos / cotización / negociación / alta de proveedor), fecha de inicio, estado.                            | pedido, mensaje, llamada                            |
| **mensaje**           | Cada mensaje enviado o recibido, con su canal. Es el registro auditable del diálogo y la base del informe PDF.                                                          | id, conversacion_id, canal (llamada / WhatsApp / email / nota de voz), sentido (enviado / recibido), participante, fecha y hora, texto o transcripción.                                             | conversacion                                        |
| **llamada**           | Datos de cada llamada telefónica y de sus reintentos.                                                                                                                   | id, conversacion_id, número, intento (1 o 2), resultado (atendida / no atendida / buzón), duración, transcripción, audio (se elimina a los 60 días), fecha de vencimiento del audio.                | conversacion                                        |
| **recomendacion**     | Sugerencias que la IA genera para el dashboard a partir de cotizaciones y compras (por ejemplo, alza de precio sobre el promedio histórico u oferta en otro proveedor). | id, tipo, producto_id, proveedor_id, mensaje, datos que la respaldan, fecha, estado (nueva / vista / descartada).                                                                                   | producto, proveedor, cotizacion_item                |

**11.4 Panel de reglas por producto**

Pantalla donde el administrador de compras consulta y ajusta las reglas de un producto (por ejemplo, el producto X):

- **Búsqueda:** se elige el producto por nombre o SKU y se ven todas sus reglas agrupadas en Reposición (compra automática, stock mínimo, stock base, zafra), Tope de precio unitario, Proveedores habilitados, Condiciones requeridas, Sustitutos y Negociación.

- **Contexto:** junto a cada regla se muestra el dato actual que la afecta, como el stock al último cierre o el mejor precio vigente contra el tope.

- **Edición con validaciones:** no se aceptan valores negativos y el stock base debe ser mayor que el stock mínimo.

- **Vista previa del efecto:** antes de guardar se muestra qué cambiaría, por ejemplo: "Con este mínimo, hoy se dispararía una compra de 40 unidades".

- **Historial:** al guardar se pide el motivo; el cambio queda registrado y se puede revertir.

- **Vigencia:** los cambios aplican a los pedidos nuevos; los pedidos en curso conservan sus reglas.

- **Permisos:** solo el administrador edita; el resto consulta.

**11.5 Negociación ensayada contra el gemelo digital**

Antes de negociar, el agente ensaya la conversación contra un gemelo digital: un modelo que responde como ese proveedor a partir de su perfil de negociación (sección 11.6).

- **Insumos:** la cotización vigente, el perfil de negociación del proveedor y las reglas de negociación del producto.

- **Estrategias:** competencia (una oferta mejor de otro proveedor), volumen (compras futuras) y plazo de pago (pago contado). Solo se usan argumentos verdaderos.

- **Ensayo:** cada estrategia se corre 2 veces, con hasta 3 rondas por corrida.

- **Ganancia esperada:** la estrategia gana cuando la oferta resultante mejora a la del resto de los proveedores en precio o bonificación, plazo de entrega, condiciones de pago y garantía.

- **Riesgo aceptable:** el resultado se acepta aunque el plazo de entrega supere en hasta 15 días el de un proveedor regular; por encima de ese margen el riesgo es alto.

- **Ejecución:** si el producto tiene compra automática, el agente ejecuta la estrategia recomendada; si no, la estrategia y el mensaje quedan para aprobación del administrador.

- **Aprendizaje:** al terminar la negociación real se registra el desvío contra lo simulado y el perfil del proveedor se ajusta.

**11.6 Perfil de negociación del proveedor**

El perfil es una estimación interna que se arma con el historial de cotizaciones y negociaciones y con lo que carga el administrador. Se consulta desde el listado de proveedores.

| **Campo**                    | **Qué guarda**                                                                                                                                                                                                | **Ejemplo (Ofisillas, datos de la demo)**                                            |
|------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
| **Estilo**                   | Cómo se comunica y cotiza.                                                                                                                                                                                    | Distribuidor con showroom; responde el vendedor por WhatsApp.                        |
| **Condiciones habituales**   | Mínimo de compra, envío, plazos de pago y entrega, forma de cotizar.                                                                                                                                          | Sin mínimo; envío \$ 1.200; pago 30 días; entrega 7 días; cotiza por unidad más IVA. |
| **Precio piso estimado**     | Cuánto se estima que puede bajar respecto de lo cotizado.                                                                                                                                                     | Hasta 8 %.                                                                           |
| **Sensible a**               | Palancas que lo hacen ceder.                                                                                                                                                                                  | Pago contado; compra futura de más puestos.                                          |
| **No sensible a**            | Argumentos que no lo mueven.                                                                                                                                                                                  | Competencia.                                                                         |
| **Concesión típica**         | Cuánto cede con cada palanca.                                                                                                                                                                                 | 2–4 % por pago contado; hasta 6 % por compras futuras.                               |
| **Confianza**                | Indicador de precisión del gemelo: desvío promedio entre la concesión simulada y la real en las negociaciones observadas. Alta: hasta ±2 puntos; media: hasta ±5; baja: más de ±5 o menos de 3 negociaciones. | Baja (sin negociaciones reales).                                                     |
| **Negociaciones observadas** | Cantidad de negociaciones reales que respaldan el perfil.                                                                                                                                                     | 0\.                                                                                  |

**12. Qué hace la IA y qué decide una persona**

**El agente realiza**

- Interpreta solicitudes por nota de voz y email, y pide al solicitante los datos que falten<sup>\[1\]\[E\]</sup>.

- Consulta el stock al cierre de cada jornada y genera los pedidos de compra automática<sup>\[1\]\[2\]\[E\]</sup>.

- Pide cotizaciones, las normaliza y clasifica a los proveedores<sup>\[4\]\[5\]\[E\]</sup>.

- Ensaya cada negociación contra el gemelo digital y negocia por llamada, WhatsApp o email<sup>\[5\]\[E\]</sup>.

- Emite la orden de compra cuando el producto tiene compra automática y el precio no supera el tope<sup>\[2\]\[E\]</sup>.

- Da de alta proveedores nuevos y mantiene actualizados sus datos<sup>\[E\]</sup>.

- Transcribe las llamadas y genera las recomendaciones del dashboard<sup>\[3\]\[E\]</sup>.

**Una persona decide**

- Configura las reglas de cada producto (compra automática, mínimos, stock base, zafra, tope de precio) y los parámetros generales<sup>\[1\]\[2\]\[E\]</sup>.

- Aprueba los pedidos de productos sin compra automática o cuyo precio supera el tope, junto con su estrategia de negociación<sup>\[2\]\[E\]</sup>.

- Corrige el perfil de negociación de un proveedor cuando no refleja la realidad<sup>\[E\]</sup>.

**13. Riesgos y supuestos**

**Riesgos**

- **Fallas en la negociación por voz:** el proveedor puede no comprender la llamada automatizada o negarse a negociar con una IA<sup>\[5\]</sup>.

- **Reglas mal configuradas:** mínimos, stock base o topes incorrectos generan compras automáticas erróneas<sup>\[1\]\[2\]</sup>.

- **Perfil de negociación sesgado:** si el perfil no refleja al proveedor, el gemelo da resultados optimistas.

- **Expectativa sobre WhatsApp:** el canal está simulado; los usuarios no deben esperar respuestas reales por esa vía<sup>\[2\]\[3\]</sup>.

- **Controles no incluidos en el MVP:** sin tratamiento de fallas de las API externas ni límites de consumo de llamadas e IA, una falla puede dejar datos incorrectos y el costo no está acotado. Riesgo aceptado para el MVP<sup>\[E\]</sup>.

**Supuestos**

- La empresa cuenta con un ERP o base de datos que expone el stock y los datos de proveedores<sup>\[1\]</sup>.

- Hay credenciales y saldo en Twilio y ElevenLabs para las llamadas<sup>\[5\]</sup>.

- Los proveedores aceptan recibir solicitudes por llamada, WhatsApp o email<sup>\[2\]\[5\]</sup>.

- Hay historial o carga manual suficiente para armar un perfil inicial de cada proveedor.

**14. Preguntas abiertas**

1.  **Margen de negociación:** ¿cuál es el descuento objetivo y la concesión máxima que el agente puede negociar sin aprobación?<sup>\[5\]</sup>

2.  **Evolución de WhatsApp:** ¿cuándo se conecta el piloto a la API oficial de WhatsApp Business?<sup>\[2\]\[3\]</sup>

3.  **Formato de la orden de compra:** ¿se envía un documento formal al proveedor o alcanza con la confirmación por email o llamada?

4.  **Perfil inicial de un proveedor nuevo:** sin historial, ¿con qué datos se arma su perfil y cómo se usa el gemelo mientras la confianza es baja?

5.  **Metas de los KPI:** salvo la precisión del gemelo (±2 puntos), las metas se fijan con la línea base del primer mes.

6.  **Responsable y aprobadores** del documento (control del documento).

Preguntas resueltas en la v1.4: acción ante exceso de tope (pasa a aprobación), estructura de la solicitud por voz (el agente pide los datos faltantes), IVA y moneda (sección 11.1), aprobación de la negociación (según compra automática). La pregunta sobre productos similares se descarta junto con RF-08.

**15. Glosario**

| **Término**                   | **Definición**                                                                                                                                   |
|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| **Agente**                    | El componente de IA de Abasto que recibe solicitudes, cotiza, negocia y emite órdenes según las reglas.                                          |
| **Cliente interno**           | Área que solicita la compra: Ventas (productos para vender) o Personal (consumo interno).                                                        |
| **Compra automática**         | Condición de un producto que permite al agente generar y emitir el pedido sin aprobación, dentro del tope de precio.                             |
| **Stock mínimo / stock base** | Nivel que dispara la reposición / nivel hasta el que se repone.                                                                                  |
| **Zafra**                     | Período de mayor demanda de un producto (ej. antigripales en invierno) con una cantidad de compra definida.                                      |
| **Tope de precio unitario**   | Precio máximo por unidad, sin IVA, que se pretende pagar por un producto.                                                                        |
| **Costo comparable**          | Precio unitario de una cotización llevado a una base común: sin IVA, en la moneda base y en la unidad del producto, considerando bonificaciones. |
| **Ranking de proveedores**    | Orden de los proveedores según costo comparable, cumplimiento de atributos y, como desempate, antigüedad y cumplimiento histórico.               |
| **Gemelo digital**            | Simulación de un proveedor, basada en su perfil de negociación, contra la que el agente ensaya antes de negociar.                                |
| **Concesión**                 | Mejora que el proveedor otorga respecto de su cotización original, expresada en porcentaje.                                                      |
| **Confianza del perfil**      | Indicador de qué tan bien el gemelo predijo las negociaciones reales de ese proveedor.                                                           |
| **Vigencia**                  | Plazo durante el cual una cotización es válida; 30 días si no se indica.                                                                         |
| **Secuencia de contacto**     | Orden de canales para llegar a un proveedor: llamada, reintento a los 30 minutos, WhatsApp y email.                                              |
