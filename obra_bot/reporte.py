"""Borrador del reporte diario: estado, campos faltantes, confirmación y salidas."""
import json
from dataclasses import dataclass
from datetime import date, datetime

from . import config, cronograma, db, obras, salidas


def datos_iniciales() -> dict:
    return {
        "condiciones": {"propuesto": None, "confirmado": False},
        "jornada": {},
        "personal": [],
        "avances": [],
        "materiales": {"ingresos": [], "faltantes": [], "stock": []},
        "equipos": [],
        "hys": {},
        "fotos_sin_revisar": [],
        "resumen": "",
        "listo": False,
    }


@dataclass
class Borrador:
    id: int
    obra: obras.Obra
    fecha: date
    dt_id: int
    dt_nombre: str
    chat_id: int
    estado: str
    numero: int | None
    datos: dict
    historial: list

    @classmethod
    def desde_fila(cls, fila) -> "Borrador":
        return cls(
            id=fila["id"],
            obra=obras.obtener(fila["obra_id"]),
            fecha=date.fromisoformat(fila["fecha"]),
            dt_id=fila["dt_id"],
            dt_nombre=fila["dt_nombre"],
            chat_id=fila["chat_id"],
            estado=fila["estado"],
            numero=fila["numero"],
            datos=json.loads(fila["datos"]),
            historial=json.loads(fila["historial"]),
        )

    def guardar(self):
        db.actualizar_reporte(self.id, self.estado, self.numero, self.datos, self.historial)

    @property
    def tareas(self):
        return self.obra.tareas


def obtener_o_crear(obra: obras.Obra, fecha: date, dt_id: int, dt_nombre: str,
                    chat_id: int) -> tuple[Borrador, bool]:
    fila = db.obtener_reporte(obra.id, fecha.isoformat(), dt_id)
    if fila:
        return Borrador.desde_fila(fila), False
    rid = db.crear_reporte(obra.id, fecha.isoformat(), dt_id, dt_nombre, chat_id, datos_iniciales())
    return Borrador.desde_fila(db.obtener_reporte_por_id(rid)), True


def faltantes(b: Borrador) -> list[str]:
    d = b.datos
    falta = []
    if not d["condiciones"].get("confirmado"):
        falta.append("clima y estado del terreno confirmados por el DT")
    if not d["jornada"].get("tipo"):
        falta.append("tipo de jornada (completa, parcial o no laborable)")
    no_laborable = d["jornada"].get("tipo") == "no_laborable"
    if not no_laborable and not d["personal"]:
        falta.append("personal en obra (empresa, categoría UOCRA, cantidad)")
    if not no_laborable and not d["avances"]:
        falta.append("al menos un avance vinculado al cronograma")
    if "epp_ok" not in d["hys"]:
        falta.append("higiene y seguridad (uso de EPP, visitas, incidentes)")
    n_fotos = len(db.fotos_de_reporte(b.id))
    if not no_laborable and n_fotos < config.MIN_FOTOS:
        falta.append(f"fotos: hay {n_fotos}, el mínimo es {config.MIN_FOTOS}")
    return falta


def proximos_pasos(b: Borrador) -> dict:
    manana = cronograma.proximo_habil(b.fecha)
    tareas_manana = [
        {"id_tarea": t.id, "tarea": t.nombre}
        for t in cronograma.activas(b.tareas, manana)
    ]
    alertas = cronograma.alertas_materiales(b.obra.id, b.tareas, b.fecha)
    return {"fecha": manana.isoformat(), "tareas": tareas_manana, "pedidos": alertas}


def confirmar(b: Borrador):
    """Cierra el reporte: numera, guarda avances y stock, genera PDF y filas de la planilla."""
    hoy = b.fecha.isoformat()
    for a in b.datos["avances"]:
        if a["id_tarea"] != "NO_PREVISTA":
            db.guardar_avance(b.obra.id, a["id_tarea"], hoy, a["pct_real"])
    for s in b.datos["materiales"]["stock"]:
        db.guardar_stock(b.obra.id, s["material"], hoy, s["cantidad"], s["unidad"])

    b.numero = db.siguiente_numero(b.obra.id)
    b.estado = "confirmado"
    b.datos["confirmado_en"] = datetime.now(config.TZ).strftime("%d/%m/%Y %H:%M")
    b.datos["proximos"] = proximos_pasos(b)

    pdf_path = salidas.generar_pdf(b)
    b.datos["pdf"] = str(pdf_path.relative_to(config.BASE_DIR))
    salidas.agregar_a_planilla(b)
    b.guardar()
    return pdf_path
