"""Cronograma de obra: carga desde CSV, días hábiles, avance previsto y alertas de materiales."""
import csv
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import config, db

# Feriados de fecha fija (nacionales + 24/9 provincial de Tucumán). Los trasladables no están.
FERIADOS_FIJOS = {(1, 1), (3, 24), (4, 2), (5, 1), (5, 25), (6, 20), (7, 9), (9, 24), (12, 8), (12, 25)}


@dataclass
class Material:
    nombre: str
    cantidad: float
    unidad: str
    proveedor: str
    plazo_dias: int


@dataclass
class Tarea:
    id: str
    rubro: str
    nombre: str
    inicio: date
    fin: date
    predecesoras: list[str] = field(default_factory=list)
    critica: bool = False
    materiales: list[Material] = field(default_factory=list)


def cargar(path: Path) -> dict[str, Tarea]:
    """Lee un CSV con una fila por (tarea, material). Las columnas de material pueden ir vacías."""
    tareas: dict[str, Tarea] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            tid = fila["id_tarea"].strip()
            if tid not in tareas:
                tareas[tid] = Tarea(
                    id=tid,
                    rubro=fila["rubro"].strip(),
                    nombre=fila["tarea"].strip(),
                    inicio=date.fromisoformat(fila["inicio"].strip()),
                    fin=date.fromisoformat(fila["fin"].strip()),
                    predecesoras=[p.strip() for p in fila.get("predecesoras", "").split(";") if p.strip()],
                    critica=fila.get("critica", "").strip().upper() in ("S", "SI", "SÍ", "1", "TRUE"),
                )
            if fila.get("material", "").strip():
                tareas[tid].materiales.append(Material(
                    nombre=fila["material"].strip(),
                    cantidad=float(fila["cantidad"] or 0),
                    unidad=fila["unidad"].strip(),
                    proveedor=fila.get("proveedor", "").strip(),
                    plazo_dias=int(fila["plazo_entrega_dias"] or 0),
                ))
    return tareas


# --- calendario -----------------------------------------------------------

def es_habil(d: date) -> bool:
    return d.weekday() < 5 and (d.month, d.day) not in FERIADOS_FIJOS


def proximo_habil(d: date) -> date:
    d += timedelta(days=1)
    while not es_habil(d):
        d += timedelta(days=1)
    return d


def restar_habiles(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if es_habil(d):
            n -= 1
    return d


# --- avance ---------------------------------------------------------------

def pct_previsto(t: Tarea, dia: date) -> float:
    if dia < t.inicio:
        return 0.0
    if dia >= t.fin:
        return 100.0
    return round(((dia - t.inicio).days + 1) / ((t.fin - t.inicio).days + 1) * 100, 1)


def activas(tareas: dict[str, Tarea], dia: date) -> list[Tarea]:
    return [t for t in tareas.values() if t.inicio <= dia <= t.fin]


def avance_obra(obra_id: str, tareas: dict[str, Tarea], dia: date) -> tuple[float, float]:
    """Avance real y previsto de la obra (promedio simple de tareas), en %."""
    if not tareas:
        return 0.0, 0.0
    reales = db.ultimos_avances(obra_id, dia.isoformat())
    real = sum(reales.get(t.id, 100.0 if t.fin < dia else 0.0) for t in tareas.values()) / len(tareas)
    previsto = sum(pct_previsto(t, dia) for t in tareas.values()) / len(tareas)
    return round(real, 1), round(previsto, 1)


def _normalizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return [p for p in re.findall(r"[a-z0-9°]+", texto) if len(p) > 2]


def buscar(tareas: dict[str, Tarea], texto: str, dia: date) -> list[Tarea]:
    """Tareas cuyo nombre o rubro comparte palabras con el texto. Prioriza las activas cerca del día."""
    palabras = set(_normalizar(texto))
    puntajes = []
    for t in tareas.values():
        comunes = palabras & set(_normalizar(f"{t.nombre} {t.rubro}"))
        if comunes:
            cercania = 1 if t.inicio - timedelta(days=7) <= dia <= t.fin + timedelta(days=7) else 0
            puntajes.append((len(comunes) + cercania, t))
    puntajes.sort(key=lambda p: -p[0])
    return [t for _, t in puntajes[:5]]


# --- previsión de materiales ------------------------------------------------

def alertas_materiales(obra_id: str, tareas: dict[str, Tarea], hoy: date,
                       incluir_verdes: bool = False) -> list[dict]:
    """Fecha límite de pedido = inicio de la tarea − plazo de entrega − margen (días hábiles)."""
    alertas = []
    for t in tareas.values():
        if t.inicio <= hoy:  # tarea ya empezada: el faltante se informa como material faltante
            continue
        for m in t.materiales:
            pedido = db.obtener_pedido(obra_id, t.id, m.nombre)
            if pedido and pedido["estado"] in ("pedido", "recibido", "no_aplica"):
                continue
            stock = db.ultimo_stock(obra_id, m.nombre)
            if stock and stock["cantidad"] >= m.cantidad:
                continue
            limite = restar_habiles(t.inicio, m.plazo_dias + config.MARGEN_PEDIDO_DIAS)
            dias = (limite - hoy).days
            if dias > 7:
                nivel = "verde"
            elif dias >= 0:
                nivel = "amarillo"
            else:
                nivel = "critico" if t.critica else "rojo"
            if nivel == "verde" and not incluir_verdes:
                continue
            alertas.append({
                "nivel": nivel,
                "id_tarea": t.id,
                "tarea": t.nombre,
                "inicio_tarea": t.inicio.isoformat(),
                "material": m.nombre,
                "cantidad": m.cantidad,
                "unidad": m.unidad,
                "proveedor": m.proveedor,
                "plazo_entrega_dias": m.plazo_dias,
                "fecha_limite_pedido": limite.isoformat(),
                "dias_para_limite": dias,
                "stock_declarado": stock["cantidad"] if stock else None,
            })
    orden = {"critico": 0, "rojo": 1, "amarillo": 2, "verde": 3}
    alertas.sort(key=lambda a: (orden[a["nivel"]], a["fecha_limite_pedido"]))
    return alertas
