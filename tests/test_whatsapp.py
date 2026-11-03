"""Canal WhatsApp de punta a punta contra una API de Meta simulada.

El modelo de IA se reemplaza por un doble que usa las herramientas reales: así se prueban el webhook,
la elección de obra, fotos, audios, botones, PDF, envío de fotos de consulta y recordatorios.
"""
import asyncio
import hashlib
import hmac
import io
import itertools
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from obra_bot import agente, config, db, equipo, herramientas, transcripcion, whatsapp_bot
from obra_bot.whatsapp_api import Cliente

DT = "5493815550000"  # dado de alta en dos obras
DT_UNA_OBRA = "5493815550001"
_ids = itertools.count(1)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 100, 80)).save(buf, "JPEG")
    return buf.getvalue()


class MetaFalsa:
    """Imita los endpoints de la Cloud API que usa el bot y guarda lo que se envió."""

    def __init__(self):
        self.enviados: list[dict] = []
        self.subidos = 0
        self.lista_de_prueba: set[str] | None = None  # si hay lista, a los demás responde 131030
        self.fuera_de_ventana = False  # responde 131047 a los textos

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_post("/v25.0/111/messages", self.mensajes)
        app.router.add_post("/v25.0/111/media", self.media)
        app.router.add_get("/v25.0/{media_id}", self.info_media)
        app.router.add_get("/descarga/{media_id}", self.descarga)
        return app

    async def mensajes(self, request):
        assert request.headers["Authorization"] == "Bearer token-de-prueba"
        cuerpo = await request.json()
        if cuerpo.get("status") == "read":
            return web.json_response({"success": True})
        if self.lista_de_prueba is not None and cuerpo["to"] not in self.lista_de_prueba:
            return web.json_response({"error": {"code": 131030, "message": "not in allowed list"}}, status=400)
        if self.fuera_de_ventana and cuerpo["type"] == "text":
            return web.json_response({"error": {"code": 131047, "message": "re-engagement"}}, status=400)
        self.enviados.append(cuerpo)
        return web.json_response({"messages": [{"id": f"wamid.out{next(_ids)}"}]})

    async def media(self, request):
        await request.post()
        self.subidos += 1
        return web.json_response({"id": f"media{self.subidos}"})

    async def info_media(self, request):
        return web.json_response({"url": f"{request.url.origin()}/descarga/{request.match_info['media_id']}"})

    async def descarga(self, request):
        return web.Response(body=_jpeg() if request.match_info["media_id"].startswith("img") else b"OggS")

    def de_tipo(self, tipo):
        return [e for e in self.enviados if e["type"] == tipo]

    def textos(self):
        return [e["text"]["body"] for e in self.de_tipo("text")]


async def agente_falso(b, mensaje):
    """Doble del modelo: usa las herramientas reales según palabras clave del mensaje."""
    ej = lambda nombre, **args: herramientas.ejecutar(b, nombre, args)  # noqa: E731
    if "cargá todo" in mensaje:
        ej("registrar_condiciones", clima_manana="soleado", clima_tarde="soleado", terreno="seco",
           confirmado_por_dt=True)
        ej("registrar_jornada", tipo="completa")
        ej("registrar_personal", empresa="propio", categoria="oficial", cantidad=2)
        ej("registrar_avance", id_tarea="T-040", descripcion="Contrafrente", pct_real=45)
        ej("registrar_hys", epp_ok=True)
        ej("cerrar_reporte", resumen="Se avanzó mampostería.\nPreocupa el ladrillo.\nFalta hierro.")
        return "Está todo. ¿Confirmo?"
    if "cómo viene" in mensaje:
        resumen = json.loads(ej("resumen_obra"))
        foto = json.loads(ej("fotos_recientes", cantidad=1))[0]
        ej("enviar_fotos", foto_ids=[foto["foto_id"]])
        return f"Avance real {resumen['avance_real_pct']}% contra {resumen['avance_previsto_pct']}% previsto."
    return f"Recibido: {mensaje[-60:]}"


@pytest.fixture
def meta(monkeypatch):
    monkeypatch.setattr(agente, "turno", agente_falso)

    async def describir(path):
        return "Mampostería de ladrillo hueco"

    async def transcribir(path):
        return "hoy vinieron dos oficiales"

    monkeypatch.setattr(agente, "describir_foto", describir)
    monkeypatch.setattr(transcripcion, "transcribir", transcribir)
    equipo.guardar([
        equipo.Persona(DT, "Martín Test", {"casa-lomas": None, "local-mate-de-luna": "2099-12-31"}),
        equipo.Persona(DT_UNA_OBRA, "Lucía Test", {"local-mate-de-luna": None}),
    ])
    with db.conexion() as con:  # cada prueba arranca sin obra elegida ni borradores de hoy
        con.execute("DELETE FROM usuarios WHERE usuario_id LIKE 'wa:%'")
        con.execute("DELETE FROM reportes WHERE dt_id LIKE 'wa:%'")
    return MetaFalsa()


def _firmar(cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(b"secreto-de-prueba", cuerpo, hashlib.sha256).hexdigest()


def _evento(numero: str, **mensaje) -> dict:
    m = {"from": numero, "id": f"wamid.in{next(_ids)}", "timestamp": "1793700000", **mensaje}
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "contacts": [{"wa_id": numero, "profile": {"name": "DT"}}],
        "messages": [m]}}]}]}


def texto(numero, body):
    return _evento(numero, type="text", text={"body": body})


def foto(numero, caption=""):
    return _evento(numero, type="image", image={"id": f"img{next(_ids)}", "mime_type": "image/jpeg",
                                                 **({"caption": caption} if caption else {})})


def audio(numero):
    return _evento(numero, type="audio", audio={"id": f"aud{next(_ids)}", "mime_type": "audio/ogg", "voice": True})


def boton(numero, boton_id, tipo="button_reply"):
    return _evento(numero, type="interactive", interactive={"type": tipo, tipo: {"id": boton_id, "title": "x"}})


class Escenario:
    def __init__(self, meta: MetaFalsa):
        self.meta = meta

    async def __aenter__(self):
        self.servidor_meta = TestServer(self.meta.app())
        await self.servidor_meta.start_server()
        config.WHATSAPP_API_URL = str(self.servidor_meta.make_url("")).rstrip("/")
        self.bot = whatsapp_bot.BotWhatsApp(Cliente())
        self.bot.espera_aviso_fotos = 0.05
        self.cliente = TestClient(TestServer(whatsapp_bot.crear_app(self.bot, recordatorios=False)))
        await self.cliente.start_server()
        return self

    async def __aexit__(self, *exc):
        await self.cliente.close()
        await self.servidor_meta.close()

    async def enviar(self, evento: dict, firma: str | None = None):
        cuerpo = json.dumps(evento).encode()
        r = await self.cliente.post(config.WHATSAPP_RUTA, data=cuerpo,
                                    headers={"X-Hub-Signature-256": firma or _firmar(cuerpo)})
        await self.bot.esperar_tareas()
        return r


def correr(coro):
    asyncio.run(coro)


def test_verificacion_del_webhook(meta):
    async def prueba():
        async with Escenario(meta) as e:
            ok = await e.cliente.get(config.WHATSAPP_RUTA, params={
                "hub.mode": "subscribe", "hub.verify_token": "verificacion-de-prueba", "hub.challenge": "1234"})
            assert ok.status == 200 and await ok.text() == "1234"
            mal = await e.cliente.get(config.WHATSAPP_RUTA, params={
                "hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "1234"})
            assert mal.status == 403
    correr(prueba())


def test_rechaza_firma_invalida(meta):
    async def prueba():
        async with Escenario(meta) as e:
            r = await e.enviar(texto(DT, "hola"), firma="sha256=falsa")
            assert r.status == 403 and not meta.enviados
    correr(prueba())


def test_numero_no_habilitado(meta):
    async def prueba():
        async with Escenario(meta) as e:
            await e.enviar(texto("5491100000000", "hola"))
            assert meta.textos() == [whatsapp_bot.NO_HABILITADO]
    correr(prueba())


def test_reporte_completo_con_eleccion_de_obra_fotos_audio_y_pdf(meta):
    async def prueba():
        async with Escenario(meta) as e:
            # Antes de elegir la obra: una sola lista aunque lleguen varios mensajes
            await e.enviar(texto(DT, "buen día"))
            await e.enviar(foto(DT))
            listas = meta.de_tipo("interactive")
            assert len(listas) == 1 and listas[0]["interactive"]["type"] == "list"
            filas = listas[0]["interactive"]["action"]["sections"][0]["rows"]
            assert {f["id"] for f in filas} == {"obra:casa-lomas", "obra:local-mate-de-luna"}
            assert all(len(f["title"]) <= 24 for f in filas)

            # Al elegir la obra se procesan los mensajes pendientes
            await e.enviar(boton(DT, "obra:casa-lomas", tipo="list_reply"))
            assert "Obra de hoy: Casa Lomas de Tafí (demo)" in meta.textos()
            assert "Recibido: buen día" in meta.textos()
            assert any(t.startswith("Foto #") for t in meta.textos())

            await e.enviar(audio(DT))
            assert 'Escuché: "hoy vinieron dos oficiales"' in meta.textos()

            await e.enviar(texto(DT, "cargá todo y cerralo"))
            botones = meta.de_tipo("interactive")[-1]["interactive"]
            assert botones["type"] == "button"
            conf = botones["action"]["buttons"][0]["reply"]["id"]
            assert conf.startswith("conf:")

            await e.enviar(boton(DT, conf))
            doc = meta.de_tipo("document")[-1]["document"]
            assert doc["filename"].endswith(".pdf") and "confirmado" in doc["caption"]
            fila = db.obtener_reporte_por_id(int(conf.split(":")[1]))
            assert fila["estado"] == "confirmado" and fila["numero"] == 6  # 5 reportes demo antes

            # Apretar Confirmar dos veces no genera otro reporte
            await e.enviar(boton(DT, conf))
            assert meta.textos()[-1].startswith("El reporte N° 6 ya estaba confirmado")
    correr(prueba())


def test_consulta_de_reemplazo_manda_brief_y_fotos(meta):
    async def prueba():
        async with Escenario(meta) as e:
            await e.enviar(texto(DT_UNA_OBRA, "estoy en un reemplazo, contame cómo viene la obra"))
            textos = meta.textos()
            assert textos[0] == "Obra de hoy: Local Av. Mate de Luna (demo)."  # una sola obra: se elige sola
            assert textos[1].startswith("Avance real")
            assert len(meta.de_tipo("image")) == 1 and meta.subidos == 1
    correr(prueba())


def test_obra_no_asignada_y_reemplazo_vencido(meta):
    async def prueba():
        async with Escenario(meta) as e:
            await e.enviar(boton(DT_UNA_OBRA, "obra:casa-lomas", tipo="list_reply"))
            assert meta.textos()[-1] == "Esa obra no la tenés asignada hoy."
            equipo.guardar([equipo.Persona(DT, "Martín Test", {"casa-lomas": "2020-01-01"})])
            await e.enviar(texto(DT, "hola"))
            assert meta.textos()[-1] == whatsapp_bot.SIN_OBRAS
    correr(prueba())


def test_numero_argentino_con_15_en_la_lista_de_prueba(meta):
    meta.lista_de_prueba = {"54381155550001"}  # cargado en Meta como 381 15 555-0001

    async def prueba():
        async with Escenario(meta) as e:
            await e.enviar(texto(DT_UNA_OBRA, "hola"))
            assert {m["to"] for m in meta.enviados} == {"54381155550001"}
    correr(prueba())


def test_varias_fotos_se_confirman_en_un_solo_mensaje(meta):
    async def prueba():
        async with Escenario(meta) as e:
            e.bot.espera_aviso_fotos = 0.5
            await e.enviar(texto(DT_UNA_OBRA, "hola"))
            antes = len(meta.textos())
            # Las tres llegan juntas, como cuando el DT elige varias fotos de la galería
            await asyncio.gather(*(e.enviar(foto(DT_UNA_OBRA)) for _ in range(3)))
            nuevos = meta.textos()[antes:]
            assert len(nuevos) == 1 and nuevos[0].startswith("Recibí 3 fotos:")
    correr(prueba())


def test_si_el_dt_escribe_enseguida_no_hay_aviso_de_fotos(meta):
    async def prueba():
        async with Escenario(meta) as e:
            e.bot.espera_aviso_fotos = 5
            await e.enviar(texto(DT_UNA_OBRA, "hola"))
            antes = len(meta.textos())
            cuerpo = json.dumps(foto(DT_UNA_OBRA)).encode()
            await e.cliente.post(config.WHATSAPP_RUTA, data=cuerpo, headers={"X-Hub-Signature-256": _firmar(cuerpo)})
            await e.enviar(texto(DT_UNA_OBRA, "esa es la mampostería"))
            assert meta.textos()[antes:] == ["Recibido: esa es la mampostería"]
    correr(prueba())


def test_mensaje_repetido_por_meta_se_procesa_una_vez(meta):
    async def prueba():
        async with Escenario(meta) as e:
            evento = texto(DT_UNA_OBRA, "primer mensaje")
            await e.enviar(evento)
            await e.enviar(evento)
            assert meta.textos().count("Recibido: primer mensaje") == 1
    correr(prueba())


def test_recordatorio_usa_plantilla_fuera_de_las_24_horas(meta, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_PLANTILLA_RECORDATORIO", "recordatorio_reporte")

    async def prueba():
        async with Escenario(meta) as e:
            await e.enviar(foto(DT_UNA_OBRA))  # deja un borrador con datos
            meta.fuera_de_ventana = True
            await e.bot.recordar()
            plantilla = meta.de_tipo("template")[-1]["template"]
            assert plantilla["name"] == "recordatorio_reporte"
            assert plantilla["components"][0]["parameters"][0]["text"] == "Local Av. Mate de Luna (demo)"
    correr(prueba())


def test_horario_del_recordatorio():
    from datetime import datetime
    sabado_19 = datetime(2026, 11, 7, 19, 0, tzinfo=config.TZ)
    # El próximo es el lunes a las 18 (el domingo no hay)
    assert whatsapp_bot.segundos_hasta_recordatorio(sabado_19) == (24 * 2 - 1) * 3600
