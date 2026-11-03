"""Lógica común a los canales (Telegram y WhatsApp): obra del día, borrador, fotos, audios, turnos y cierre.

Cada canal recibe los mensajes, llama a estas funciones y manda las respuestas con sus propios botones.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import agente, clima, config, db, obras, reporte, transcripcion

AYUDA = (
    "Soy el asistente de reportes de obra.\n\n"
    "- Mandame fotos, audios o texto con lo que pasa en la obra durante el día y armo el reporte.\n"
    "- Preguntame qué hay hoy en el cronograma o qué materiales hay que pedir.\n"
    "- Si estás haciendo un reemplazo, preguntame cómo viene la obra.\n"
    "- Cuando termines, escribí \"cerrar\" y te digo qué falta."
)
LISTO_OBRA = "Listo. Mandame fotos, audios o preguntame qué hay hoy en el cronograma o cómo viene la obra."


@dataclass
class Respuesta:
    texto: str
    pedir_confirmacion: bool = False  # mostrar los botones Confirmar / Corregir
    fotos: list[Path] = field(default_factory=list)


def hoy() -> date:
    return datetime.now(config.TZ).date()


def elegir_obra(usuario_id, nombre: str, chat_id, obra_id: str) -> obras.Obra:
    obra = obras.obtener(obra_id)
    db.guardar_usuario(usuario_id, nombre, chat_id)
    db.fijar_obra(usuario_id, obra.id, hoy().isoformat())
    return obra


async def borrador(usuario_id, nombre: str, chat_id,
                   permitidas: list[str] | None = None) -> reporte.Borrador | None:
    """Borrador de hoy del usuario. None si todavía no eligió obra hoy (o la que eligió ya no le corresponde)."""
    db.guardar_usuario(usuario_id, nombre, chat_id)
    usuario = db.obtener_usuario(usuario_id)
    dia = hoy()
    obra = obras.obtener(usuario["obra_id"] or "")
    if usuario["obra_fecha"] != dia.isoformat() or not obra:
        return None
    if permitidas is not None and obra.id not in permitidas:
        return None
    b, nuevo = reporte.obtener_o_crear(obra, dia, usuario_id, nombre, chat_id)
    if nuevo:
        b.datos["condiciones"]["propuesto"] = await clima.del_dia(obra.lat, obra.lon, dia)
        b.guardar()
    return b


async def transcribir(path: Path) -> str:
    """Texto del audio. Lanza excepción si falla el servicio de transcripción."""
    return await transcripcion.transcribir(path)


def carpeta_fotos(b: reporte.Borrador) -> Path:
    carpeta = config.FOTOS_DIR / b.obra.id / b.fecha.isoformat()
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


async def guardar_foto(b: reporte.Borrador, path: Path, hora: str) -> tuple[int, str]:
    """Describe la foto, la registra en el reporte y la deja para que el asistente la vincule."""
    descripcion = await agente.describir_foto(path)
    foto_id = db.agregar_foto(b.id, str(path), hora, descripcion)
    b.datos.setdefault("fotos_sin_revisar", []).append({"id": foto_id, "hora": hora, "descripcion": descripcion})
    b.guardar()
    return foto_id, descripcion


async def turno(b: reporte.Borrador, texto: str) -> Respuesta:
    estaba_listo = b.datos.get("listo")
    b.salientes = []
    texto_respuesta = await agente.turno(b, texto)
    return Respuesta(
        texto=texto_respuesta,
        pedir_confirmacion=bool(b.datos.get("listo") and not estaba_listo and b.estado != "confirmado"),
        fotos=list(b.salientes),
    )


def corregir(b: reporte.Borrador):
    b.datos["listo"] = False
    b.guardar()


def confirmar(b: reporte.Borrador) -> Path:
    return reporte.confirmar(b)


def para_recordar() -> list[reporte.Borrador]:
    """Borradores de hoy abiertos que tienen algo cargado (los de solo consultas no se recuerdan)."""
    abiertos = [reporte.Borrador.desde_fila(f) for f in db.borradores_abiertos(hoy().isoformat())]
    return [b for b in abiertos if reporte.tiene_datos(b)]


def texto_recordatorio(b: reporte.Borrador) -> str:
    return (f"Recordatorio: el reporte de hoy de {b.obra.nombre} sigue abierto. "
            "Escribí \"cerrar\" cuando quieras y te digo qué falta.")
