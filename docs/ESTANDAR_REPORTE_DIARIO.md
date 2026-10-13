# Estándar de Reporte Diario de Obra — Asistente DT (Tucumán)

12/10/2026 · Leonardo Díaz (SoyLeo AI)

## Objetivo

El asistente convierte las fotos y audios que el director técnico (DT) manda por chat en un reporte diario estándar. Con ese reporte y el cronograma de obra, anticipa los pedidos de materiales para que la obra no se detenga.

- **Para el DT:** reportar el día le lleva menos de 5 minutos desde el celular, sin completar formularios.
- **Para el director de proyectos:** un PDF diario por obra con el mismo formato siempre.
- **Para gerencia:** filas listas para pegar en la planilla de seguimiento, comparables entre obras.
- **Para la obra:** alertas de pedido con la fecha límite calculada, antes de que falte el material.

El reporte es la fuente de datos del sistema de gestión más grande. Por eso cada campo tiene formato fijo y el DT confirma todo antes de enviarlo.

## Flujo diario del DT

El DT manda lo que tiene durante el día y el bot ordena todo. Nada sale de la obra hasta que el DT confirma clima y datos.

![Flujo diario del DT: 8 pasos, 1 confirmación](img/flujo-diario.png)

Si el DT solo sube fotos, el bot propone el texto a partir de ellas y pregunta lo demás. Si nadie cierra el reporte, a las 18 h el bot avisa con el borrador listo para confirmar.

## Cronograma de obra como base

Cada obra arranca con su cronograma cargado, y todo lo que el DT reporta se vincula a una tarea de ese cronograma. Como el estudio planifica en MS Project, el cronograma se exporta a Excel/CSV con estas columnas y se completan las de materiales:

| Columna | Ejemplo | Uso en el sistema |
| --- | --- | --- |
| ID tarea | T-034 | Vínculo de avances, fotos y notas |
| Rubro | 08 Contrapisos y carpetas | Agrupar el reporte y la planilla |
| Tarea | Contrapiso planta baja | Lo que el bot reconoce en el audio |
| Inicio / fin previsto | 13/10/2026 – 17/10/2026 | Avance previsto y desvío |
| Predecesoras | T-031 | Saber qué tareas se traban si algo se atrasa |
| Material | Cemento portland | Previsión de pedidos |
| Cantidad y unidad | 120 bolsas | Consumo previsto por día |
| Proveedor habitual | Corralón X | A quién pedir |
| Plazo de entrega (días) | 3 | Fecha límite de pedido |

Rubros estándar, numerados para que el sistema grande pueda cruzarlos con el cómputo y presupuesto:

01 Trabajos preliminares · 02 Movimiento de suelos · 03 Fundaciones · 04 Estructura de H°A° · 05 Mampostería · 06 Aislaciones · 07 Revoques · 08 Contrapisos y carpetas · 09 Cubiertas · 10 Instalación sanitaria · 11 Instalación eléctrica · 12 Instalación de gas · 13 Climatización · 14 Carpinterías · 15 Revestimientos · 16 Pisos y zócalos · 17 Cielorrasos · 18 Pinturas · 19 Vidrios y espejos · 20 Limpieza final

Cuando el DT dice "terminé el contrapiso de planta baja", el bot propone la tarea T-034. Si hay dos parecidas, pregunta cuál es. Un trabajo que no está en el cronograma se registra como **tarea no prevista**, que también es un dato útil para gerencia.

## Campos del reporte diario

El reporte tiene 11 bloques fijos. Ninguno se envía sin los obligatorios, y el bot pregunta lo que falta antes de cerrar.

| Bloque | Campos | Oblig. | De dónde sale |
| --- | --- | --- | --- |
| A. Encabezado | N° de reporte (correlativo por obra), obra, fecha, DT, horario de jornada | Sí | Automático; el bot pregunta la obra |
| B. Condiciones | Clima mañana y tarde, temp. máx./mín. (°C), lluvia (mm), estado del terreno (seco / húmedo / anegado) | Sí | API de clima, confirmado por el DT |
| C. Jornada | Completa / parcial / no laborable; causa de horas perdidas (lluvia, falta de material, corte de luz o agua, paro, feriado) | Sí | DT |
| D. Personal | Empresa o subcontrato, categoría UOCRA, cantidad, horas | Sí | Audio del DT |
| E. Avance | ID de tarea, rubro, descripción, % acumulado real, % previsto, desvío | Sí | Audio + cronograma; el desvío es automático |
| F. Materiales | Ingresos (remito, proveedor, material, cantidad), faltantes, stock declarado | Si hubo | Foto del remito + audio |
| G. Equipos | Equipos en obra (hormigonera, andamios, guinche, bomba) y su estado | No | DT |
| H. Higiene y seguridad | Uso de EPP, visitas de ART o del responsable de HyS, incidentes | Sí (sí/no) | DT |
| I. Notas de obra | Órdenes de servicio, notas de pedido, observaciones (ver sección siguiente) | Si hubo | DT, texto literal |
| J. Fotos | Foto, tarea vinculada, descripción, hora | Mín. 3 | El DT las sube; el bot las describe y vincula |
| K. Próximos pasos | Tareas de mañana según cronograma, pedidos a gestionar | Sí | Automático desde cronograma y alertas |

Si el DT solo manda fotos, el bot arma un borrador de los bloques E y J a partir de las imágenes y pregunta lo demás en mensajes cortos: primero lo que va con sí/no o botones, después lo abierto.

## Notas de obra

Las notas se guardan textuales y siguen abiertas hasta que alguien las cierra, porque tienen valor contractual. Es la única parte del reporte que el bot no resume ni reescribe: transcribe, muestra el texto y pide confirmación.

| Tipo | Quién la emite | A quién | Ejemplo |
| --- | --- | --- | --- |
| Orden de servicio | DT / inspección | Contratista | Rehacer el revoque del muro medianero norte |
| Nota de pedido | Contratista | DT / inspección | Pedido de definición del color de carpinterías |
| Observación del DT | DT | Registro interno / director | Fisura en viga V-12, revisar con el calculista |
| Comunicación con el comitente | DT o comitente | El otro | El cliente pide cambiar cerámico por porcelanato |
| Acta | DT y partes | Registro | Acta de replanteo, de medición o de recepción |

Campos de cada nota: número correlativo por tipo y obra, fecha, emisor, destinatario, asunto, texto literal, plazo de respuesta, estado (pendiente / respondida / cumplida), tarea y fotos vinculadas.

Reglas:

- Toda nota pendiente aparece en cada reporte diario hasta que se cierra.
- Si tiene plazo, el bot avisa al DT un día antes y al director cuando vence.
- Si la nota cambia un material o una cantidad (como el porcelanato del ejemplo), se marca **impacto en materiales** y la previsión se recalcula.
- Las fotos tomadas para una nota quedan como evidencia, con fecha y hora.

## Contexto Tucumán

Lo que más pesa en Tucumán son las lluvias del verano: el reporte las registra con detalle porque justifican prórrogas de plazo y cambian el ritmo de consumo de materiales. Los datos de esta sección son conocimiento general, no consultado en fuentes; hay que validarlos con los DT del estudio.

| Factor | Qué registra o hace el sistema |
| --- | --- |
| Lluvias concentradas aprox. de noviembre a marzo, con tormentas fuertes por la tarde | Clima mañana/tarde por separado, mm de lluvia y días perdidos por terreno anegado después de la lluvia |
| Calor intenso en verano y heladas en invierno | Alerta antes de hormigonar con temperaturas extremas (cuidados de curado según CIRSOC 201) |
| Zona sísmica (INPRES-CIRSOC 103) | Hito obligatorio con fotos: inspección de armaduras antes de cada hormigonado |
| Feriados: 9 de julio (nacional, con actos en Tucumán) y 24 de septiembre (Batalla de Tucumán, provincial) | Calendario laboral de la obra; esos días no cuentan como atraso |
| Personal bajo convenio UOCRA (CCT 76/75) | Categorías fijas: oficial especializado, oficial, medio oficial, ayudante, sereno |
| Zafra azucarera (aprox. mayo a noviembre) | Posible demora de fletes y más tránsito pesado; sumar margen al plazo de entrega |
| Hornos de ladrillo común que paran con lluvia | En temporada de lluvias, sumar margen a los pedidos de ladrillo común |
| Hormigón elaborado | Programar con 24 a 48 h; el bot pide confirmación de la planta el día anterior |

Preguntas para los DT: qué proveedores fallan más en temporada de lluvias, y con qué margen piden hoy cada material.

## Previsión de materiales

El sistema calcula para cada material la fecha límite en que hay que pedirlo y le avisa al DT antes de que llegue. Usa tres datos: cuándo empieza la tarea que lo consume (cronograma), cuánto queda en obra (reportes) y cuánto tarda el proveedor (plazo de entrega).

```
fecha límite de pedido = inicio de la tarea − plazo de entrega − margen de seguridad
```

El margen de seguridad arranca en 2 días hábiles y se ajusta según temporada de lluvias, zafra y la historia real de cada proveedor.

| Nivel | Condición | Qué hace el bot |
| --- | --- | --- |
| Verde | Faltan más de 7 días para la fecha límite | Nada; aparece en el reporte semanal |
| Amarillo | La fecha límite cae dentro de los próximos 7 días | Lo incluye en "pedidos de la semana" del lunes |
| Rojo | Fecha límite vencida, o stock menor a 2 días de consumo | Mensaje al DT ese día, con botones |
| Crítico | Rojo en una tarea de camino crítico | Mensaje al DT y al director de proyectos |

### Interacción con el DT

1. **Al cerrar el día**, el bot pregunta el stock de uno o dos materiales que se usan en los próximos 10 días, no de todos: "¿Cuántas bolsas de cemento quedan?"
2. **Foto del remito**: el bot lee material, cantidad y proveedor, pide confirmación y lo carga como ingreso.
3. **Lunes 8:00**: "pedidos de la semana" con botones *Ya pedido* / *Pedir* / *No aplica*.
4. **Ya pedido**: el bot pregunta la fecha de entrega prometida. El día de entrega pregunta "¿Llegó?". Si no llegó, avisa al director.
5. **Atraso o adelanto de obra**: si el avance real se aleja del previsto, el bot corre las fechas de consumo y recalcula las alertas.
6. **Aprendizaje**: cada entrega registra el plazo real del proveedor, y la previsión usa ese dato en lugar del teórico.

## Salidas

Cada reporte confirmado genera dos salidas a partir de los mismos datos: un PDF para el director de proyectos y filas para la planilla de seguimiento del director y de gerencia.

### PDF para el director de proyectos

1. Encabezado: obra, N° de reporte, fecha, DT.
2. Resumen de 3 líneas: qué se hizo, qué preocupa y qué se necesita.
3. Alertas: materiales en rojo o crítico, notas vencidas, desvíos de más del 10 %.
4. Condiciones y jornada.
5. Avance: real contra previsto por tarea.
6. Personal por empresa y categoría.
7. Materiales: ingresos y faltantes.
8. Notas de obra abiertas, con texto literal.
9. Higiene y seguridad e incidencias.
10. Fotos: 2 por fila, con tarea, descripción y hora.
11. Próximos pasos y confirmación del DT con fecha y hora.

### Tabla para la planilla de seguimiento

La planilla tiene una pestaña por tipo de dato, y cada reporte agrega filas. Así se puede filtrar y cruzar entre obras sin copiar a mano. Se escribe directo en Google Sheets, igual que el sistema de horas, y también se puede bajar como Excel.

| Pestaña | Una fila por | Columnas |
| --- | --- | --- |
| Diario | Obra y día | fecha, obra, n_reporte, dt, clima_manana, clima_tarde, lluvia_mm, jornada, horas_perdidas, causa, personal_total, avance_real_pct, avance_previsto_pct, desvio_pct, alertas_rojas, notas_abiertas, link_pdf |
| Avance | Tarea y día | fecha, obra, id_tarea, rubro, tarea, pct_real, pct_previsto, desvio_pct, fotos |
| Materiales | Material y día | fecha, obra, material, unidad, stock, ingreso, remito, proveedor, fecha_limite_pedido, nivel_alerta, estado_pedido |
| Notas | Nota | n_nota, tipo, obra, fecha, emisor, destinatario, asunto, plazo, estado, impacto_materiales |

Ejemplo de fila de la pestaña Diario:

```csv
fecha,obra,n_reporte,dt,clima_manana,clima_tarde,lluvia_mm,jornada,horas_perdidas,causa,personal_total,avance_real_pct,avance_previsto_pct,desvio_pct,alertas_rojas,notas_abiertas,link_pdf
2026-10-12,Casa Gutiérrez,47,DT Obra 1,Soleado,Tormenta,18,Parcial,3,Lluvia,9,42,45,-3,1,2,https://...
```

Pregunta abierta: si la planilla actual del director y de gerencia ya tiene columnas definidas, la tabla se adapta a esas.

## Infraestructura y canal

El sistema vive en un VPS y el núcleo no depende del canal. El piloto corre en WhatsApp con el número de prueba gratuito de Meta (hasta 5 teléfonos), y Telegram queda como alternativa.

### Por qué un VPS

- El canal de chat avisa cada mensaje a una URL pública con HTTPS, que tiene que estar encendida las 24 h.
- Corre las tareas programadas: aviso de cierre a las 18 h, pedidos del lunes y recordatorios de notas.
- Transcribe los audios con la API de OpenAI (fracciones de centavo por minuto), sin cargar el servidor; o en el propio servidor con faster-whisper si tiene recursos.
- Guarda fotos, PDFs y la base de datos con control del estudio, lo que protege la confidencialidad de la información de obra.
- Tamaño de partida: 2 vCPU, 4 GB de RAM y 80 GB de disco (aproximado; depende de cuántas obras y fotos haya).

### WhatsApp o Telegram

| Criterio | Telegram | WhatsApp (Cloud API oficial) |
| --- | --- | --- |
| Puesta en marcha | Minutos: se crea el bot con BotFather | Días: verificación del negocio en Meta y número dedicado |
| Costo por mensaje | Gratis | Gratis si responde dentro de las 24 h; los avisos que inicia el bot se pagan por plantilla |
| Botones y menús | Completos y flexibles | Hasta 3 botones o una lista por mensaje |
| Grupos de obra | Sí | Limitado |
| Uso entre DT y gremios en Argentina | Bajo: hay que instalarlo | Universal |
| Riesgo | Bajo | Bajo con la API oficial; alto con librerías no oficiales (bloqueo del número) |

### Modos de funcionamiento

El bot es un asistente que responde: **solo actúa cuando el DT le escribe**. Si el DT no manda ningún mensaje ni reporte, el bot no puede avisarle nada. El estudio elige uno de estos tres modos:

| Modo | Cómo funciona | Costo de mensajería | Limitación |
| --- | --- | --- | --- |
| A. WhatsApp, el DT inicia (recomendado) | El DT escribe primero cada día; el bot responde y en esas respuestas incluye avisos y preguntas de materiales | Gratis | Si el DT no escribe, no recibe avisos |
| B. WhatsApp, el bot también inicia | Como A, más recordatorios que el bot manda por su cuenta (DT sin reportar, pedidos vencidos) | Gratis dentro de las 24 h desde el último mensaje del DT; fuera de esa ventana, unos centavos de dólar por mensaje con plantilla aprobada por Meta (aprox. 1 a 4 USD por mes para 5 a 10 DT) | Fuera de la ventana, el aviso usa el texto fijo de la plantilla |
| C. Telegram | El bot puede escribir primero cuando quiera | Gratis | Cada DT tiene que instalar Telegram y usarlo para la obra |

Cómo se cubren los avisos sin costo en el modo A:

- A la mañana, cuando el DT pregunta qué hay en el cronograma, el bot responde las tareas del día y agrega las alertas de materiales ("el jueves arranca el contrapiso y no hay cemento pedido").
- Al cierre del reporte, el bot pregunta los materiales de la semana siguiente. El viernes adelanta lo del lunes.
- Del modo A se puede pasar al B en cualquier momento sin cambiar el resto del sistema.

Requisito para el estudio: **cada DT escribe al bot al menos una vez por día de obra**, con la consulta de la mañana o con el reporte.

Piloto: modo A con el número de prueba de Meta y 1 o 2 DT durante 3 a 4 semanas. Producción: número propio del estudio, con la cuenta de WhatsApp Business en el portfolio del estudio.

### Herramientas del bot

| Herramienta | Qué hace |
| --- | --- |
| `elegir_obra` | Lista las obras del DT y fija la obra activa del día |
| `buscar_tarea` | Encuentra en el cronograma la tarea que el DT describe |
| `registrar_avance` | Carga el % real de una tarea y calcula el desvío |
| `registrar_personal` | Carga empresa, categoría UOCRA, cantidad y horas |
| `asignar_foto` | Describe la foto y la vincula a una tarea o nota |
| `leer_remito` | Extrae material, cantidad y proveedor de la foto de un remito |
| `registrar_nota` | Guarda una nota de obra con su texto literal |
| `consultar_clima` | Trae el clima del día según la ubicación de la obra |
| `consultar_stock` | Pregunta el stock de los materiales próximos a usarse |
| `pedir_dato_faltante` | Pregunta un campo obligatorio vacío |
| `cerrar_reporte` | Muestra el resumen, espera confirmación y genera las salidas |

## MVP y próximos pasos

El MVP es el reporte diario completo con una sola obra piloto en WhatsApp (modo A). La previsión de materiales entra en la segunda etapa, cuando ya haya stock y avance reales para alimentarla.

**Etapa 1: reporte diario (piloto)**

- [ ] Bot de WhatsApp (número de prueba) en el VPS, con elección de obra
- [ ] Fotos y audios, con transcripción en el servidor
- [ ] Carga del cronograma exportado de MS Project
- [ ] Clima automático con confirmación del DT
- [ ] Notas de obra con texto literal y estado
- [ ] PDF del director y filas en Google Sheets

**Etapa 2: previsión de materiales**

- [ ] Materiales y plazos de entrega en el cronograma
- [ ] Lectura de remitos y preguntas de stock
- [ ] Alertas por nivel y "pedidos de la semana"

**Etapa 3: escala**

- [ ] Número de WhatsApp propio del estudio y verificación del negocio
- [ ] Todas las obras y DT del estudio
- [ ] Conexión con el gestor de proyectos (junto con el sistema de horas)

**Lo que hace falta del estudio para empezar**

- [ ] Un reporte o auditoría de DT actual, como modelo
- [ ] Un cronograma real en MS Project
- [ ] Las columnas actuales de la planilla de seguimiento del director y de gerencia
- [ ] Qué DT y qué obra hacen el piloto
- [ ] Plazos de entrega habituales de los principales proveedores
