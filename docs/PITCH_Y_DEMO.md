# Pitch y demo — Abasto

Tiempo supuesto: 3 min de pitch + 2 min de demo + preguntas. Ajustar al formato real de la hackatón.
Regla: si hay que cortar, se cortan slides, nunca la demo.

## Guion de pitch (3 minutos)

**[0:00 – 0:25] El problema, con una escena.**
"Lucía es la encargada de compras de Tecnova, una empresa de servicios de 80 personas. Este mes
tiene que comprar diez notebooks, quince sillas para los puestos nuevos, papel, tóner y limpieza.
Le escribe a seis proveedores. El importador le manda un PDF en dólares más IVA. La papelera, un
audio de 40 segundos. El fabricante de sillas, una foto de un presupuesto escrito a mano. Otro le
tira precios sin decir si incluyen IVA. Lucía no compara: le compra al de siempre."

**[0:25 – 0:50] Por qué importa (al jefe).**
"Esto pasa en cualquier empresa. Compran decenas de cosas por mes y nadie cotiza bien porque lleva
horas. El gerente no sabe si está pagando de más, no se entera cuando un proveedor sube los precios
de a poco, y si Lucía se va, se va con ella todo lo que sabe de los proveedores. Las empresas grandes
tienen un departamento de compras y software de cien mil dólares al año. Las demás tienen a Lucía y
un WhatsApp."

**[0:50 – 1:35] Qué es Abasto.**
"Abasto es un agente de compras con IA. Lucía le dice qué necesita, por voz o por escrito, y Abasto hace
la compra entera: revisa el inventario, pide cotizaciones, llama a quien no contesta, arma el plan, ensaya
la negociación y emite las órdenes. Con el piloto automático, Lucía no toca nada más: Abasto le
repregunta al proveedor lo que no entendió y cierra la compra. Sin piloto, lo que ella marcó como manual
o lo que supera su tope espera su OK.
Por dentro hace tres cosas que sin IA no se pueden hacer.
Uno: **entiende** las cotizaciones como llegan: texto, PDF, foto, audio, en pesos o en dólares, con o
sin IVA, y las normaliza con evidencia de cada número.
Dos: **optimiza** la compra con un solver matemático: reparte el pedido entre proveedores considerando
mínimos de pedido, plazos de entrega, envío y riesgo. No elige 'el más barato', elige el que más conviene.
Tres: **ensaya la negociación**. Antes de mandar un mensaje, simula la conversación contra un gemelo
digital del proveedor con tres estrategias distintas, mide cuál funciona mejor y le propone a Lucía
el mensaje. Lucía aprueba. Nada se manda sin ella."

**[1:35 – 1:45] Transición a la demo.**
"Lucía le pide a Abasto la compra de octubre de Tecnova. Por voz."

→ **DEMO (ver abajo)**

**[post-demo, 0:40] Hacia dónde va.**
"Lo que vieron son tres de siete capas, y la mitad de una cuarta: el pronóstico de consumo ya funciona.
Con cada compra, Abasto aprende cómo se comporta cada proveedor: cuánto cede, cuándo sube, si cumple. Con
el historial, también va a predecir precios: 'comprá el tóner del trimestre ahora, el importador sube cuando
sube el dólar'. Y con muchas empresas, arma
un índice de precios de mercado: 'estás pagando 14 % sobre la mediana por las resmas'. Eso es lo que
nadie puede copiar sin los datos."

**[0:20] Cierre.**
"SAP, Pactum y Walmart ya tienen esto. La empresa de 80 personas compra por WhatsApp y guarda las
cotizaciones en una carpeta de mails. Abasto es el director de compras que esa empresa nunca pudo
pagar."

## Demo en vivo (2 minutos)

Preparación: `make reset` hecho (también vuelve el Inventario a los modos de siempre), navegador al 125 %,
pestaña única en la pantalla **Agente**, Chrome o Edge con el permiso de micrófono dado, modo no molestar,
video de respaldo abierto en otra ventana. Tipo de cambio del día cargado en `config.tipo_cambio_usd`.

La pantalla **Agente** es la portada de la app. Lucía dice qué hay que comprar y el agente hace el resto:
en la demo, después del primer clic no se toca nada más. Todo se ve en vivo en la línea de tiempo de los 9 pasos.

Con `data/inventario_demo.json`, la frase de la demo arma el pedido de siempre: 10 notebooks y 15 sillas (lo
pedido) más 150 resmas, 8 tóner y 60 L de desinfectante (reposición). Por eso el plan y el ahorro son los de
siempre: $ 498.454 + IVA y 8,1 %.

| Paso | Qué hacés | Qué decís |
|---|---|---|
| 1. El pedido, por voz | En **Agente**, con **Piloto automático** prendido, clic en el micrófono y decir: "Abasto, armá la compra del mes. Entran diez personas nuevas el 28 y necesitan notebook. Y para la oficina nueva, quince sillas ergonómicas para el 3 de noviembre." Revisar el texto y clic en **Hacer la compra**. Sin micrófono: **Usar el ejemplo**. Desde acá, no se toca nada. | "Lucía no llena una planilla: le dice a Abasto qué necesita, como se lo diría a alguien del equipo. Y se va a hacer otra cosa." |
| 2. La propuesta | Señalar los pasos **Entender el pedido** y **Revisar el inventario**: lo que pidió (notebooks y sillas) y la reposición (resmas, tóner y desinfectante), con la cuenta de las resmas. | "Lo que pidió, y lo que se le va a terminar. Las resmas: noviembre viene 14 % arriba y ya están bajo el mínimo. Cada línea dice por qué está ahí." |
| 3. Las respuestas | En **Pedir cotizaciones** van llegando los 6 proveedores. Si la papelera no contesta a tiempo, el agente la llama solo (paso **Llamar a quien no responde**). Para mostrar un PDF o la foto: **Ver los mensajes**. | "Llegan como llegan de verdad: un PDF en dólares más IVA, una foto escrita a mano. Al que no contesta, Abasto no lo espera: lo llama." |
| 4. La duda | En **Revisar respuestas dudosas** aparece el WhatsApp del agente con Compuservice: "¿Los precios que me pasaste incluyen IVA?" "Sí, todo con el IVA incluido." | "Compuservice no aclaró el IVA. Abasto no adivina: le pregunta al proveedor y confirma con su respuesta. Nadie tuvo que intervenir." |
| 5. El plan | Señalar el paso **Armar el plan de compra**: ahorro, total y el caso de las sillas. Para el detalle: **Ver el plan y por qué**. | "Reparte entre tres proveedores: $ 498.454 más IVA, 8 % menos que comprarle todo al de siempre, casi 44 mil pesos, y 16 % en lo que el habitual vende. Las sillas no van al más barato: el fabricante exige un lote de 20 y necesitamos 15. Eso lo decide un solver, no el modelo de lenguaje." |
| 6. Negociación y órdenes | El agente ensaya la negociación con Ofisillas, manda el mensaje y emite las 3 órdenes: todas con **La mandó el agente**. Arriba aparece **Compra cerrada** con el resumen. | "Con Ofisillas ensayó tres estrategias y la de volumen consiguió 5 % menos; le mandó el mensaje. Y emitió las órdenes. Las notebooks estaban en manual y el tóner pasaba su tope: con el piloto automático, Lucía le dio permiso para resolverlo. Cada orden dice qué regla saltó y por qué." |
| 7. Visión | 10 segundos en las próximas capas. En Predicción, mostrar que el pronóstico de consumo ya es real (el del Inventario); el de precios sigue siendo diseño. | "Y esto es lo que se construye con el tiempo y los datos. El pronóstico de consumo ya lo vieron funcionar; el de precios es lo que sigue." |

Las órdenes que tienen que aparecer en el paso 6, con y sin piloto automático:

| Orden | Proveedor | Qué lleva | Con piloto | Sin piloto |
|---|---|---|---|---|
| OC-1001 | Compuservice | Notebooks (manual) y tóner ($ 25.574, supera su tope de $ 20.000) | La manda el agente | Espera a Lucía |
| OC-1002 | Ofisillas | Sillas (manual) y la negociación | La manda el agente | Espera a Lucía |
| OC-1003 | Papelera del Sur | Resmas ($ 26.804, tope $ 30.000) y desinfectante ($ 6.787, tope $ 10.000) | La manda el agente | **Sola** |

Para mostrar el control, si sobra tiempo: **Nueva compra** con **Piloto automático** apagado (el agente resetea
la demo solo). Hace todo igual, también la repregunta del IVA, y se frena una sola vez: la tarjeta **Abasto
necesita tu OK** con OC-1001 y OC-1002. Desde **Inventario** se cambia qué compra solo y hasta qué monto:

- Desinfectante a manual: la orden de Papelera también espera.
- Tóner "sin tope": la orden de Compuservice sigue esperando, por las notebooks.

Sin `ANTHROPIC_API_KEY` el paso de negociación queda en error y la compra sigue igual (las otras órdenes salen).

### Plan B: recorrido paso a paso, sin el agente

Las pantallas de siempre siguen funcionando con el mismo pedido (menú **Detalle**, "Hacer la compra a mano").
Si el agente falla en vivo:

| Paso | Qué hacés | Qué decís |
|---|---|---|
| 1. Pedido | Mostrar la tabla precargada (5 líneas: notebooks, sillas, resmas, tóner, desinfectante). Clic en **Cotizar**. | "La compra de octubre. Un clic." |
| 2. Feed | Ver llegar las respuestas: texto, PDF, foto. La papelera tarda: en su fila, clic en **Llamar**, antes de los 40 s (si llega su audio, ya no se la puede llamar). Seguir la transcripción en vivo; al cortar, su cotización entra al feed como un mensaje más. Sin llamadas, la papelera manda un audio a los 40 s: clic en **Ver transcripción** (no hay audio que reproducir). | "Llegan como llegan de verdad. Este PDF está en dólares más IVA. Esta foto está escrita a mano. Este mensaje de Compuservice no dice si incluye IVA: Abasto lo marca para revisar en vez de adivinar. Y la papelera todavía no contestó. En vez de esperar, Abasto la llama. Lo que dice por teléfono se lee igual que un WhatsApp." |
| 3. Cotizaciones | Abrir la tarjeta de TecnoImport: mostrar la conversión USD → UYU y el bloque de **evidencia** (botón "Ver original" resalta el fragmento en el PDF). Abrir la de Papelera del Sur: caja de 5 → unidad, con IVA → sin IVA. En la tarjeta amarilla de Compuservice, clic en **Sí, IVA incluido**. | "Cada número tiene de dónde salió y qué conversión se aplicó. Esto es lo que nos separa de un chatbot: nunca inventa un precio. Y cuando no sabe, pregunta: Lucía confirma el IVA con un clic." |
| 4. Plan | Clic en **Optimizar**. Mostrar el ahorro grande y la explicación. Señalar las sillas. | "Reparte entre tres proveedores. Ahorra 8 % del total, casi 44 mil pesos, y 16 % en lo que el habitual vende. Y fíjense las sillas: no las compra al más barato, porque el fabricante exige un lote de 20 y necesitamos 15. Eso lo decide un solver, no el modelo de lenguaje." |
| 5. Negociar | Clic en **Negociar con Ofisillas** (el proveedor que Abasto sugiere: es donde hay más brecha con el mejor precio). Esperar las 3 columnas (mientras carga, hablar). Mostrar la elegida y el mensaje. Clic en **Aprobar y llamar** (en modo real suena el celular de Ofisillas); al cortar, aparece el resultado (si hubo acuerdo y el precio acordado frente al cotizado). Sin llamadas: **Aprobar y enviar**. | "Acá simula tres negociaciones contra un gemelo de Ofisillas. Competencia, volumen, plazo. Miren: mencionar que el fabricante cotiza 9.800 no funcionó, el vendedor sabe que exige 20 unidades. Pero comprometer el equipamiento de los próximos puestos consiguió 5 % menos. Abasto eligió esa, redactó el mensaje y Lucía lo aprueba. Nunca negocia sola. Y en vez de mandar un WhatsApp, Abasto llama con esa estrategia y le trae el resultado." |
| 6. Visión | Mostrar 10 segundos las pantallas de próximas capas. | "Y esto es lo que se construye con el tiempo y los datos." |

Las llamadas alargan la demo. En modo simulado, la de la papelera dura unos 15 s y la de Ofisillas algo más (repite
la charla ensayada); en real, lo que dure la charla. Si no entran en el tiempo, dejar una sola. Cómo configurarlas:
`docs/LLAMADAS.md`.

Si algo falla en vivo: "Les muestro la corrida de hace un rato" y abrir el video. Sin disculpas largas. Si
falla solo el agente, seguir con el plan B desde el paso donde se quedó. Si una
llamada no sale o el celular no suena: **Simular llamada** (la misma llamada, simulada) y seguir.

## Slides (máximo 8)

1. Portada: Abasto · Director de compras con IA para empresas.
2. La escena de Lucía (captura de un WhatsApp con audio + PDF + foto + mensaje ambiguo).
3. El problema en dos frases: "nadie cotiza bien porque lleva horas" (quien compra) / "no sé si pago de más" (quien paga).
4. Las tres capacidades (entiende · optimiza · ensaya).
5. "Sin IA no existe" (qué pasa si sacamos el modelo: queda una planilla vacía).
6. Las 7 capas: la 1, la 4 y la 5 resaltadas; la 3 a medias (el pronóstico de consumo ya funciona); las demás en gris.
7. Mercado y competencia: SAP Ariba, Pactum, Mandel AI → empresas grandes con ERP y equipo de compras. Nosotros: la empresa que compra por WhatsApp y mail.
8. Modelo de negocio + equipo + pedido (qué necesitamos: 10 empresas piloto).

## Modelo de negocio (si preguntan)

- Suscripción mensual por empresa, escalonada por volumen de compras (orden de 1 a 2 % del gasto gestionado), con piloto gratis.
- Más adelante, participación sobre el ahorro verificado en negociaciones.
- Lado proveedor: en el futuro, los proveedores pueden conectar su agente para recibir pedidos estructurados (modelo marketplace).

## Preguntas difíciles y respuestas

**"¿Y si la IA lee mal un precio?"**
Por eso cada número lleva evidencia literal y las cotizaciones con baja confianza se marcan para
revisar; en la demo lo vieron con el mensaje que no aclaraba el IVA. El error es visible y
recuperable: la persona ve el mensaje original al lado. Y el solver trabaja solo con cotizaciones
validadas.

**"¿Los proveedores le van a contestar a un bot?"**
El mensaje sale desde el WhatsApp o el mail de la empresa, con el tono de quien compra, y esa persona
aprueba cada mensaje. Para el proveedor es Lucía pidiendo precios, como siempre. Cuando Abasto llama por
teléfono, se presenta de parte de Lucía y, si le preguntan, dice que es un asistente virtual: nunca lo niega. A
mediano plazo, el proveedor también gana: pedidos claros y sin idas y vueltas.

**"¿Esto no lo hace ChatGPT pegando los mensajes?"**
Pegar un mensaje te da un resumen. No te da un solver que respeta mínimos de pedido y plazos, ni un
gemelo del proveedor que aprende cuánto cede, ni un índice de precios de mercado. Es un sistema que
acumula datos, no un chat.

**"¿Qué pasa si el gemelo del proveedor no se parece al proveedor real?"**
Al principio es un perfil genérico por rubro. Cada negociación real lo corrige: si el distribuidor
cedió 4 % con el argumento de pago contado, el gemelo lo aprende. Hoy mostramos el mecanismo; el
valor crece con el uso.

**"¿Por qué el gerente va a pagar por esto si el ahorro en insumos es chico?"**
Tres cosas. Primero, el ahorro no es solo en insumos: el equipamiento, los servicios y las compras
grandes pasan por el mismo flujo, y ahí un 5 % son decenas de miles de pesos. Segundo, control:
historial de precios por proveedor, alertas de aumentos y registro de por qué se eligió cada compra.
Tercero, continuidad: el conocimiento de proveedores queda en la empresa, no en una persona.

**"¿Competencia?"**
Hay mucha, arriba: SAP metió agentes de negociación en Ariba, Pactum negocia para Walmart, startups
como Mandel AI leen mails de proveedores para fábricas. Todas venden a empresas con ERP y equipo
de compras, a precios de seis cifras por año. Nadie atiende a la empresa mediana que compra por
WhatsApp. Esa es la oportunidad y también la validación de que el problema vale.

**"¿Y la privacidad de los precios?"**
Los datos de cada empresa son suyos. El índice de mercado se construye solo con precios anonimizados
y agregados, y la empresa elige participar a cambio de ver el índice.

**"¿Cuánto de esto funciona de verdad?"**
Lo que vieron corre: el agente que entiende el pedido por voz y revisa el inventario con un pronóstico
de consumo estacional, la extracción de cuatro formatos y dos monedas, el solver, la negociación simulada y
las órdenes de compra (su envío es simulado).
Los proveedores son simulados porque en 24 horas nadie contesta. Las llamadas salen de verdad (ElevenLabs +
Twilio), pero solo a celulares del equipo, que hacen de proveedores (si la demo fue con llamadas simuladas,
decirlo). La predicción de precios y el índice de mercado son diseño, no código. Lo decimos con claridad.

## Checklist de la hora previa

- [ ] `make reset` ejecutado; recorrido probado una vez más.
- [ ] Micrófono: Chrome o Edge, permiso dado, probado con la frase de la demo. Sin LLM, el back solo entiende
      esa frase: decirla tal cual o usar **Usar el ejemplo**.
- [ ] Inventario con los modos de siempre (el reset los vuelve): notebooks y sillas en manual; resmas, tóner y
      desinfectante en automático, con topes de $ 30.000, $ 20.000 y $ 10.000.
- [ ] En **Agente**, **Piloto automático** prendido (es el default de cada compra nueva).
- [ ] Si la demo va contra el deploy: abrir https://abasto-backend.onrender.com/health para despertarlo (se duerme
      a los 15 min) y resetear con el botón de la UI.
- [ ] Llamadas: decidir real o simulada (`LLAMADAS_MODO`). En real: `GET /llamadas/config` responde `lista: true`,
      hay una llamada de prueba hecha (`python -m scripts.probar_llamada papelera_del_sur`), los celulares de
      Guzmán (papelera) y Emiliano (Ofisillas) tienen sonido, y quien atiende por la papelera dice lo mismo que su
      audio de `data/respuestas_fijas.json` (caja de 5 resmas a 1.090 y bidón de 5 L a 690, con IVA; entrega mañana,
      sin cargo desde $ 5.000; tóner no maneja). Si no, cambian los números del plan del paso 4.
- [ ] Tipo de cambio del día actualizado en `config.tipo_cambio_usd`.
- [ ] Video de respaldo en el disco, abierto y pausado.
- [ ] Cargador enchufado, notificaciones apagadas, zoom 125 %.
- [ ] Cronómetro en el celular del que no presenta.
- [ ] Quién responde cada pregunta: IA → A, arquitectura/solver → C, negocio → B.
