"""Crea dos obras ficticias en Tucumán con cronogramas fechados alrededor de hoy.

Uso: python scripts/seed_demo.py
Volver a correrlo regenera los cronogramas con fechas relativas al día en que se ejecuta.
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obra_bot import config  # noqa: E402

COLUMNAS = ["id_tarea", "rubro", "tarea", "inicio", "fin", "predecesoras", "critica",
            "material", "cantidad", "unidad", "proveedor", "plazo_entrega_dias"]

# (id, rubro, tarea, inicio, fin (días desde hoy), predecesoras, crítica, [(material, cant, unidad, proveedor, plazo)])
CASA = [
    ("T-010", "01 Trabajos preliminares", "Replanteo y obrador", -40, -36, "", "N", []),
    ("T-020", "02 Movimiento de suelos", "Excavación de bases y vigas de fundación", -35, -28, "T-010", "S", []),
    ("T-030", "03 Fundaciones", "Bases y vigas de fundación de H°A°", -27, -12, "T-020", "S",
     [("Hormigón elaborado H-21", 14, "m3", "Hormigonera del Norte", 2)]),
    ("T-040", "05 Mampostería", "Mampostería de elevación planta baja", -10, 6, "T-030", "S",
     [("Ladrillo cerámico hueco 18x18x33", 3200, "u", "Corralón San Martín", 4)]),
    ("T-045", "06 Aislaciones", "Capa aisladora horizontal", -12, -9, "T-030", "N",
     [("Hidrófugo", 40, "kg", "Corralón San Martín", 2)]),
    ("T-050", "08 Contrapisos y carpetas", "Contrapiso planta baja", 8, 12, "T-040", "S",
     [("Cemento portland", 120, "bolsas", "Corralón San Martín", 3),
      ("Arena gruesa", 6, "m3", "Áridos Lules", 2),
      ("Ripio", 8, "m3", "Áridos Lules", 2)]),
    ("T-060", "10 Instalación sanitaria", "Cañerías de desagüe planta baja", 9, 14, "T-040", "N",
     [("Caño PVC 110 mm", 24, "u", "Sanitarios Tucumán", 5)]),
    ("T-070", "04 Estructura de H°A°", "Losa sobre planta baja", 15, 25, "T-040", "S",
     [("Hierro aletado 8 mm", 1.2, "t", "Hierros del Norte", 7),
      ("Hormigón elaborado H-21", 18, "m3", "Hormigonera del Norte", 2),
      ("Viguetas pretensadas", 46, "u", "Pretensados Tucumán", 10)]),
    ("T-071", "04 Estructura de H°A°", "Inspección de armaduras de losa", 25, 25, "T-070", "S", []),
    ("T-080", "05 Mampostería", "Mampostería de elevación planta alta", 27, 40, "T-070", "N",
     [("Ladrillo común", 8000, "u", "Hornos de Famaillá", 10)]),
    ("T-090", "09 Cubiertas", "Cubierta de chapa", 41, 50, "T-080", "N",
     [("Chapa sinusoidal C25", 60, "u", "Chapas del NOA", 15)]),
]

LOCAL = [
    ("L-010", "01 Trabajos preliminares", "Demolición de tabiques y retiro de escombros", -15, -10, "", "S", []),
    ("L-020", "11 Instalación eléctrica", "Canalización y cableado", -9, 6, "L-010", "S",
     [("Cable unipolar 2,5 mm", 400, "m", "Eléctrica Mate de Luna", 3),
      ("Caja de PVC rectangular", 60, "u", "Eléctrica Mate de Luna", 3)]),
    ("L-030", "07 Revoques", "Revoque grueso y fino interior", 7, 17, "L-020", "S",
     [("Cal hidratada", 80, "bolsas", "Corralón San Martín", 2),
      ("Arena fina", 4, "m3", "Áridos Lules", 2)]),
    ("L-040", "16 Pisos y zócalos", "Porcelanato 60x60 en salón", 18, 26, "L-030", "S",
     [("Porcelanato 60x60", 180, "m2", "Cerámicos Yerba Buena", 12),
      ("Pegamento para porcelanato", 70, "bolsas", "Cerámicos Yerba Buena", 5)]),
    ("L-050", "18 Pinturas", "Pintura látex interior", 27, 34, "L-040", "N",
     [("Látex interior 20 l", 12, "baldes", "Pinturerías del Norte", 3)]),
]

OBRAS = [
    {"id": "casa-lomas", "nombre": "Casa Lomas de Tafí (demo)",
     "direccion": "Barrio Lomas de Tafí, Tafí Viejo, Tucumán", "lat": -26.7906, "lon": -65.2486,
     "cronograma_path": "cronogramas/casa-lomas.csv", "tareas": CASA},
    {"id": "local-mate-de-luna", "nombre": "Local Av. Mate de Luna (demo)",
     "direccion": "Av. Mate de Luna 2500, San Miguel de Tucumán", "lat": -26.8186, "lon": -65.2266,
     "cronograma_path": "cronogramas/local-mate-de-luna.csv", "tareas": LOCAL},
]


def escribir_cronograma(path: Path, tareas, hoy: date):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNAS)
        for tid, rubro, nombre, ini, fin, pred, crit, materiales in tareas:
            base = [tid, rubro, nombre, (hoy + timedelta(days=ini)).isoformat(),
                    (hoy + timedelta(days=fin)).isoformat(), pred, crit]
            if not materiales:
                w.writerow(base + ["", "", "", "", ""])
            for mat, cant, unidad, prov, plazo in materiales:
                w.writerow(base + [mat, cant, unidad, prov, plazo])


def main():
    hoy = date.today()
    obras_json = []
    for o in OBRAS:
        escribir_cronograma(config.DATA_DIR / o["cronograma_path"], o["tareas"], hoy)
        obras_json.append({k: v for k, v in o.items() if k != "tareas"})
    config.OBRAS_FILE.write_text(json.dumps(obras_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo: {len(OBRAS)} obras demo en {config.OBRAS_FILE}")


if __name__ == "__main__":
    main()
