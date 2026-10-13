# obra-report-w

Asistente de reporte diario de obra por WhatsApp para directores técnicos (DT).

El DT manda fotos y audios del día; el bot arma un reporte estándar vinculado al cronograma de obra, genera un PDF para el director de proyectos y filas para la planilla de seguimiento de gerencia, y anticipa los pedidos de materiales para que la obra no se detenga.

![Flujo diario del DT](docs/img/flujo-diario.png)

## Documentación

- [Estándar del reporte diario](docs/ESTANDAR_REPORTE_DIARIO.md): campos del reporte, notas de obra, contexto Tucumán, previsión de materiales, salidas, infraestructura, modos de funcionamiento y MVP.
- [Demo en Telegram](docs/DEMO_TELEGRAM.md): cómo levantarlo y guion para mostrarlo.

## Estructura

| Archivo | Qué hace |
|---|---|
| `obra_bot/telegram_bot.py` | Canal Telegram: texto, audios, fotos, botones y recordatorio de las 18 h |
| `obra_bot/agente.py` | Conversación con Claude y descripción automática de fotos |
| `obra_bot/herramientas.py` | Herramientas que usa Claude para cargar el reporte |
| `obra_bot/reporte.py` | Borrador del día, campos faltantes y confirmación |
| `obra_bot/cronograma.py` | Cronograma, días hábiles, avance previsto y alertas de materiales |
| `obra_bot/salidas.py` | PDF para el director y filas de la planilla de seguimiento |
| `obra_bot/clima.py` | Clima del día por ubicación (Open-Meteo) |
| `obra_bot/transcripcion.py` | Audios a texto (faster-whisper local o Groq) |
| `scripts/seed_demo.py` | Dos obras demo en Tucumán con cronograma |

## Estado

Demo funcional en Telegram. Próximo paso: canal WhatsApp Cloud API cuando Meta apruebe la verificación del negocio.
