"""Herramientas que usa el modelo: cargar el reporte del día y consultar cómo viene la obra."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, cronograma, db
from .reporte import Borrador, faltantes, proximos_pasos

CATEGORIAS_UOCRA = ["oficial especializado", "oficial", "medio oficial", "ayudante", "sereno", "otro"]
TIPOS_NOTA = ["orden_de_servicio", "nota_de_pedido", "observacion_dt", "comunicacion_comitente", "acta"]

# Con el reporte del día ya confirmado solo se puede consultar (y actualizar pedidos, que son de la obra)
PERMITIDAS_CONFIRMADO = {
    "consultar_cronograma", "buscar_tarea", "alertas_materiales", "registrar_pedido", "ver_borrador",
    "resumen_obra", "ultimos_reportes", "notas_abiertas", "pedidos_pendientes", "fotos_recientes",
    "enviar_fotos", "buscar_en_reportes",
}
MAX_FOTOS_POR_ENVIO = 5


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
    # --- consultas sobre la obra (no modifican el reporte) ---
    {
        "name": "resumen_obra",
        "description": "Estado general de la obra a hoy: avance real contra previsto, tareas atrasadas, "
                       "en curso y próximas, último reporte y cantidad de notas y alertas abiertas. "
                       "Es lo primero para contarle a alguien cómo viene la obra.",
        "input_schema": _obj({}, []),
    },
    {
        "name": "ultimos_reportes",
        "description": "Últimos reportes diarios de la obra (sin contar el borrador actual): fecha, DT, "
                       "resumen, jornada, avances, faltantes de material e incidentes.",
        "input_schema": _obj({"cantidad": {"type": "integer", "description": "1 a 10; por defecto 5"}}, []),
    },
    {
        "name": "notas_abiertas",
        "description": "Órdenes de servicio, notas de pedido y demás notas de obra sin cerrar, con su texto "
                       "y plazo de respuesta.",
        "input_schema": _obj({}, []),
    },
    {
        "name": "pedidos_pendientes",
        "description": "Materiales pedidos que todavía no llegaron y materiales que hay que pedir según el "
                       "cronograma.",
        "input_schema": _obj({}, []),
    },
    {
        "name": "fotos_recientes",
        "description": "Últimas fotos de la obra con su descripción, opcionalmente de una tarea. Devuelve los "
                       "id para mandarlas con enviar_fotos.",
        "input_schema": _obj({
            "id_tarea": {"type": "string", "description": "Vacío = todas las tareas"},
            "cantidad": {"type": "integer", "description": "1 a 20; por defecto 8"},
        }, []),
    },
    {
        "name": "enviar_fotos",
        "description": f"Le manda al usuario por el chat las fotos indicadas (hasta {MAX_FOTOS_POR_ENVIO}), "
                       "después de tu respuesta.",
        "input_schema": _obj({"foto_ids": {"type": "array", "items": {"type": "integer"}}}, ["foto_ids"]),
    },
    {
        "name": "buscar_en_reportes",
        "description": "Busca palabras en los reportes y notas de la obra (por ejemplo 'losa hormigonado' o "
                       "'corralón'). Devuelve fechas y fragmentos.",
        "input_schema": _obj({"texto": {"type": "string"}}, ["texto"]),
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


# --- consultas sobre la obra ----------------------------------------------

def _resumen_obra(b: Borrador) -> dict:
    hoy = b.fecha
    reales = db.ultimos_avances(b.obra.id, hoy.isoformat())
    real, previsto = cronograma.avance_obra(b.obra.id, b.tareas, hoy)
    atrasadas, sin_avance = [], []
    for t in b.tareas.values():
        prev = cronograma.pct_previsto(t, hoy)
        if t.id in reales:
            desvio = round(reales[t.id] - prev, 1)
            if desvio <= -5:
                atrasadas.append({"id_tarea": t.id, "tarea": t.nombre, "critica": t.critica,
                                  "pct_real": reales[t.id], "pct_previsto": prev, "desvio": desvio})
        elif t.inicio <= hoy <= t.fin:
            sin_avance.append({"id_tarea": t.id, "tarea": t.nombre, "inicio": t.inicio.isoformat()})
    atrasadas.sort(key=lambda a: (not a["critica"], a["desvio"]))

    ultimos = [r for r in db.reportes_de_obra(b.obra.id, hoy.isoformat(), 2) if r["id"] != b.id]
    alertas = cronograma.alertas_materiales(b.obra.id, b.tareas, hoy)
    notas = db.notas_abiertas(b.obra.id)
    return {
        "obra": b.obra.nombre,
        "fecha": hoy.isoformat(),
        "avance_real_pct": real,
        "avance_previsto_pct": previsto,
        "tareas_atrasadas": atrasadas,
        "tareas_en_curso_sin_avance_informado": sin_avance,
        "en_curso": [_tarea_info(b, t) for t in cronograma.activas(b.tareas, hoy)],
        "proximas_10_dias": [
            {"id_tarea": t.id, "tarea": t.nombre, "inicio": t.inicio.isoformat(), "critica": t.critica}
            for t in sorted(b.tareas.values(), key=lambda t: t.inicio)
            if hoy < t.inicio <= hoy + timedelta(days=10)
        ],
        "ultimo_reporte": {"fecha": ultimos[0]["fecha"], "dt": ultimos[0]["dt_nombre"],
                           "estado": ultimos[0]["estado"]} if ultimos else None,
        "notas_abiertas": len(notas),
        "notas_vencidas": sum(1 for n in notas if n["plazo"] and n["plazo"] < hoy.isoformat()),
        "alertas_materiales": {nivel: sum(1 for a in alertas if a["nivel"] == nivel)
                               for nivel in ("critico", "rojo", "amarillo")},
    }


def _ultimos_reportes(b: Borrador, cantidad: int) -> list[dict]:
    filas = [r for r in db.reportes_de_obra(b.obra.id, b.fecha.isoformat(), cantidad + 1) if r["id"] != b.id]
    res = []
    for r in filas[:cantidad]:
        d = json.loads(r["datos"])
        res.append({
            "fecha": r["fecha"], "numero": r["numero"], "dt": r["dt_nombre"], "estado": r["estado"],
            "resumen": d.get("resumen", ""),
            "jornada": d.get("jornada", {}),
            "personal_total": sum(p.get("cantidad", 0) for p in d.get("personal", [])),
            "avances": [{"tarea": a.get("tarea"), "pct_real": a.get("pct_real"), "desvio": a.get("desvio"),
                         "descripcion": a.get("descripcion")} for a in d.get("avances", [])],
            "faltantes_material": d.get("materiales", {}).get("faltantes", []),
            "incidentes": d.get("hys", {}).get("incidentes", ""),
        })
    return res


def _notas_abiertas(b: Borrador) -> list[dict]:
    hoy = b.fecha.isoformat()
    return [{
        "tipo": n["tipo"], "numero": n["numero"], "fecha": n["fecha"], "emisor": n["emisor"],
        "destinatario": n["destinatario"], "asunto": n["asunto"], "texto": n["texto"], "plazo": n["plazo"],
        "vencida": bool(n["plazo"] and n["plazo"] < hoy), "impacto_materiales": bool(n["impacto_materiales"]),
    } for n in db.notas_abiertas(b.obra.id)]


def _pedidos_pendientes(b: Borrador) -> dict:
    hoy = b.fecha.isoformat()

    def fila(p):
        t = b.tareas.get(p["id_tarea"])
        return {"material": p["material"], "id_tarea": p["id_tarea"], "tarea": t.nombre if t else "",
                "fecha_registro": p["fecha"], "fecha_entrega": p["fecha_entrega"],
                "entrega_vencida": bool(p["fecha_entrega"] and p["fecha_entrega"] < hoy)}

    return {
        "pedidos_sin_recibir": [fila(p) for p in db.pedidos_de_obra(b.obra.id, ("pedido",))],
        "marcados_pendientes": [fila(p) for p in db.pedidos_de_obra(b.obra.id, ("pendiente",))],
        "a_pedir_segun_cronograma": cronograma.alertas_materiales(b.obra.id, b.tareas, b.fecha),
    }


def _fotos_recientes(b: Borrador, id_tarea: str | None, cantidad: int) -> list[dict]:
    res = []
    for f in db.fotos_de_obra(b.obra.id, id_tarea or None, cantidad):
        t = b.tareas.get(f["id_tarea"] or "")
        res.append({"foto_id": f["id"], "fecha": f["fecha"], "hora": f["hora"], "id_tarea": f["id_tarea"],
                    "tarea": t.nombre if t else "", "descripcion": f["descripcion"], "dt": f["dt_nombre"]})
    return res


def _enviar_fotos(b: Borrador, foto_ids: list[int]) -> dict:
    enviadas, no_encontradas = [], []
    for fid in foto_ids[:MAX_FOTOS_POR_ENVIO]:
        f = db.foto_de_obra(fid, b.obra.id)
        if f and Path(f["path"]).exists():
            b.salientes.append(Path(f["path"]))
            enviadas.append(fid)
        else:
            no_encontradas.append(fid)
    return {"se_envian_despues_de_tu_respuesta": enviadas, "no_encontradas": no_encontradas,
            "omitidas_por_limite": foto_ids[MAX_FOTOS_POR_ENVIO:]}


def _fragmentos(b: Borrador):
    """(fecha, origen, texto) de todo lo escrito en reportes, fotos y notas de la obra."""
    for r in db.reportes_de_obra(b.obra.id, b.fecha.isoformat(), 500):
        d = json.loads(r["datos"])
        origen = f"reporte de {r['dt_nombre']}"
        if d.get("resumen"):
            yield r["fecha"], origen, d["resumen"]
        if d.get("jornada", {}).get("causa"):
            yield r["fecha"], origen, f"Jornada {d['jornada'].get('tipo', '')}: {d['jornada']['causa']}"
        for a in d.get("avances", []):
            yield r["fecha"], origen, f"{a.get('tarea', '')}: {a.get('descripcion', '')} ({a.get('pct_real')}%)"
        for tipo, items in d.get("materiales", {}).items():
            for m in items:
                yield r["fecha"], origen, (f"Material ({tipo}): {m.get('material')} {m.get('cantidad')} "
                                           f"{m.get('unidad')} {m.get('proveedor', '')}")
        for e in d.get("equipos", []):
            yield r["fecha"], origen, f"Equipo: {e.get('equipo')} - {e.get('estado')}"
        hys = d.get("hys", {})
        for clave in ("visitas", "incidentes"):
            if hys.get(clave):
                yield r["fecha"], origen, f"HyS {clave}: {hys[clave]}"
    for f in db.fotos_de_obra(b.obra.id, None, 500):
        yield f["fecha"], f"foto #{f['id']}", f["descripcion"] or ""
    for n in db.notas_de_obra(b.obra.id):
        yield n["fecha"], f"{n['tipo']} N° {n['numero']} ({n['estado']})", f"{n['asunto']}: {n['texto']}"


def _buscar_en_reportes(b: Borrador, texto: str) -> list[dict]:
    palabras = set(cronograma.normalizar(texto))
    if not palabras:
        return []
    encontrados = []
    for fecha, origen, frag in _fragmentos(b):
        n = len(palabras & set(cronograma.normalizar(frag)))
        if n:
            encontrados.append((n, fecha, origen, frag))
    if not encontrados:
        return []
    # Solo los fragmentos con más palabras en común, del más nuevo al más viejo
    mejor = max(e[0] for e in encontrados)
    elegidos = sorted((e for e in encontrados if e[0] == mejor), key=lambda e: e[1], reverse=True)
    return [{"fecha": f, "origen": o, "texto": t[:400]} for _, f, o, t in elegidos[:10]]


def _consulta(b: Borrador, nombre: str, args: dict):
    """Ejecuta una herramienta de consulta. Devuelve None si el nombre no es una consulta."""
    if nombre == "resumen_obra":
        return _resumen_obra(b)
    if nombre == "ultimos_reportes":
        return _ultimos_reportes(b, max(1, min(int(args.get("cantidad") or 5), 10)))
    if nombre == "notas_abiertas":
        return _notas_abiertas(b) or "No hay notas abiertas"
    if nombre == "pedidos_pendientes":
        return _pedidos_pendientes(b)
    if nombre == "fotos_recientes":
        return _fotos_recientes(b, args.get("id_tarea"), max(1, min(int(args.get("cantidad") or 8), 20))) \
            or "No hay fotos"
    if nombre == "enviar_fotos":
        return _enviar_fotos(b, [int(i) for i in args["foto_ids"]])
    if nombre == "buscar_en_reportes":
        return _buscar_en_reportes(b, args["texto"]) or "Sin coincidencias"
    return None


def ejecutar(b: Borrador, nombre: str, args: dict) -> str:
    """Ejecuta una herramienta y devuelve el resultado como texto JSON."""
    d = b.datos
    hoy = b.fecha.isoformat()

    if b.estado == "confirmado" and nombre not in PERMITIDAS_CONFIRMADO:
        raise ValueError("El reporte de hoy ya está confirmado y no se puede modificar. "
                         "Solo se pueden hacer consultas.")
    consulta = _consulta(b, nombre, args)
    if consulta is not None:
        return json.dumps(consulta, ensure_ascii=False, default=str)

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
