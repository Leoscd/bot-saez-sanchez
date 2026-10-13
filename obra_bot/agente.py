"""Conversación con Claude: un turno por mensaje del DT, con herramientas sobre el borrador."""
import base64
import logging
from pathlib import Path

import anthropic

from . import config, herramientas
from .reporte import Borrador

log = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic()

# Fallback del lado del servidor ante rechazos de los clasificadores de seguridad
MODELOS_CON_FALLBACK = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
MAX_ITERACIONES = 12

SYSTEM = """Sos el asistente de reportes de obra de un estudio de arquitectura de Tucumán, Argentina. \
Hablás por chat con el director técnico (DT) de una obra. Tenés dos trabajos:
1. Armar el reporte diario de obra con lo que manda el DT (texto, audios transcriptos y fotos), \
cargando cada dato con las herramientas.
2. Ayudarlo a anticipar los pedidos de materiales según el cronograma, para que la obra no se detenga.

Cómo trabajar:
- Registrá cada dato con su herramienta apenas lo recibís. No inventes datos: si algo no está claro, preguntá.
- Vinculá cada avance a una tarea del cronograma (buscar_tarea). Si dudás entre dos tareas, preguntá cuál. \
Si el trabajo no está en el cronograma, usá id_tarea "NO_PREVISTA".
- Clima: el contexto del día trae un clima propuesto por API. Mostráselo al DT y pedile que lo confirme o \
corrija, junto con el estado del terreno, antes de registrarlo con confirmado_por_dt=true.
- Notas de obra (órdenes de servicio, notas de pedido, observaciones, comunicaciones con el comitente, actas): \
registrá el texto literal, sin resumir ni corregir. Mostrale el texto al DT y pedile confirmación antes de guardarla.
- Personal: usá las categorías del convenio UOCRA.
- Fotos: el sistema te pasa una descripción automática de cada foto. Vinculalas a la tarea que corresponda; \
si no es obvio, preguntá. Si una foto es un remito, proponé cargar el ingreso y pedí confirmación.
- Materiales: cuando el DT pregunte qué hay hoy, y al cierre, mencioná las alertas amarillas, rojas o críticas \
y preguntá si ya se pidieron; registrá la respuesta con registrar_pedido. Al cierre, preguntá el stock de uno o \
dos materiales que se usan en los próximos días. Los viernes, anticipá lo que se necesita el lunes.
- Cierre: cuando el DT quiera cerrar, llamá a cerrar_reporte con un resumen de 3 líneas (qué se hizo, qué \
preocupa, qué se necesita). Si devuelve faltantes, pedilos de a poco, primero lo que se responde con sí o no.

Estilo: mensajes cortos para leer en el celular, en español rioplatense, en texto plano (sin markdown, sin \
asteriscos ni numerales; usá guiones para listas). Una pregunta por vez cuando necesitás datos."""


def _parametros_modelo() -> dict:
    p = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": 16000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": config.CLAUDE_EFFORT},
    }
    if config.CLAUDE_MODEL in MODELOS_CON_FALLBACK:
        p["betas"] = ["server-side-fallback-2026-07-01"]
        p["fallbacks"] = "default"
    return p


async def _crear(**kwargs):
    return await client.beta.messages.create(**_parametros_modelo(), **kwargs)


def _texto(resp) -> str:
    return "\n".join(b.text for b in resp.content if b.type == "text").strip()


async def turno(b: Borrador, mensaje: str) -> str:
    """Procesa un mensaje del DT y devuelve la respuesta del asistente. Guarda el historial."""
    partes = []
    if not b.historial:
        partes.append(herramientas.contexto_del_dia(b))
    pendientes = b.datos.get("fotos_sin_revisar", [])
    if pendientes:
        lineas = [f"- Foto #{f['id']} ({f['hora']}): {f['descripcion']}" for f in pendientes]
        partes.append("[Fotos recibidas desde el último mensaje]\n" + "\n".join(lineas))
        b.datos["fotos_sin_revisar"] = []
    partes.append(f"[{herramientas.hora_actual()}] DT: {mensaje}")

    # El historial solo se agrega al final (nunca se edita), así los bloques de thinking siguen válidos
    b.historial.append({"role": "user", "content": "\n\n".join(partes)})

    respuesta = ""
    for i in range(MAX_ITERACIONES):
        try:
            resp = await _crear(system=SYSTEM, tools=herramientas.TOOLS, messages=b.historial)
        except anthropic.RateLimitError:
            log.warning("Límite de uso de la API alcanzado")
            respuesta = "Estoy con mucha demanda. Probá de nuevo en un minuto."
            break
        except anthropic.APIStatusError as e:
            log.exception("Error de la API: %s", e.status_code)
            respuesta = "Tuve un problema técnico procesando el mensaje. Probá de nuevo."
            break
        except anthropic.APIConnectionError:
            log.exception("Sin conexión con la API")
            respuesta = "No tengo conexión en este momento. Probá de nuevo en un rato."
            break

        if resp.stop_reason == "refusal":
            if i == 0:
                b.historial.pop()
            respuesta = "No pude procesar ese mensaje. ¿Me lo contás de otra forma?"
            break

        b.historial.append({
            "role": "assistant",
            "content": [blk.model_dump(mode="json", exclude_none=True) for blk in resp.content],
        })

        if resp.stop_reason != "tool_use":
            respuesta = _texto(resp)
            break

        resultados = []
        for blk in resp.content:
            if blk.type != "tool_use":
                continue
            try:
                salida = herramientas.ejecutar(b, blk.name, dict(blk.input))
                resultados.append({"type": "tool_result", "tool_use_id": blk.id, "content": salida})
            except Exception as e:  # el error vuelve a Claude para que corrija
                log.info("Herramienta %s falló: %s", blk.name, e)
                resultados.append({"type": "tool_result", "tool_use_id": blk.id,
                                   "content": f"Error: {e}", "is_error": True})
        b.historial.append({"role": "user", "content": resultados})
    else:
        respuesta = "Me trabé con este mensaje. ¿Me lo repetís más corto?"

    b.guardar()
    return respuesta or "Listo."


async def describir_foto(path: Path) -> str:
    """Descripción breve de una foto de obra; si es un remito, extrae sus datos."""
    datos = base64.standard_b64encode(path.read_bytes()).decode()
    params = _parametros_modelo()
    params["output_config"] = {"effort": "low"}
    try:
        resp = await client.beta.messages.create(
            **params,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": datos}},
                    {"type": "text", "text": (
                        "Foto enviada por el director técnico de una obra. En una o dos oraciones en español, "
                        "describí qué trabajo o elemento muestra y en qué estado está, con vocabulario de obra "
                        "argentino. Si es un remito o factura de materiales, empezá con 'REMITO:' y listá "
                        "proveedor, número y materiales con cantidad y unidad. Solo texto plano."
                    )},
                ],
            }],
        )
    except anthropic.APIError:
        log.exception("No se pudo describir la foto")
        return "(sin descripción automática)"
    if resp.stop_reason == "refusal":
        return "(sin descripción automática)"
    return _texto(resp) or "(sin descripción automática)"
