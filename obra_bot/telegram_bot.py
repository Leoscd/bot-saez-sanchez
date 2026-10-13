"""Canal Telegram: recibe texto, audios y fotos del DT y los pasa al asistente."""
import logging
from datetime import datetime, time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatAction
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from . import agente, clima, config, db, obras, reporte, transcripcion

log = logging.getLogger(__name__)

AYUDA = (
    "Soy el asistente de reportes de obra.\n\n"
    "- Mandame fotos, audios o texto con lo que pasa en la obra durante el día.\n"
    "- Preguntame qué hay hoy en el cronograma o qué materiales hay que pedir.\n"
    "- Cuando termines, escribí \"cerrar\" o usá /cerrar.\n\n"
    "Comandos: /obra cambiar de obra, /hoy tareas del día, /alertas materiales a pedir, /cerrar cerrar el reporte."
)


def _hoy():
    return datetime.now(config.TZ).date()


async def _enviar(msg: Message, texto: str, **kwargs):
    for i in range(0, len(texto), 4000):  # límite de Telegram: 4096 caracteres
        await msg.reply_text(texto[i:i + 4000], **kwargs)


def _teclado_obras() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(o.nombre, callback_data=f"obra:{o.id}")]
                                 for o in obras.todas()])


async def _borrador(update: Update, context: ContextTypes.DEFAULT_TYPE) -> reporte.Borrador | None:
    """Borrador de hoy del DT. Si todavía no eligió obra hoy, la pide y devuelve None."""
    u = update.effective_user
    db.guardar_usuario(u.id, u.full_name, update.effective_chat.id)
    usuario = db.obtener_usuario(u.id)
    hoy = _hoy()
    if usuario["obra_fecha"] != hoy.isoformat() or not obras.obtener(usuario["obra_id"] or ""):
        context.user_data.setdefault("pendientes", []).append(update.effective_message)
        await update.effective_message.reply_text("¿De qué obra es?", reply_markup=_teclado_obras())
        return None
    obra = obras.obtener(usuario["obra_id"])
    b, nuevo = reporte.obtener_o_crear(obra, hoy, u.id, u.full_name, update.effective_chat.id)
    if nuevo:
        b.datos["condiciones"]["propuesto"] = await clima.del_dia(obra.lat, obra.lon, hoy)
        b.guardar()
    return b


async def _turno(msg: Message, context: ContextTypes.DEFAULT_TYPE, b: reporte.Borrador, texto: str):
    if b.estado == "confirmado":
        await msg.reply_text("El reporte de hoy ya está confirmado. Lo que mandes ahora no se agrega.")
        return
    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)
    estaba_listo = b.datos.get("listo")
    respuesta = await agente.turno(b, texto)
    if b.datos.get("listo") and not estaba_listo:
        botones = InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirmar y enviar", callback_data=f"conf:{b.id}"),
            InlineKeyboardButton("Corregir algo", callback_data=f"corr:{b.id}"),
        ]])
        await _enviar(msg, respuesta, reply_markup=botones)
    else:
        await _enviar(msg, respuesta)


# --- procesamiento por tipo de mensaje ----------------------------------------

async def _procesar(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: Message):
    b = await _borrador(update, context)
    if b is None:
        return

    if msg.voice or msg.audio:
        await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)
        archivo = await (msg.voice or msg.audio).get_file()
        destino = config.AUDIOS_DIR / f"{b.id}_{msg.message_id}.ogg"
        await archivo.download_to_drive(destino)
        try:
            texto = await transcripcion.transcribir(destino)
        except Exception:
            log.exception("Falló la transcripción")
            await msg.reply_text("No pude transcribir el audio. ¿Me lo mandás de nuevo o por texto?")
            return
        if not texto:
            await msg.reply_text("No se escuchó nada en el audio. ¿Lo repetís?")
            return
        await msg.reply_text(f"Escuché: \"{texto}\"")
        await _turno(msg, context, b, f"(audio transcripto) {texto}")

    elif msg.photo:
        await context.bot.send_chat_action(msg.chat_id, ChatAction.UPLOAD_PHOTO)
        archivo = await msg.photo[-1].get_file()
        carpeta = config.FOTOS_DIR / b.obra.id / b.fecha.isoformat()
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{msg.message_id}.jpg"
        await archivo.download_to_drive(destino)
        descripcion = await agente.describir_foto(destino)
        hora = msg.date.astimezone(config.TZ).strftime("%H:%M")
        foto_id = db.agregar_foto(b.id, str(destino), hora, descripcion)
        b.datos.setdefault("fotos_sin_revisar", []).append(
            {"id": foto_id, "hora": hora, "descripcion": descripcion})
        b.guardar()
        if msg.caption:
            await _turno(msg, context, b, f"(foto #{foto_id} con texto) {msg.caption}")
        else:
            await msg.reply_text(f"Foto #{foto_id} guardada: {descripcion}")

    elif msg.text:
        await _turno(msg, context, b, msg.text)


async def on_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _procesar(update, context, update.effective_message)


# --- comandos -------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    db.guardar_usuario(u.id, u.full_name, update.effective_chat.id)
    await update.message.reply_text(f"Hola {u.first_name}. {AYUDA}")
    await update.message.reply_text("¿En qué obra estás hoy?", reply_markup=_teclado_obras())


async def cmd_obra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Elegí la obra:", reply_markup=_teclado_obras())


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(AYUDA)


def _cmd_turno(texto: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        b = await _borrador(update, context)
        if b:
            await _turno(update.effective_message, context, b, texto)
    return handler


# --- botones --------------------------------------------------------------

async def on_boton(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    accion, valor = q.data.split(":", 1)

    if accion == "obra":
        obra = obras.obtener(valor)
        db.guardar_usuario(q.from_user.id, q.from_user.full_name, q.message.chat_id)
        db.fijar_obra(q.from_user.id, obra.id, _hoy().isoformat())
        await q.edit_message_text(f"Obra de hoy: {obra.nombre}")
        pendientes = context.user_data.pop("pendientes", [])
        for msg in pendientes:
            await _procesar(update, context, msg)
        if not pendientes:
            await q.message.reply_text("Listo. Mandame fotos, audios o preguntame qué hay hoy en el cronograma.")
        return

    b = reporte.Borrador.desde_fila(db.obtener_reporte_por_id(int(valor)))
    if b.dt_id != q.from_user.id:
        return
    if accion == "corr":
        b.datos["listo"] = False
        b.guardar()
        await q.edit_message_reply_markup(None)
        await q.message.reply_text("Decime qué hay que corregir.")
    elif accion == "conf" and b.estado != "confirmado":
        await q.edit_message_reply_markup(None)
        await context.bot.send_chat_action(q.message.chat_id, ChatAction.UPLOAD_DOCUMENT)
        pdf = reporte.confirmar(b)
        with open(pdf, "rb") as f:
            await q.message.reply_document(f, filename=pdf.name,
                                           caption=f"Reporte N° {b.numero} confirmado y cargado en la planilla.")
        if config.DIRECTOR_CHAT_ID:
            with open(pdf, "rb") as f:
                await context.bot.send_document(
                    int(config.DIRECTOR_CHAT_ID), f, filename=pdf.name,
                    caption=f"{b.obra.nombre}: reporte N° {b.numero} de {b.dt_nombre}")


# --- recordatorio ---------------------------------------------------------

async def recordatorio(context: ContextTypes.DEFAULT_TYPE):
    for fila in db.borradores_abiertos(_hoy().isoformat()):
        b = reporte.Borrador.desde_fila(fila)
        await context.bot.send_message(
            b.chat_id,
            f"Recordatorio: el reporte de hoy de {b.obra.nombre} sigue abierto. "
            "Escribí \"cerrar\" cuando quieras y te digo qué falta.",
        )


def crear_app() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("obra", cmd_obra))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("hoy", _cmd_turno("¿Qué tenemos hoy en el cronograma?")))
    app.add_handler(CommandHandler("alertas", _cmd_turno("¿Qué materiales hay que pedir?")))
    app.add_handler(CommandHandler("cerrar", _cmd_turno("Quiero cerrar el reporte de hoy.")))
    app.add_handler(CallbackQueryHandler(on_boton))
    app.add_handler(MessageHandler(
        (filters.TEXT & ~filters.COMMAND) | filters.VOICE | filters.AUDIO | filters.PHOTO, on_mensaje))

    hh, mm = (int(x) for x in config.HORA_RECORDATORIO.split(":"))
    app.job_queue.run_daily(recordatorio, time(hh, mm, tzinfo=config.TZ), days=(1, 2, 3, 4, 5, 6))  # lunes a sábado (0 = domingo)
    return app
