"""Cliente de la API de WhatsApp Cloud (Meta): textos, botones, listas, archivos, plantillas y descarga de medios."""
import logging
import mimetypes
from pathlib import Path

import httpx

from . import config

log = logging.getLogger(__name__)

# Códigos de error de la API que el bot trata aparte
FUERA_DE_LISTA = 131030  # con el número de prueba: el destinatario no está en la lista de Meta
FUERA_DE_VENTANA = 131047  # pasaron más de 24 h del último mensaje del usuario: solo se puede usar plantilla

LARGO_TEXTO = 4000  # límite de WhatsApp: 4096
LARGO_CUERPO_BOTONES = 1024
LARGO_TITULO_BOTON = 20
LARGO_TITULO_FILA = 24
LARGO_DESCRIPCION_FILA = 72
MAX_FILAS = 10


class ErrorWhatsApp(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo


def variantes_ar(wa_id: str) -> list[str]:
    """Formas de escribir un celular argentino.

    WhatsApp informa los celulares como 549 + característica + número, pero según cómo se cargó el
    destinatario en la lista de prueba, la API a veces solo acepta 54 + número o 54 + característica + 15 + número.
    """
    if not (wa_id.startswith("549") and len(wa_id) == 13):
        return [wa_id]
    resto = wa_id[3:]
    return [wa_id, "54" + resto] + ["54" + resto[:n] + "15" + resto[n:] for n in (2, 3, 4)]


def _cortar(texto: str, largo: int) -> str:
    return texto if len(texto) <= largo else texto[:largo - 1] + "…"


class Cliente:
    def __init__(self, http: httpx.AsyncClient | None = None):
        self.http = http or httpx.AsyncClient(timeout=60)
        self.base = f"{config.WHATSAPP_API_URL}/{config.WHATSAPP_API_VERSION}"
        self._formato: dict[str, str] = {}  # wa_id -> forma del número que aceptó la API

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}

    async def _post(self, ruta: str, **kwargs) -> dict:
        r = await self.http.post(f"{self.base}/{ruta}", headers=self._headers, **kwargs)
        try:
            datos = r.json()
        except ValueError:
            datos = {}
        if r.status_code >= 400 or "error" in datos:
            error = datos.get("error", {})
            raise ErrorWhatsApp(error.get("code", r.status_code), error.get("message", r.text[:300]))
        return datos

    async def _enviar(self, wa_id: str, cuerpo: dict) -> dict:
        candidatos = [self._formato[wa_id]] if wa_id in self._formato else variantes_ar(wa_id)
        for i, numero in enumerate(candidatos):
            try:
                datos = await self._post(f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages", json={
                    "messaging_product": "whatsapp", "recipient_type": "individual", "to": numero, **cuerpo})
            except ErrorWhatsApp as e:
                if e.codigo == FUERA_DE_LISTA and i < len(candidatos) - 1:
                    continue
                raise
            self._formato[wa_id] = numero
            return datos
        raise AssertionError("sin candidatos")

    # --- envíos ------------------------------------------------------------

    async def texto(self, wa_id: str, texto: str):
        texto = texto or "…"
        for i in range(0, len(texto), LARGO_TEXTO):
            await self._enviar(wa_id, {"type": "text",
                                       "text": {"body": texto[i:i + LARGO_TEXTO], "preview_url": False}})

    async def botones(self, wa_id: str, texto: str, botones: list[tuple[str, str]]):
        """Mensaje con hasta 3 botones (id, título). Si el texto es largo, va antes en otro mensaje."""
        if len(texto) > LARGO_CUERPO_BOTONES:
            await self.texto(wa_id, texto)
            texto = "¿Qué hacemos?"
        await self._enviar(wa_id, {"type": "interactive", "interactive": {
            "type": "button",
            "body": {"text": texto},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": bid, "title": _cortar(titulo, LARGO_TITULO_BOTON)}}
                for bid, titulo in botones[:3]
            ]},
        }})

    async def lista(self, wa_id: str, texto: str, boton: str, filas: list[tuple[str, str, str]]):
        """Lista desplegable de hasta 10 opciones (id, título, descripción)."""
        await self._enviar(wa_id, {"type": "interactive", "interactive": {
            "type": "list",
            "body": {"text": _cortar(texto, LARGO_CUERPO_BOTONES)},
            "action": {"button": _cortar(boton, LARGO_TITULO_BOTON), "sections": [{
                "title": "Opciones",
                "rows": [{"id": fid, "title": _cortar(titulo, LARGO_TITULO_FILA),
                          "description": _cortar(desc, LARGO_DESCRIPCION_FILA)}
                         for fid, titulo, desc in filas[:MAX_FILAS]],
            }]},
        }})

    async def subir(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        datos = await self._post(f"{config.WHATSAPP_PHONE_NUMBER_ID}/media",
                                 data={"messaging_product": "whatsapp", "type": mime},
                                 files={"file": (path.name, path.read_bytes(), mime)})
        return datos["id"]

    async def documento(self, wa_id: str, path: Path, leyenda: str = ""):
        media_id = await self.subir(path)
        await self._enviar(wa_id, {"type": "document",
                                   "document": {"id": media_id, "filename": path.name, "caption": leyenda}})

    async def imagen(self, wa_id: str, path: Path, leyenda: str = ""):
        media_id = await self.subir(path)
        cuerpo = {"id": media_id, **({"caption": leyenda} if leyenda else {})}
        await self._enviar(wa_id, {"type": "image", "image": cuerpo})

    async def plantilla(self, wa_id: str, nombre: str, parametros: list[str], idioma: str = "es_AR"):
        plantilla = {"name": nombre, "language": {"code": idioma}}
        if parametros:
            plantilla["components"] = [
                {"type": "body", "parameters": [{"type": "text", "text": p} for p in parametros]}]
        await self._enviar(wa_id, {"type": "template", "template": plantilla})

    async def marcar_leido(self, message_id: str):
        """Tilde azul e indicador de "escribiendo…". Si falla no importa."""
        try:
            await self._post(f"{config.WHATSAPP_PHONE_NUMBER_ID}/messages", json={
                "messaging_product": "whatsapp", "status": "read", "message_id": message_id,
                "typing_indicator": {"type": "text"}})
        except (ErrorWhatsApp, httpx.HTTPError) as e:
            log.debug("No se pudo marcar como leído: %s", e)

    # --- medios recibidos ----------------------------------------------------

    async def descargar(self, media_id: str, destino: Path) -> Path:
        r = await self.http.get(f"{self.base}/{media_id}", headers=self._headers)
        r.raise_for_status()
        url = r.json()["url"]
        archivo = await self.http.get(url, headers=self._headers)
        archivo.raise_for_status()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(archivo.content)
        return destino
