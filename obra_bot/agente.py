"""Conversación con el modelo de IA: un turno por mensaje del DT, con herramientas sobre el borrador.

Proveedores: OpenAI (por defecto) o Anthropic, según LLM_PROVIDER en el .env.
El historial de cada borrador queda en el formato del proveedor con el que se empezó el día.
"""
import base64
import json
import logging
from pathlib import Path

from . import config, herramientas
from .reporte import Borrador

log = logging.getLogger(__name__)

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

PROMPT_FOTO = (
    "Foto enviada por el director técnico de una obra. En una o dos oraciones en español, describí qué "
    "trabajo o elemento muestra y en qué estado está, con vocabulario de obra argentino. Si es un remito o "
    "factura de materiales, empezá con 'REMITO:' y listá proveedor, número y materiales con cantidad y "
    "unidad. Solo texto plano."
)

MSG_ERROR = "Tuve un problema técnico procesando el mensaje. Probá de nuevo en un rato."
MSG_RECHAZO = "No pude procesar ese mensaje. ¿Me lo contás de otra forma?"
MSG_TRABADO = "Me trabé con este mensaje. ¿Me lo repetís más corto?"
SIN_DESCRIPCION = "(sin descripción automática)"


def _ejecutar_herramienta(b: Borrador, nombre: str, args: dict) -> tuple[str, bool]:
    """Devuelve (resultado, es_error). Los errores vuelven al modelo para que corrija."""
    try:
        return herramientas.ejecutar(b, nombre, args), False
    except Exception as e:
        log.info("Herramienta %s falló: %s", nombre, e)
        return f"Error: {e}", True


def _mensaje_usuario(b: Borrador, mensaje: str) -> str:
    partes = []
    if not b.historial:
        partes.append(herramientas.contexto_del_dia(b))
    pendientes = b.datos.get("fotos_sin_revisar", [])
    if pendientes:
        lineas = [f"- Foto #{f['id']} ({f['hora']}): {f['descripcion']}" for f in pendientes]
        partes.append("[Fotos recibidas desde el último mensaje]\n" + "\n".join(lineas))
        b.datos["fotos_sin_revisar"] = []
    partes.append(f"[{herramientas.hora_actual()}] DT: {mensaje}")
    return "\n\n".join(partes)


# --- OpenAI -----------------------------------------------------------------

_openai = None


def _cliente_openai():
    global _openai
    if _openai is None:
        from openai import AsyncOpenAI
        _openai = AsyncOpenAI()
    return _openai


TOOLS_OPENAI = [
    {"type": "function",
     "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
    for t in herramientas.TOOLS
]


def _params_openai() -> dict:
    p = {"model": config.OPENAI_MODEL, "max_completion_tokens": 16000}
    if config.OPENAI_REASONING_EFFORT:
        p["reasoning_effort"] = config.OPENAI_REASONING_EFFORT
    return p


async def _turno_openai(b: Borrador) -> str:
    import openai

    for _ in range(MAX_ITERACIONES):
        try:
            resp = await _cliente_openai().chat.completions.create(
                **_params_openai(),
                messages=[{"role": "system", "content": SYSTEM}, *b.historial],
                tools=TOOLS_OPENAI,
            )
        except openai.RateLimitError:
            log.warning("Límite de uso de OpenAI alcanzado")
            return "Estoy con mucha demanda. Probá de nuevo en un minuto."
        except openai.APIStatusError as e:
            log.exception("Error de OpenAI: %s", e.status_code)
            return MSG_ERROR
        except openai.APIConnectionError:
            log.exception("Sin conexión con OpenAI")
            return MSG_ERROR

        choice = resp.choices[0]
        msg = choice.message
        if msg.refusal:
            return MSG_RECHAZO

        asistente = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            asistente["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        b.historial.append(asistente)

        if not msg.tool_calls:
            return (msg.content or "").strip()

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                resultado = "Error: argumentos JSON inválidos, reintentá la llamada."
            else:
                resultado, _ = _ejecutar_herramienta(b, tc.function.name, args)
            b.historial.append({"role": "tool", "tool_call_id": tc.id, "content": resultado})
    return MSG_TRABADO


async def _foto_openai(datos_b64: str) -> str:
    import openai
    try:
        resp = await _cliente_openai().chat.completions.create(
            model=config.OPENAI_MODEL,
            max_completion_tokens=4000,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{datos_b64}"}},
                {"type": "text", "text": PROMPT_FOTO},
            ]}],
        )
    except openai.APIError:
        log.exception("No se pudo describir la foto")
        return SIN_DESCRIPCION
    msg = resp.choices[0].message
    return (msg.content or "").strip() if not msg.refusal else SIN_DESCRIPCION


# --- Anthropic --------------------------------------------------------------

_anthropic = None
MODELOS_CON_FALLBACK = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


def _cliente_anthropic():
    global _anthropic
    if _anthropic is None:
        import anthropic
        _anthropic = anthropic.AsyncAnthropic()
    return _anthropic


def _params_anthropic(effort: str | None = None) -> dict:
    p = {
        "model": config.CLAUDE_MODEL,
        "max_tokens": 16000,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort or config.CLAUDE_EFFORT},
    }
    if config.CLAUDE_MODEL in MODELOS_CON_FALLBACK:
        # Fallback del lado del servidor ante rechazos de los clasificadores de seguridad
        p["betas"] = ["server-side-fallback-2026-07-01"]
        p["fallbacks"] = "default"
    return p


def _texto_anthropic(resp) -> str:
    return "\n".join(blk.text for blk in resp.content if blk.type == "text").strip()


async def _turno_anthropic(b: Borrador) -> str:
    import anthropic

    for i in range(MAX_ITERACIONES):
        try:
            resp = await _cliente_anthropic().beta.messages.create(
                **_params_anthropic(), system=SYSTEM, tools=herramientas.TOOLS, messages=b.historial)
        except anthropic.RateLimitError:
            log.warning("Límite de uso de Anthropic alcanzado")
            return "Estoy con mucha demanda. Probá de nuevo en un minuto."
        except anthropic.APIStatusError as e:
            log.exception("Error de Anthropic: %s", e.status_code)
            return MSG_ERROR
        except anthropic.APIConnectionError:
            log.exception("Sin conexión con Anthropic")
            return MSG_ERROR

        if resp.stop_reason == "refusal":
            if i == 0:
                b.historial.pop()
            return MSG_RECHAZO

        # El historial solo se agrega al final, así los bloques de thinking siguen siendo válidos
        b.historial.append({
            "role": "assistant",
            "content": [blk.model_dump(mode="json", exclude_none=True) for blk in resp.content],
        })
        if resp.stop_reason != "tool_use":
            return _texto_anthropic(resp)

        resultados = []
        for blk in resp.content:
            if blk.type == "tool_use":
                salida, es_error = _ejecutar_herramienta(b, blk.name, dict(blk.input))
                r = {"type": "tool_result", "tool_use_id": blk.id, "content": salida}
                if es_error:
                    r["is_error"] = True
                resultados.append(r)
        b.historial.append({"role": "user", "content": resultados})
    return MSG_TRABADO


async def _foto_anthropic(datos_b64: str) -> str:
    import anthropic
    try:
        resp = await _cliente_anthropic().beta.messages.create(
            **_params_anthropic(effort="low"),
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": datos_b64}},
                {"type": "text", "text": PROMPT_FOTO},
            ]}],
        )
    except anthropic.APIError:
        log.exception("No se pudo describir la foto")
        return SIN_DESCRIPCION
    return _texto_anthropic(resp) if resp.stop_reason != "refusal" else SIN_DESCRIPCION


# --- interfaz común -----------------------------------------------------------

async def turno(b: Borrador, mensaje: str) -> str:
    """Procesa un mensaje del DT y devuelve la respuesta del asistente. Guarda el historial."""
    b.datos.setdefault("proveedor", config.LLM_PROVIDER)
    b.historial.append({"role": "user", "content": _mensaje_usuario(b, mensaje)})
    if b.datos["proveedor"] == "anthropic":
        respuesta = await _turno_anthropic(b)
    else:
        respuesta = await _turno_openai(b)
    b.guardar()
    return respuesta or "Listo."


async def describir_foto(path: Path) -> str:
    """Descripción breve de una foto de obra; si es un remito, extrae sus datos."""
    datos = base64.standard_b64encode(path.read_bytes()).decode()
    if config.LLM_PROVIDER == "anthropic":
        texto = await _foto_anthropic(datos)
    else:
        texto = await _foto_openai(datos)
    return texto or SIN_DESCRIPCION
