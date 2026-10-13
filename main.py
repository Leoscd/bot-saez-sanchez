"""Arranca el bot de Telegram (long polling: no necesita URL pública ni HTTPS)."""
import logging
import os
import sys

from obra_bot import config, db, obras


def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("Falta TELEGRAM_BOT_TOKEN en el archivo .env (ver docs/DEMO_TELEGRAM.md).")
    clave = "ANTHROPIC_API_KEY" if config.LLM_PROVIDER == "anthropic" else "OPENAI_API_KEY"
    if not os.getenv(clave):
        sys.exit(f"Falta {clave} en el archivo .env (LLM_PROVIDER={config.LLM_PROVIDER}).")
    obras.todas()  # falla con un mensaje claro si no se corrió el seed
    db.inicializar()

    from obra_bot.telegram_bot import crear_app
    app = crear_app()
    modelo = config.CLAUDE_MODEL if config.LLM_PROVIDER == "anthropic" else config.OPENAI_MODEL
    logging.info("Bot iniciado con %s (%s). Ctrl+C para detenerlo.", modelo, config.LLM_PROVIDER)
    app.run_polling()


if __name__ == "__main__":
    main()
