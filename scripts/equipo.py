"""Alta de personas y asignación de obras para el bot de WhatsApp (data/equipo.json).

  python scripts/equipo.py listar
  python scripts/equipo.py alta "+54 9 381 555-0000" "Martín Gómez"
  python scripts/equipo.py asignar "+54 9 381 555-0000" casa-lomas
  python scripts/equipo.py asignar "+54 9 381 555-0000" local-mate-de-luna --hasta 2026-11-20   (reemplazo)
  python scripts/equipo.py asignar "+54 9 381 555-0000" "*"                                    (todas las obras)
  python scripts/equipo.py quitar "+54 9 381 555-0000" casa-lomas
  python scripts/equipo.py baja "+54 9 381 555-0000"

El bot relee el archivo solo: no hace falta reiniciarlo.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from obra_bot import equipo, obras  # noqa: E402


def _buscar(personas, telefono):
    t = equipo.normalizar(telefono)
    p = next((p for p in personas if p.telefono == t), None)
    if p is None:
        sys.exit(f"{t} no está dado de alta. Usá primero: alta")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="accion", required=True)
    sub.add_parser("listar")
    a = sub.add_parser("alta")
    a.add_argument("telefono")
    a.add_argument("nombre")
    s = sub.add_parser("asignar")
    s.add_argument("telefono")
    s.add_argument("obra", help='id de la obra (ver data/obras.json) o "*" para todas')
    s.add_argument("--hasta", help="último día habilitado, AAAA-MM-DD (para reemplazos)")
    q = sub.add_parser("quitar")
    q.add_argument("telefono")
    q.add_argument("obra")
    b = sub.add_parser("baja")
    b.add_argument("telefono")
    args = ap.parse_args()

    personas = list(equipo.cargar())

    if args.accion == "listar":
        if not personas:
            print("No hay nadie dado de alta.")
        for p in personas:
            asignadas = ", ".join(f"{o} (hasta {h})" if h else o for o, h in p.obras.items()) or "sin obras"
            print(f"{p.telefono}  {p.nombre}: {asignadas}")
        return

    if args.accion == "alta":
        t = equipo.normalizar(args.telefono)
        if any(p.telefono == t for p in personas):
            sys.exit(f"{t} ya está dado de alta.")
        personas.append(equipo.Persona(telefono=t, nombre=args.nombre))
        print(f"Alta: {args.nombre} ({t}). Ahora asignale obras con: asignar")

    elif args.accion == "asignar":
        if args.obra != "*" and not obras.obtener(args.obra):
            sys.exit(f"No existe la obra {args.obra}. Obras: {', '.join(o.id for o in obras.todas())}")
        if args.hasta:
            date.fromisoformat(args.hasta)  # valida el formato
        p = _buscar(personas, args.telefono)
        p.obras[args.obra] = args.hasta
        print(f"{p.nombre}: {args.obra}" + (f" hasta el {args.hasta}" if args.hasta else ""))

    elif args.accion == "quitar":
        p = _buscar(personas, args.telefono)
        p.obras.pop(args.obra, None)
        print(f"{p.nombre}: se quitó {args.obra}")

    elif args.accion == "baja":
        p = _buscar(personas, args.telefono)
        personas.remove(p)
        print(f"Baja: {p.nombre}")

    equipo.guardar(personas)


if __name__ == "__main__":
    main()
