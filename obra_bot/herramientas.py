"""Herramientas que Claude usa para cargar el reporte. Cada una modifica el borrador o consulta datos."""
import json
from datetime import date, datetime

from . import config, cronograma, db
from .reporte import Borrador, faltantes, proximos_pasos

CATEGORIAS_UOCRA = ["oficial especializado", "oficial", "medio oficial", "ayudante", "sereno", "otro"]
TIPOS_NOTA = ["orden_de_servicio", "nota_de_pedido", "observacion_dt", "comunicacion_comitente", "acta"]


def _obj(props: dict, requeridos: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": requeridos, "additionalProperties": False}


TOOLS = [
    {
        "name": "consultar_cronograma",
        "description": "Tareas previstas para una fecha (por defecto hoy), con % previsto y último % real "
                       "informado. Usala cuando el DT pregunta qué hay hoy o para ubicar trabajos.",
        "input_schema": _obj({"fecha": {"type": "string", "description": "YYYY-MM-DD; vacío = hoy"}}, []),
    },
    {
        "name": "buscar_tarea",
        "description": "Busca en el cronograma las tareas que coinciden con lo que describe el DT. "
                       "Devuelve hasta 5 candidatas con su id.",
        "input_schema": _obj({"texto": {"type": "string"}}, ["texto"]),
    },
    {
        "name": "registrar_condiciones",
        "description": "Registra clima y estado del terreno. Poné confirmado_por_dt=true solo cuando el DT "
                       "confirmó o corrigió los valores propuestos.",
        "input_schema": _obj({
            "clima_manana": {"type": "string"},
            "clima_tarde": {"type": "string"},
            "temp_max": {"type": "number"},
            "temp_min": {"type": "number"},
            "lluvia_mm": {"type": "number"},
            "terreno": {"type": "string", "enum": ["seco", "humedo", "anegado"]},
            "confirmado_por_dt": {"type": "boolean"},
        }, ["clima_manana", "clima_tarde", "terreno", "confirmado_por_dt"]),
    },
    {
        "name": "registrar_jornada",
        "description": "Tipo de jornada y, si hubo, horas perdidas y su causa.",
        "input_schema": _obj({
            "tipo": {"type": "string", "enum": ["completa", "parcial", "no_laborable"]},
            "horas_perdidas": {"type": "number"},
            "causa": {"type": "string", "description": "lluvia, falta de material, corte de luz o agua, paro, feriado, otra"},
        }, ["tipo"]),
    },
    {
        "name": "registrar_personal",
        "description": "Personal en obra por empresa y categoría UOCRA. Reemplaza el registro previo "
                       "de la misma empresa y categoría.",
        "input_schema": _obj({
            "empresa": {"type": "string", "description": "Empresa o subcontrato; 'propio' si es personal propio"},
            "categoria": {"type": "string", "enum": CATEGORIAS_UOCRA},
            "cantidad": {"type": "integer"},
            "horas": {"type": "number"},
        }, ["empresa", "categoria", "cantidad"]),
    },
    {
        "name": "registrar_avance",
        "description": "Avance de una tarea del cronograma: % acumulado real. Usá id_tarea='NO_PREVISTA' "
                       "si el trabajo no está en el cronograma.",
        "input_schema": _obj({
            "id_tarea": {"type": "string"},
            "descripcion": {"type": "string"},
            "pct_real": {"type": "number", "description": "% acumulado de la tarea, 0 a 100"},
        }, ["id_tarea", "descripcion", "pct_real"]),
    },
    {
        "name": "registrar_material",
        "description": "Ingreso de material (con remito), faltante o stock declarado en obra.",
        "input_schema": _obj({
            "tipo": {"type": "string", "enum": ["ingreso", "faltante", "stock"]},
            "material": {"type": "string"},
            "cantidad": {"type": "number"},
            "unidad": {"type": "string"},
            "proveedor": {"type": "string"},
            "remito": {"type": "string"},
        }, ["tipo", "material", "cantidad", "unidad"]),
    },
    {
        "name": "registrar_equipo",
        "description": "Equipo en obra y su estado.",
        "input_schema": _obj({"equipo": {"type": "string"}, "estado": {"type": "string"}}, ["equipo", "estado"]),
    },
    {
        "name": "registrar_hys",
        "description": "Higiene y seguridad del día.",
        "input_schema": _obj({
            "epp_ok": {"type": "boolean", "description": "¿Se usó el equipo de protección personal?"},
            "visitas": {"type": "string", "description": "Visitas de ART o del responsable de HyS; vacío si no hubo"},
            "incidentes": {"type": "string", "description": "Incidentes; vacío si no hubo"},
        }, ["epp_ok"]),
    },
    {
        "name": "registrar_nota",
        "description": "Nota de obra con su texto LITERAL (no resumir). Queda pendiente hasta que se cierre.",
        "input_schema": _obj({
            "tipo": {"type": "string", "enum": TIPOS_NOTA},
            "emisor": {"type": "string"},
            "destinatario": {"type": "string"},
            "asunto": {"type": "string"},
            "texto": {"type": "string"},
            "plazo": {"type": "string", "description": "YYYY-MM-DD si tiene plazo de respuesta"},
            "impacto_materiales": {"type": "boolean"},
        }, ["tipo", "emisor", "destinatario", "asunto", "texto", "impacto_materiales"]),
    },
    {
        "name": "vincular_foto",
        "description": "Vincula una foto del día a una tarea del cronograma, con una descripción corta.",
        "input_schema": _obj({
            "foto_id": {"type": "integer"},
            "id_tarea": {"type": "string"},
            "descripcion": {"type": "string"},
        }, ["foto_id", "id_tarea", "descripcion"]),
    },
    {
        "name": "alertas_materiales",
        "description": "Materiales que hay que pedir según cronograma, plazo de entrega y stock. "
                       "Niveles: amarillo (pedir esta semana), rojo (fecha límite vencida), "
                       "critico (rojo en tarea crítica).",
        "input_schema": _obj({}, []),
    },
    {
        "name": "registrar_pedido",
        "description": "Estado de pedido de un material para una tarea, según lo que diga el DT.",
        "input_schema": _obj({
            "id_tarea": {"type": "string"},
            "material": {"type": "string"},
            "estado": {"type": "string", "enum": ["pedido", "recibido", "no_aplica", "pendiente"]},
            "fecha_entrega": {"type": "string", "description": "YYYY-MM-DD prometida por el proveedor"},
        }, ["id_tarea", "material", "estado"]),
    },
    {
        "name": "ver_borrador",
        "description": "Muestra todo lo cargado hoy y los campos obligatorios que faltan.",
        "input_schema": _obj({}, []),
    },
    {
        "name": "cerrar_reporte",
        "description": "Intenta cerrar el reporte. Si faltan obligatorios los devuelve; si no, deja el "
                       "reporte listo para que el DT lo confirme con un botón.",
        "input_schema": _obj({
            "resumen": {"type": "string", "description": "3 líneas: qué se hizo, qué preocupa, qué se necesita"},
        }, ["resumen"]),
    },
]


def _tarea_info(b: Borrador, t: cronograma.Tarea) -> dict:
    reales = db.ultimos_avances(b.obra.id, b.fecha.isoformat())
    return {
        "id_tarea": t.id, "rubro": t.rubro, "tarea": t.nombre,
        "inicio": t.inicio.isoformat(), "fin": t.fin.isoformat(),
        "pct_previsto": cronograma.pct_previsto(t, b.fecha),
        "ultimo_pct_real": reales.get(t.id), "critica": t.critica,
    }


def ejecutar(b: Borrador, nombre: str, args: dict) -> str:
    """Ejecuta una herramienta y devuelve el resultado como texto JSON."""
    d = b.datos
    hoy = b.fecha.isoformat()

    if nombre == "consultar_cronograma":
        dia = date.fromisoformat(args["fecha"]) if args.get("fecha") else b.fecha
        res = [_tarea_info(b, t) for t in cronograma.activas(b.tareas, dia)]
        return json.dumps({"fecha": dia.isoformat(), "tareas": res}, ensure_ascii=False)

    if nombre == "buscar_tarea":
        res = [_tarea_info(b, t) for t in cronograma.buscar(b.tareas, args["texto"], b.fecha)]
        return json.dumps(res or "Sin coincidencias en el cronograma", ensure_ascii=False)

    if nombre == "registrar_condiciones":
        d["condiciones"].update({k: v for k, v in args.items() if k != "confirmado_por_dt"})
        d["condiciones"]["confirmado"] = bool(args["confirmado_por_dt"])
        return "ok"

    if nombre == "registrar_jornada":
        d["jornada"] = args
        return "ok"

    if nombre == "registrar_personal":
        d["personal"] = [p for p in d["personal"]
                         if (p["empresa"], p["categoria"]) != (args["empresa"], args["categoria"])]
        d["personal"].append(args)
        return "ok"

    if nombre == "registrar_avance":
        tid = args["id_tarea"]
        if tid != "NO_PREVISTA" and tid not in b.tareas:
            raise ValueError(f"La tarea {tid} no existe en el cronograma. Usá buscar_tarea.")
        t = b.tareas.get(tid)
        args["pct_previsto"] = cronograma.pct_previsto(t, b.fecha) if t else None
        args["desvio"] = round(args["pct_real"] - args["pct_previsto"], 1) if t else None
        args["tarea"] = t.nombre if t else "Tarea no prevista"
        args["rubro"] = t.rubro if t else ""
        d["avances"] = [a for a in d["avances"] if a["id_tarea"] != tid or tid == "NO_PREVISTA"]
        d["avances"].append(args)
        return json.dumps({"ok": True, "pct_previsto": args["pct_previsto"], "desvio": args["desvio"]})

    if nombre == "registrar_material":
        clave = {"ingreso": "ingresos", "faltante": "faltantes", "stock": "stock"}[args["tipo"]]
        d["materiales"][clave].append(args)
        return "ok"

    if nombre == "registrar_equipo":
        d["equipos"].append(args)
        return "ok"

    if nombre == "registrar_hys":
        d["hys"] = args
        return "ok"

    if nombre == "registrar_nota":
        nid, numero = db.crear_nota(
            b.obra.id, args["tipo"], hoy, args["emisor"], args["destinatario"], args["asunto"],
            args["texto"], args.get("plazo"), args["impacto_materiales"], b.id,
        )
        return json.dumps({"ok": True, "numero": numero, "tipo": args["tipo"]})

    if nombre == "vincular_foto":
        if args["id_tarea"] != "NO_PREVISTA" and args["id_tarea"] not in b.tareas:
            raise ValueError(f"La tarea {args['id_tarea']} no existe en el cronograma.")
        if not db.vincular_foto(args["foto_id"], b.id, args["id_tarea"], args["descripcion"]):
            raise ValueError(f"La foto {args['foto_id']} no es de este reporte.")
        return "ok"

    if nombre == "alertas_materiales":
        return json.dumps(cronograma.alertas_materiales(b.obra.id, b.tareas, b.fecha), ensure_ascii=False)

    if nombre == "registrar_pedido":
        db.guardar_pedido(b.obra.id, args["id_tarea"], args["material"], args["estado"],
                          hoy, args.get("fecha_entrega"))
        return "ok"

    if nombre == "ver_borrador":
        fotos = [dict(f) for f in db.fotos_de_reporte(b.id)]
        vista = {k: v for k, v in d.items() if k not in ("fotos_sin_revisar",)}
        return json.dumps({"borrador": vista, "fotos": fotos, "faltan": faltantes(b)},
                          ensure_ascii=False, default=str)

    if nombre == "cerrar_reporte":
        d["resumen"] = args["resumen"]
        falta = faltantes(b)
        if falta:
            return json.dumps({"listo": False, "faltan": falta}, ensure_ascii=False)
        d["listo"] = True
        return json.dumps({
            "listo": True,
            "nota": "El bot va a mostrar el botón Confirmar. Mostrale al DT un resumen corto del reporte "
                    "y los pedidos de materiales pendientes.",
            "proximos": proximos_pasos(b),
        }, ensure_ascii=False)

    raise ValueError(f"Herramienta desconocida: {nombre}")


def contexto_del_dia(b: Borrador) -> str:
    """Bloque de contexto que se agrega al primer mensaje del día."""
    activas = [_tarea_info(b, t) for t in cronograma.activas(b.tareas, b.fecha)]
    alertas = cronograma.alertas_materiales(b.obra.id, b.tareas, b.fecha)
    notas = [
        {"tipo": n["tipo"], "numero": n["numero"], "asunto": n["asunto"], "plazo": n["plazo"]}
        for n in db.notas_abiertas(b.obra.id)
    ]
    ctx = {
        "obra": b.obra.nombre,
        "direccion": b.obra.direccion,
        "fecha": b.fecha.isoformat(),
        "dia_semana": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"][b.fecha.weekday()],
        "dt": b.dt_nombre,
        "clima_propuesto_api": b.datos["condiciones"].get("propuesto"),
        "tareas_previstas_hoy": activas,
        "alertas_materiales": alertas,
        "notas_abiertas": notas,
        "minimo_fotos": config.MIN_FOTOS,
    }
    return "[Contexto del día, generado por el sistema]\n" + json.dumps(ctx, ensure_ascii=False, default=str)


def hora_actual() -> str:
    return datetime.now(config.TZ).strftime("%H:%M")
