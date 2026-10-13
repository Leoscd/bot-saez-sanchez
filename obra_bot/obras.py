"""Obras configuradas en data/obras.json, con su cronograma cacheado."""
import json
from dataclasses import dataclass

from . import config, cronograma


@dataclass
class Obra:
    id: str
    nombre: str
    direccion: str
    lat: float
    lon: float
    cronograma_path: str

    @property
    def tareas(self) -> dict[str, cronograma.Tarea]:
        path = config.DATA_DIR / self.cronograma_path
        mtime = path.stat().st_mtime
        cache = _CACHE.get(self.id)
        if cache is None or cache[0] != mtime:
            _CACHE[self.id] = (mtime, cronograma.cargar(path))
        return _CACHE[self.id][1]


_CACHE: dict[str, tuple[float, dict]] = {}


def todas() -> list[Obra]:
    if not config.OBRAS_FILE.exists():
        raise FileNotFoundError(
            f"No existe {config.OBRAS_FILE}. Corré primero: python scripts/seed_demo.py"
        )
    datos = json.loads(config.OBRAS_FILE.read_text(encoding="utf-8"))
    return [Obra(**o) for o in datos]


def obtener(obra_id: str) -> Obra | None:
    return next((o for o in todas() if o.id == obra_id), None)
