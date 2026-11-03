"""Quién puede usar el bot por WhatsApp y en qué obras (data/equipo.json).

Formato del archivo (se edita a mano o con scripts/equipo.py):

[
  {"telefono": "5493815550000", "nombre": "Martín Gómez",
   "obras": {"casa-lomas": null, "local-mate-de-luna": "2026-11-20"}}
]

En "obras", null es sin vencimiento y una fecha es el último día habilitado (reemplazos).
"*" habilita todas las obras.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date

from . import config, obras


@dataclass
class Persona:
    telefono: str
    nombre: str
    obras: dict[str, str | None] = field(default_factory=dict)

    def obras_habilitadas(self, dia: date) -> list[str]:
        vigentes = {o for o, hasta in self.obras.items() if not hasta or hasta >= dia.isoformat()}
        todas = [o.id for o in obras.todas()]
        return todas if "*" in vigentes else [o for o in todas if o in vigentes]


def normalizar(numero: str) -> str:
    """Número en el formato de WhatsApp (solo dígitos, con código de país).

    Para celulares de Argentina deja 549 + característica + número, que es como lo informa WhatsApp:
    acepta "+54 9 381 555-0000", "0381 15 555-0000", "381 5550000", etc.
    """
    d = re.sub(r"\D", "", numero or "")
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("54"):
        d = d[3:] if d.startswith("549") else d[2:]
    elif d.startswith("0"):
        d = d.lstrip("0")  # característica con el 0 de larga distancia
    elif len(d) > 12:
        return d  # otro país
    if len(d) == 12:  # característica + 15 + número: se saca el 15
        for largo_caract in (2, 3, 4):
            if d[largo_caract:largo_caract + 2] == "15":
                d = d[:largo_caract] + d[largo_caract + 2:]
                break
    return "549" + d if len(d) == 10 else d


_cache: tuple[float, list[Persona]] | None = None


def cargar() -> list[Persona]:
    global _cache
    if not config.EQUIPO_FILE.exists():
        return []
    mtime = config.EQUIPO_FILE.stat().st_mtime
    if _cache is None or _cache[0] != mtime:
        datos = json.loads(config.EQUIPO_FILE.read_text(encoding="utf-8"))
        _cache = (mtime, [Persona(telefono=normalizar(p["telefono"]), nombre=p["nombre"],
                                  obras=p.get("obras", {})) for p in datos])
    return _cache[1]


def buscar(telefono: str) -> Persona | None:
    t = normalizar(telefono)
    return next((p for p in cargar() if p.telefono == t), None)


def guardar(personas: list[Persona]):
    datos = [{"telefono": p.telefono, "nombre": p.nombre, "obras": p.obras} for p in personas]
    config.EQUIPO_FILE.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
