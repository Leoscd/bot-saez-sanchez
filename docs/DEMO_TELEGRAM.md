# Demo en Telegram

El bot corre en tu PC (o en el VPS) con *long polling*: no necesita dominio, HTTPS ni webhook. Se usa mientras Meta aprueba la verificación del negocio para WhatsApp; el núcleo es el mismo.

## 1. Crear el bot en Telegram (2 minutos)

1. En Telegram, abrí **@BotFather** y mandá `/newbot`.
2. Nombre: por ejemplo `Reportes de Obra (demo)`.
3. Usuario: tiene que terminar en `bot`, por ejemplo `reportes_obra_demo_bot`.
4. BotFather te da un **token**. Copialo directo al archivo `.env` (paso 3). No lo pegues en chats ni capturas.

## 2. API key de OpenAI

En [platform.openai.com](https://platform.openai.com) → **API keys** → crear una key y pegarla en `.env` como `OPENAI_API_KEY`. La misma key se usa para el chat, la descripción de fotos y la transcripción de audios. La cuenta necesita saldo cargado (Billing).

Para usar Claude en lugar de OpenAI: `LLM_PROVIDER=anthropic` y `ANTHROPIC_API_KEY`.

## 3. Instalar y configurar

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Completá en `.env` al menos `TELEGRAM_BOT_TOKEN` y `OPENAI_API_KEY`.

## 4. Cargar las obras demo y arrancar

```bash
.venv\Scripts\python scripts\seed_demo.py
.venv\Scripts\python main.py
```

El seed crea dos obras ficticias en Tucumán con cronogramas fechados alrededor de hoy (volver a correrlo antes de cada demo para que las fechas sigan vigentes).

## 5. Probarlo

1. En Telegram, buscá tu bot y mandá `/start`. Elegí la obra.
2. Preguntá "¿qué tenemos hoy?" o usá `/hoy`: responde las tareas del cronograma y las alertas de materiales.
3. Mandá fotos y audios contando el día.
4. Escribí "cerrar" o usá `/cerrar`: el bot pide lo que falta, muestra el resumen y el botón **Confirmar y enviar**.
5. Al confirmar, llega el PDF al chat y se agregan filas a `data/salidas/planilla_seguimiento.xlsx`.

Para que el director reciba una copia de cada PDF: que le escriba `/start` al bot, buscar su `chat_id` (por ejemplo con @userinfobot) y ponerlo en `DIRECTOR_CHAT_ID`.

## Guion para mostrar en una reunión (5 minutos)

1. `/start` → elegir **Casa Lomas de Tafí (demo)**.
2. "¿Qué tenemos hoy?" → mampostería de planta baja en curso y una **alerta crítica**: las viguetas de la losa ya tendrían que estar pedidas.
3. Responder "las viguetas las pedí ayer, llegan el lunes" → el bot registra el pedido y la alerta desaparece.
4. Audio: "Hoy estuvimos tres oficiales y dos ayudantes del equipo propio, avanzamos la mampostería de planta baja, calculo que vamos por el sesenta por ciento. A la tarde llovió y perdimos dos horas."
5. Tres fotos de obra (o del remito de un corralón): el bot las describe y las vincula a la tarea.
6. Orden de servicio por texto: "Orden de servicio al contratista: rehacer el tramo de muro medianero norte entre ejes 2 y 3 por falta de plomo, plazo viernes."
7. "Cerrar" → confirma el clima propuesto por la API, pregunta lo que falta, muestra el resumen → **Confirmar y enviar** → llega el PDF.
8. Abrir la planilla `planilla_seguimiento.xlsx`: pestañas Diario, Avance, Materiales y Notas con las filas nuevas.

## Costos de la demo

- Telegram: gratis.
- OpenAI: unos centavos de dólar por reporte (depende de cuántos mensajes, fotos y minutos de audio haya).
- Transcripción: con OpenAI, fracciones de centavo por minuto de audio. Alternativas: `TRANSCRIPCION=local` (gratis, instalar faster-whisper) o `groq`.
