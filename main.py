"""Arranca el bot en el canal elegido.

  python main.py             Telegram (long polling: no necesita URL pública ni HTTPS)
  python main.py whatsapp    WhatsApp Cloud API (webhook: necesita una URL pública con HTTPS, ver docs/WHATSAPP.md)
"""
import logging
import os
import sys

from obra_bot import config, db, equipo, obras


def _verificar_ia():
    clave = "ANTHROPIC_API_KEY" if config.LLM_PROVIDER == "anthropic" else "OPENAI_API_KEY"
    if not os.getenv(clave):
        sys.exit(f"Falta {clave} en el archivo .env (LLM_PROVIDER={config.LLM_PROVIDER}).")


def telegram():
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("Falta TELEGRAM_BOT_TOKEN en el archivo .env (ver docs/DEMO_TELEGRAM.md).")
    from obra_bot.telegram_bot import crear_app
    app = crear_app()
    logging.info("Bot de Telegram iniciado. Ctrl+C para detenerlo.")
    app.run_polling()


def whatsapp():
    faltan = [n for n in ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_APP_SECRET",
                          "WHATSAPP_VERIFY_TOKEN") if not getattr(config, n)]
    if faltan:
        sys.exit(f"Faltan en el archivo .env: {', '.join(faltan)} (ver docs/WHATSAPP.md).")
    personas = equipo.cargar()
    if not personas:
        logging.warning("No hay nadie en %s: el bot no va a atender a ningún número "
                        "(ver scripts/equipo.py).", config.EQUIPO_FILE)
    from aiohttp import web
    from obra_bot.whatsapp_bot import crear_app
    logging.info("Bot de WhatsApp en el puerto %s, ruta %s, %d personas habilitadas.",
                 config.WHATSAPP_PUERTO, config.WHATSAPP_RUTA, len(personas))
    web.run_app(crear_app(), host="127.0.0.1", port=config.WHATSAPP_PUERTO, print=None)


def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    canal = (sys.argv[1] if len(sys.argv) > 1 else "telegram").lower()
    if canal not in ("telegram", "whatsapp"):
        sys.exit("Uso: python main.py [telegram|whatsapp]")
    _verificar_ia()
    obras.todas()  # falla con un mensaje claro si no se corrió el seed
    db.inicializar()
    modelo = config.CLAUDE_MODEL if config.LLM_PROVIDER == "anthropic" else config.OPENAI_MODEL
    logging.info("Modelo: %s (%s).", modelo, config.LLM_PROVIDER)
    telegram() if canal == "telegram" else whatsapp()


if __name__ == "__main__":
    main()
