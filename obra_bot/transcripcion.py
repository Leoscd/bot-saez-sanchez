"""Transcripción de audios del DT: faster-whisper local o API de Groq."""
import asyncio
from pathlib import Path

import httpx

from . import config

_modelo = None


def _local(path: Path) -> str:
    global _modelo
    if _modelo is None:
        from faster_whisper import WhisperModel  # import diferido: es pesado
        _modelo = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    segmentos, _ = _modelo.transcribe(str(path), language="es", vad_filter=True)
    return " ".join(s.text.strip() for s in segmentos).strip()


async def _groq(path: Path) -> str:
    async with httpx.AsyncClient(timeout=120) as http:
        with open(path, "rb") as f:
            r = await http.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                data={"model": "whisper-large-v3-turbo", "language": "es"},
                files={"file": (path.name, f)},
            )
        r.raise_for_status()
        return r.json()["text"].strip()


async def transcribir(path: Path) -> str:
    if config.TRANSCRIPCION == "groq":
        return await _groq(path)
    return await asyncio.to_thread(_local, path)
