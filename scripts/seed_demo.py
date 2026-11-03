"""Crea dos obras ficticias en Tucumán con cronogramas fechados alrededor de hoy.

Uso: python scripts/seed_demo.py [--historial]
Volver a correrlo regenera los cronogramas con fechas relativas al día en que se ejecuta.
Con --historial también carga reportes, notas, pedidos y fotos de días anteriores, para mostrar
la consulta "estoy haciendo un reemplazo, contame cómo viene la obra".
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from obra_bot import config, cronograma, db, obras, reporte  # noqa: E402

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


# --- historial demo -----------------------------------------------------------

# Reportes de los últimos días hábiles, del más viejo al más nuevo:
# (resumen, jornada, personal [(empresa, categoría, cantidad)], avances {id_tarea: (% real, descripción)},
#  faltantes [(material, cantidad, unidad)], hys, fotos [(id_tarea, descripción)])
HISTORIAL = {
    "casa-lomas": ("demo:martin", "Martín Gómez (demo)", [
        ("Se terminó la capa aisladora y arrancó la mampostería de planta baja por el frente.",
         {"tipo": "completa"}, [("Hnos. Díaz", "oficial", 2), ("Hnos. Díaz", "ayudante", 3)],
         {"T-045": (100, "Capa aisladora terminada en todo el perímetro"),
          "T-040": (12, "Primeras hiladas del frente")},
         [], {"epp_ok": True},
         [("T-045", "Capa aisladora horizontal terminada sobre viga de fundación"),
          ("T-040", "Primeras hiladas de ladrillo hueco en el frente")]),
        ("Mampostería del frente y medianera oeste. Quedan 400 ladrillos: pedir.",
         {"tipo": "completa"}, [("Hnos. Díaz", "oficial", 2), ("Hnos. Díaz", "ayudante", 3)],
         {"T-040": (22, "Frente a 1,20 m y medianera oeste empezada")},
         [], {"epp_ok": True}, [("T-040", "Medianera oeste a media altura")]),
        ("Lluvia a la mañana, se trabajó desde las 11. Se pidió ladrillo al corralón, entrega prometida para ayer.",
         {"tipo": "parcial", "horas_perdidas": 3, "causa": "lluvia"},
         [("Hnos. Díaz", "oficial", 2), ("Hnos. Díaz", "ayudante", 2)],
         {"T-040": (28, "Medianera oeste a 1,80 m")},
         [], {"epp_ok": True, "visitas": "Visita de la ART: sin observaciones"}, []),
        ("Sin ladrillos desde el mediodía: el corralón no entregó. Se adelantó limpieza y acopio.",
         {"tipo": "parcial", "horas_perdidas": 4, "causa": "falta de material"},
         [("Hnos. Díaz", "oficial", 2), ("Hnos. Díaz", "ayudante", 3)],
         {"T-040": (33, "Tabique de baño y cocina a 1 m")},
         [("Ladrillo cerámico hueco 18x18x33", 1800, "u")], {"epp_ok": True},
         [("T-040", "Tabiques de baño y cocina a un metro de altura")]),
        ("Llegó parte del ladrillo (1000 u). Se retomó mampostería del contrafrente. El comitente pidió mover una ventana.",
         {"tipo": "completa"}, [("Hnos. Díaz", "oficial", 3), ("Hnos. Díaz", "ayudante", 3)],
         {"T-040": (40, "Contrafrente a 1,50 m, faltan dinteles")},
         [], {"epp_ok": True}, [("T-040", "Contrafrente con vano de ventana del dormitorio 2")]),
    ]),
    "local-mate-de-luna": ("demo:lucia", "Lucía Ferreyra (demo)", [
        ("Canalización de la pared del salón y bandeja del depósito.",
         {"tipo": "completa"}, [("Eléctrica Norte", "oficial especializado", 1), ("Eléctrica Norte", "ayudante", 1)],
         {"L-020": (40, "Canalización salón terminada")}, [], {"epp_ok": True},
         [("L-020", "Cañerías embutidas en pared del salón")]),
        ("Cableado de circuitos de iluminación del salón.",
         {"tipo": "completa"}, [("Eléctrica Norte", "oficial especializado", 1), ("Eléctrica Norte", "ayudante", 2)],
         {"L-020": (55, "Iluminación del salón cableada")}, [], {"epp_ok": True}, []),
        ("Tablero seccional montado. Falta cablear tomas del depósito.",
         {"tipo": "completa"}, [("Eléctrica Norte", "oficial especializado", 1), ("Eléctrica Norte", "ayudante", 2)],
         {"L-020": (68, "Tablero seccional montado")}, [], {"epp_ok": True},
         [("L-020", "Tablero seccional montado y rotulado")]),
    ]),
}


def _foto_demo(path: Path, texto: str):
    img = Image.new("RGB", (800, 600), (196, 180, 160))
    dibujo = ImageDraw.Draw(img)
    dibujo.rectangle((40, 40, 760, 560), outline=(90, 70, 50), width=6)
    dibujo.text((70, 280), f"FOTO DEMO\n{texto}", fill=(40, 30, 20))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG")


def sembrar_historial(hoy: date):
    db.inicializar()
    with db.conexion() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM reportes WHERE dt_id LIKE 'demo:%'")]
        marcas = ",".join("?" * len(ids))
        if ids:
            con.execute(f"DELETE FROM fotos WHERE reporte_id IN ({marcas})", ids)
            con.execute(f"DELETE FROM notas WHERE reporte_id IN ({marcas})", ids)
        con.execute("DELETE FROM reportes WHERE dt_id LIKE 'demo:%'")
        for tabla in ("avance_tareas", "pedidos", "stock"):
            con.execute(f"DELETE FROM {tabla} WHERE obra_id IN ('casa-lomas', 'local-mate-de-luna')")

    for obra_id, (dt_id, dt_nombre, dias) in HISTORIAL.items():
        tareas = obras.obtener(obra_id).tareas
        fechas = []
        d = hoy
        for _ in dias:
            d = cronograma.restar_habiles(d, 1)
            fechas.insert(0, d)
        tareas_previas = {"casa-lomas": ["T-010", "T-020", "T-030"], "local-mate-de-luna": ["L-010"]}[obra_id]
        for tid in tareas_previas:
            db.guardar_avance(obra_id, tid, cronograma.restar_habiles(fechas[0], 1).isoformat(), 100)

        for numero, (fecha, (resumen, jornada, personal, avances, faltantes, hys, fotos)) in \
                enumerate(zip(fechas, dias), start=1):
            datos = reporte.datos_iniciales()
            datos.update({
                "condiciones": {"clima_manana": "nublado" if jornada.get("causa") == "lluvia" else "soleado",
                                "clima_tarde": "soleado", "terreno": "seco", "confirmado": True},
                "jornada": jornada,
                "personal": [{"empresa": e, "categoria": c, "cantidad": n, "horas": 8} for e, c, n in personal],
                "avances": [{"id_tarea": t, "tarea": tareas[t].nombre, "rubro": tareas[t].rubro,
                             "descripcion": desc, "pct_real": pct,
                             "pct_previsto": cronograma.pct_previsto(tareas[t], fecha),
                             "desvio": round(pct - cronograma.pct_previsto(tareas[t], fecha), 1)}
                            for t, (pct, desc) in avances.items()],
                "materiales": {"ingresos": [], "stock": [], "faltantes": [
                    {"tipo": "faltante", "material": m, "cantidad": c, "unidad": u} for m, c, u in faltantes]},
                "hys": hys, "resumen": resumen, "listo": True, "proveedor": config.LLM_PROVIDER,
            })
            rid = db.crear_reporte(obra_id, fecha.isoformat(), dt_id, dt_nombre, dt_id, datos)
            db.actualizar_reporte(rid, "confirmado", numero, datos, [])
            for tid, (pct, _) in avances.items():
                db.guardar_avance(obra_id, tid, fecha.isoformat(), pct)
            for i, (tid, desc) in enumerate(fotos, start=1):
                path = config.FOTOS_DIR / obra_id / fecha.isoformat() / f"demo_{i}.jpg"
                _foto_demo(path, f"{fecha.isoformat()} - {desc}")
                fid = db.agregar_foto(rid, str(path), "12:00", desc)
                db.vincular_foto(fid, rid, tid, desc)
        ultimo_reporte = rid

        if obra_id == "casa-lomas":
            db.crear_nota(obra_id, "nota_de_pedido", fechas[-1].isoformat(), "Comitente (Sr. Pérez)", dt_nombre,
                          "Cambio de ubicación de ventana del dormitorio 2",
                          "Solicito desplazar 60 cm hacia el placard la ventana del dormitorio 2, manteniendo "
                          "las medidas del vano. Aguardo confirmación de costo y plazo.",
                          (hoy + timedelta(days=3)).isoformat(), False, ultimo_reporte)
            db.crear_nota(obra_id, "orden_de_servicio", fechas[-3].isoformat(), dt_nombre, "Hnos. Díaz",
                          "Dinteles en vanos del contrafrente",
                          "Ejecutar dinteles de H°A° en los vanos del contrafrente antes de continuar la "
                          "mampostería por encima de 2,00 m.", (hoy - timedelta(days=1)).isoformat(), False,
                          ultimo_reporte)
            db.guardar_pedido(obra_id, "T-040", "Ladrillo cerámico hueco 18x18x33", "pedido",
                              fechas[2].isoformat(), fechas[3].isoformat())
            db.guardar_pedido(obra_id, "T-070", "Hierro aletado 8 mm", "pendiente", fechas[-1].isoformat(), None)
    print("Listo: historial demo cargado (reportes, notas, pedidos y fotos de días anteriores)")


def main():
    hoy = date.today()
    obras_json = []
    for o in OBRAS:
        escribir_cronograma(config.DATA_DIR / o["cronograma_path"], o["tareas"], hoy)
        obras_json.append({k: v for k, v in o.items() if k != "tareas"})
    config.OBRAS_FILE.write_text(json.dumps(obras_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Listo: {len(OBRAS)} obras demo en {config.OBRAS_FILE}")
    if "--historial" in sys.argv:
        sembrar_historial(hoy)


if __name__ == "__main__":
    main()
