"""Canal WhatsApp (Cloud API de Meta): webhook que recibe los mensajes y responde por la API.

Meta llama a WHATSAPP_RUTA: GET una vez para verificar el webhook y POST con cada mensaje. El bot
contesta 200 enseguida y procesa el mensaje aparte, de a uno por usuario para no pisar el borrador.
Solo atiende a los números cargados en data/equipo.json, y a cada uno en sus obras habilitadas.
"""
import asyncio
import hashlib
import hmac
import json
import logging
from collections import OrderedDict
from datetime import datetime, timedelta

from aiohttp import web

from . import config, db, equipo, nucleo, obras, reporte
from .whatsapp_api import FUERA_DE_VENTANA, Cliente, ErrorWhatsApp

log = logging.getLogger(__name__)

NO_HABILITADO = ("Hola. Este es el asistente de reportes de obra del estudio. Tu número no está habilitado: "
                 "pedile a la oficina que te den de alta.")
SIN_OBRAS = "No tenés obras asignadas hoy. Pedile a la oficina que te asignen la obra."
NO_SOPORTADO = "Por ahora proceso texto, audios y fotos. ¿Me lo mandás de alguna de esas formas?"
ERROR = "Tuve un problema técnico con ese mensaje. Probá de nuevo en un rato."
PEDIR_AYUDA = {"ayuda", "/ayuda", "/start", "menu", "menú"}
CAMBIAR_OBRA = {"obra", "/obra", "cambiar obra", "cambiar de obra", "otra obra"}
MAX_VISTOS = 2000
# Las fotos sin texto se confirman juntas en un solo mensaje cuando el DT deja de mandar por unos segundos:
# cada mensaje del bot cuenta para el cupo mensual gratis de WhatsApp
ESPERA_AVISO_FOTOS = 8.0


def firma_valida(cuerpo: bytes, firma: str) -> bool:
    """Meta firma cada POST con la clave secreta de la app (encabezado X-Hub-Signature-256)."""
    esperada = "sha256=" + hmac.new(config.WHATSAPP_APP_SECRET.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma or "")


def segundos_hasta_recordatorio(ahora: datetime) -> float:
    hh, mm = (int(x) for x in config.HORA_RECORDATORIO.split(":"))
    proximo = ahora.replace(hour=hh, minute=mm, second=0, microsecond=0)
    while proximo <= ahora or proximo.weekday() == 6:  # lunes a sábado
        proximo += timedelta(days=1)
    return (proximo - ahora).total_seconds()


def _nombre_archivo(message_id: str) -> str:
    return hashlib.sha1(message_id.encode()).hexdigest()[:12]


class BotWhatsApp:
    def __init__(self, api: Cliente | None = None):
        self.api = api or Cliente()
        self._locks: dict[str, asyncio.Lock] = {}
        self._pendientes: dict[str, list[dict]] = {}  # mensajes recibidos antes de elegir la obra
        self._vistos: OrderedDict[str, None] = OrderedDict()  # Meta reintenta: no procesar dos veces
        self._tareas: set[asyncio.Task] = set()
        self.espera_aviso_fotos = ESPERA_AVISO_FOTOS
        self._fotos_por_avisar: dict[str, list[tuple[int, str]]] = {}
        self._aviso_fotos: dict[str, asyncio.Task] = {}

    # --- webhook -------------------------------------------------------------

    async def verificar(self, request: web.Request) -> web.Response:
        q = request.query
        if (q.get("hub.mode") == "subscribe" and config.WHATSAPP_VERIFY_TOKEN
                and hmac.compare_digest(q.get("hub.verify_token", ""), config.WHATSAPP_VERIFY_TOKEN)):
            log.info("Webhook verificado por Meta")
            return web.Response(text=q.get("hub.challenge", ""))
        return web.Response(status=403, text="token de verificación incorrecto")

    async def recibir(self, request: web.Request) -> web.Response:
        cuerpo = await request.read()
        if not firma_valida(cuerpo, request.headers.get("X-Hub-Signature-256", "")):
            log.warning("POST al webhook con firma inválida")
            return web.Response(status=403, text="firma inválida")
        datos = json.loads(cuerpo)
        for entrada in datos.get("entry", []):
            for cambio in entrada.get("changes", []):
                valor = cambio.get("value", {})
                for m in valor.get("messages", []):
                    if not self._ya_visto(m.get("id", "")):
                        self._lanzar(self.atender(m))
                for s in valor.get("statuses", []):
                    if s.get("status") == "failed":
                        log.warning("WhatsApp no pudo entregar un mensaje a %s: %s",
                                    s.get("recipient_id"), s.get("errors"))
        return web.Response(text="ok")

    def _ya_visto(self, message_id: str) -> bool:
        if message_id in self._vistos:
            return True
        self._vistos[message_id] = None
        if len(self._vistos) > MAX_VISTOS:
            self._vistos.popitem(last=False)
        return False

    def _lanzar(self, coro) -> asyncio.Task:
        tarea = asyncio.create_task(coro)
        self._tareas.add(tarea)
        tarea.add_done_callback(self._tareas.discard)
        return tarea

    async def esperar_tareas(self):
        """Para las pruebas: espera a que terminen los mensajes en proceso."""
        while self._tareas:
            await asyncio.gather(*self._tareas, return_exceptions=True)

    # --- mensajes --------------------------------------------------------------

    async def atender(self, m: dict):
        wa_id = m["from"]
        async with self._locks.setdefault(wa_id, asyncio.Lock()):
            try:
                await self._procesar(m)
            except Exception:
                log.exception("Error procesando un mensaje de %s", wa_id)
                try:
                    await self.api.texto(wa_id, ERROR)
                except Exception:
                    log.exception("Tampoco se pudo avisar del error")

    async def _procesar(self, m: dict):
        wa_id = m["from"]
        persona = equipo.buscar(wa_id)
        if persona is None:
            log.info("Mensaje de un número no habilitado: %s", wa_id)
            await self.api.texto(wa_id, NO_HABILITADO)
            return
        await self.api.marcar_leido(m["id"])
        uid = f"wa:{wa_id}"
        permitidas = persona.obras_habilitadas(nucleo.hoy())

        if m.get("type") == "interactive":
            r = m["interactive"].get("button_reply") or m["interactive"].get("list_reply") or {}
            await self._boton(persona, uid, wa_id, r.get("id", ""), permitidas)
            return

        texto = m.get("text", {}).get("body", "").strip() if m.get("type") == "text" else ""
        if texto.lower() in PEDIR_AYUDA:
            await self.api.texto(wa_id, f"Hola {persona.nombre}. {nucleo.AYUDA}\n\n"
                                        "Para cambiar de obra escribí \"obra\".")
            return
        if texto.lower() in CAMBIAR_OBRA:
            await self._pedir_obra(wa_id, permitidas)
            return

        b = await nucleo.borrador(uid, persona.nombre, uid, permitidas)
        if b is None:
            if not permitidas:
                await self.api.texto(wa_id, SIN_OBRAS)
                return
            if len(permitidas) > 1:
                pendientes = self._pendientes.setdefault(wa_id, [])
                pendientes.append(m)
                if len(pendientes) == 1:  # una sola lista aunque lleguen varias fotos juntas
                    await self._pedir_obra(wa_id, permitidas)
                return
            obra = nucleo.elegir_obra(uid, persona.nombre, uid, permitidas[0])
            await self.api.texto(wa_id, f"Obra de hoy: {obra.nombre}.")
            b = await nucleo.borrador(uid, persona.nombre, uid, permitidas)
        await self._mensaje(b, wa_id, m)

    async def _mensaje(self, b: reporte.Borrador, wa_id: str, m: dict):
        tipo = m.get("type")
        if tipo == "document" and m["document"].get("mime_type", "").startswith("image/"):
            tipo, m = "image", {**m, "image": m["document"]}  # foto mandada como archivo

        if tipo == "text":
            await self._turno(b, wa_id, m["text"]["body"])

        elif tipo == "audio":
            destino = config.AUDIOS_DIR / f"{b.id}_{_nombre_archivo(m['id'])}.ogg"
            await self.api.descargar(m["audio"]["id"], destino)
            try:
                texto = await nucleo.transcribir(destino)
            except Exception:
                log.exception("Falló la transcripción")
                await self.api.texto(wa_id, "No pude transcribir el audio. ¿Me lo mandás de nuevo o por texto?")
                return
            if not texto:
                await self.api.texto(wa_id, "No se escuchó nada en el audio. ¿Lo repetís?")
                return
            await self.api.texto(wa_id, f"Escuché: \"{texto}\"")
            await self._turno(b, wa_id, f"(audio transcripto) {texto}")

        elif tipo == "image":
            destino = nucleo.carpeta_fotos(b) / f"{_nombre_archivo(m['id'])}.jpg"
            await self.api.descargar(m["image"]["id"], destino)
            hora = datetime.fromtimestamp(int(m.get("timestamp", 0)) or datetime.now().timestamp(),
                                          config.TZ).strftime("%H:%M")
            foto_id, descripcion = await nucleo.guardar_foto(b, destino, hora)
            leyenda = m["image"].get("caption", "").strip()
            if leyenda:
                await self._turno(b, wa_id, f"(foto #{foto_id} con texto) {leyenda}")
            else:
                self._avisar_foto(wa_id, foto_id, descripcion)

        else:
            await self.api.texto(wa_id, NO_SOPORTADO)

    def _avisar_foto(self, wa_id: str, foto_id: int, descripcion: str):
        self._fotos_por_avisar.setdefault(wa_id, []).append((foto_id, descripcion))
        anterior = self._aviso_fotos.get(wa_id)
        if anterior:
            anterior.cancel()
        self._aviso_fotos[wa_id] = self._lanzar(self._aviso_diferido(wa_id))

    async def _aviso_diferido(self, wa_id: str):
        await asyncio.sleep(self.espera_aviso_fotos)
        async with self._locks[wa_id]:
            fotos = self._fotos_por_avisar.pop(wa_id, [])
            self._aviso_fotos.pop(wa_id, None)
            if len(fotos) == 1:
                await self.api.texto(wa_id, f"Foto #{fotos[0][0]} guardada: {fotos[0][1]}")
            elif fotos:
                lineas = "\n".join(f"- #{fid}: {desc}" for fid, desc in fotos)
                await self.api.texto(wa_id, f"Recibí {len(fotos)} fotos:\n{lineas}")

    def _cancelar_aviso_fotos(self, wa_id: str):
        """El asistente ya comenta las fotos nuevas en su respuesta: no hace falta el aviso aparte."""
        tarea = self._aviso_fotos.pop(wa_id, None)
        if tarea:
            tarea.cancel()
        self._fotos_por_avisar.pop(wa_id, None)

    async def _turno(self, b: reporte.Borrador, wa_id: str, texto: str):
        self._cancelar_aviso_fotos(wa_id)
        r = await nucleo.turno(b, texto)
        if r.pedir_confirmacion:
            await self.api.botones(wa_id, r.texto, [(f"conf:{b.id}", "Confirmar y enviar"),
                                                    (f"corr:{b.id}", "Corregir algo")])
        else:
            await self.api.texto(wa_id, r.texto)
        for foto in r.fotos:
            await self.api.imagen(wa_id, foto)

    async def _pedir_obra(self, wa_id: str, permitidas: list[str]):
        if not permitidas:
            await self.api.texto(wa_id, SIN_OBRAS)
            return
        filas = [(f"obra:{o.id}", o.nombre, o.direccion) for o in obras.todas() if o.id in permitidas]
        if len(filas) > 10:
            log.warning("%s tiene %d obras habilitadas: la lista de WhatsApp muestra 10", wa_id, len(filas))
        await self.api.lista(wa_id, "¿En qué obra estás hoy?", "Elegir obra", filas)

    async def _boton(self, persona: equipo.Persona, uid: str, wa_id: str, boton_id: str, permitidas: list[str]):
        accion, _, valor = boton_id.partition(":")

        if accion == "obra":
            if valor not in permitidas:
                await self.api.texto(wa_id, "Esa obra no la tenés asignada hoy.")
                return
            obra = nucleo.elegir_obra(uid, persona.nombre, uid, valor)
            await self.api.texto(wa_id, f"Obra de hoy: {obra.nombre}")
            pendientes = self._pendientes.pop(wa_id, [])
            if not pendientes:
                await self.api.texto(wa_id, nucleo.LISTO_OBRA)
                return
            b = await nucleo.borrador(uid, persona.nombre, uid, permitidas)
            for m in pendientes:
                await self._mensaje(b, wa_id, m)
            return

        fila = db.obtener_reporte_por_id(int(valor)) if valor.isdigit() else None
        if fila is None or fila["dt_id"] != uid:
            return
        b = reporte.Borrador.desde_fila(fila)
        if accion == "corr":
            nucleo.corregir(b)
            await self.api.texto(wa_id, "Decime qué hay que corregir.")
        elif accion == "conf":
            if b.estado == "confirmado":
                await self.api.texto(wa_id, f"El reporte N° {b.numero} ya estaba confirmado.")
                return
            pdf = nucleo.confirmar(b)
            await self.api.documento(wa_id, pdf, f"Reporte N° {b.numero} confirmado y cargado en la planilla.")
            if config.WHATSAPP_DIRECTOR:
                try:
                    await self.api.documento(equipo.normalizar(config.WHATSAPP_DIRECTOR), pdf,
                                             f"{b.obra.nombre}: reporte N° {b.numero} de {b.dt_nombre}")
                except ErrorWhatsApp as e:
                    # Fuera de las 24 h del último mensaje del director, WhatsApp solo deja mandar plantillas
                    log.warning("No se pudo mandar el PDF al director: %s", e)

    # --- recordatorio ------------------------------------------------------------

    async def recordar(self):
        for b in nucleo.para_recordar():
            if not str(b.chat_id).startswith("wa:"):
                continue  # los de Telegram los recuerda su canal
            wa_id = b.chat_id[3:]
            try:
                await self.api.texto(wa_id, nucleo.texto_recordatorio(b))
            except ErrorWhatsApp as e:
                if e.codigo == FUERA_DE_VENTANA and config.WHATSAPP_PLANTILLA_RECORDATORIO:
                    await self.api.plantilla(wa_id, config.WHATSAPP_PLANTILLA_RECORDATORIO, [b.obra.nombre])
                else:
                    log.warning("No se pudo mandar el recordatorio a %s: %s", wa_id, e)

    async def ciclo_recordatorios(self):
        while True:
            await asyncio.sleep(segundos_hasta_recordatorio(datetime.now(config.TZ)))
            try:
                await self.recordar()
            except Exception:
                log.exception("Falló el recordatorio")


async def salud(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


def crear_app(bot: BotWhatsApp | None = None, recordatorios: bool = True) -> web.Application:
    bot = bot or BotWhatsApp()
    app = web.Application()
    app.router.add_get(config.WHATSAPP_RUTA, bot.verificar)
    app.router.add_post(config.WHATSAPP_RUTA, bot.recibir)
    app.router.add_get("/salud", salud)

    if recordatorios:
        async def ciclo(_app):
            tarea = asyncio.create_task(bot.ciclo_recordatorios())
            yield
            tarea.cancel()
        app.cleanup_ctx.append(ciclo)
    return app
