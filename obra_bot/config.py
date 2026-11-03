"""Configuración del bot, leída del archivo .env."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env(nombre: str, default: str = "") -> str:
    return os.getenv(nombre, default).strip()


TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")

# Proveedor del modelo de IA: "openai" o "anthropic"
LLM_PROVIDER = _env("LLM_PROVIDER", "openai").lower()

OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-5.5")
OPENAI_REASONING_EFFORT = _env("OPENAI_REASONING_EFFORT", "low")
OPENAI_TRANSCRIBE_MODEL = _env("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")

CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5-5")
CLAUDE_EFFORT = _env("CLAUDE_EFFORT", "medium")

# "openai" = API de OpenAI; "local" = faster-whisper en esta máquina; "groq" = API de Groq
TRANSCRIPCION = _env("TRANSCRIPCION", "openai" if LLM_PROVIDER == "openai" else "local")
WHISPER_MODEL = _env("WHISPER_MODEL", "small")
GROQ_API_KEY = _env("GROQ_API_KEY")

# Chat de Telegram del director de proyectos: recibe una copia de cada PDF (opcional)
DIRECTOR_CHAT_ID = _env("DIRECTOR_CHAT_ID")

# WhatsApp Cloud API (developers.facebook.com > tu app > WhatsApp)
WHATSAPP_TOKEN = _env("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = _env("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_APP_SECRET = _env("WHATSAPP_APP_SECRET")
WHATSAPP_VERIFY_TOKEN = _env("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_API_VERSION = _env("WHATSAPP_API_VERSION", "v25.0")
WHATSAPP_API_URL = _env("WHATSAPP_API_URL", "https://graph.facebook.com")
WHATSAPP_PUERTO = int(_env("WHATSAPP_PUERTO", "8085"))
WHATSAPP_RUTA = _env("WHATSAPP_RUTA", "/whatsapp/webhook")
# Plantilla aprobada para el recordatorio cuando pasaron más de 24 h del último mensaje del DT (opcional)
WHATSAPP_PLANTILLA_RECORDATORIO = _env("WHATSAPP_PLANTILLA_RECORDATORIO")
# Teléfono del director de proyectos: recibe una copia de cada PDF (opcional)
WHATSAPP_DIRECTOR = _env("WHATSAPP_DIRECTOR")

HORA_RECORDATORIO = _env("HORA_RECORDATORIO", "18:00")
TZ = ZoneInfo(_env("TZ_OBRA", "America/Argentina/Tucuman"))
MIN_FOTOS = int(_env("MIN_FOTOS", "3"))
MARGEN_PEDIDO_DIAS = int(_env("MARGEN_PEDIDO_DIAS", "2"))

DATA_DIR = BASE_DIR / _env("DATA_DIR", "data")
DB_PATH = DATA_DIR / "obra_report.db"
OBRAS_FILE = DATA_DIR / "obras.json"
EQUIPO_FILE = DATA_DIR / "equipo.json"
FOTOS_DIR = DATA_DIR / "fotos"
AUDIOS_DIR = DATA_DIR / "audios"
SALIDAS_DIR = DATA_DIR / "salidas"
PLANILLA_PATH = SALIDAS_DIR / "planilla_seguimiento.xlsx"

for _d in (DATA_DIR, FOTOS_DIR, AUDIOS_DIR, SALIDAS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
