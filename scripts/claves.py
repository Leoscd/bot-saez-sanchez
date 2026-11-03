"""Carga las claves del bot en el .env sin abrir un editor.

Pide cada clave sin mostrarla en pantalla (se puede pegar). Enter deja la que ya estaba.

  python scripts/claves.py
"""
import getpass
import re
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
CLAVES = [
    ("OPENAI_API_KEY", "Clave de OpenAI (platform.openai.com > API keys)"),
    ("WHATSAPP_TOKEN", "Token de Meta (Paso 1 > Generar token)"),
    ("WHATSAPP_APP_SECRET", "Clave secreta de la app (Configuración de la app > Básica)"),
]


def main():
    if not ENV.exists():
        sys.exit(f"No existe {ENV}. Copiá primero .env.example a .env")
    texto = ENV.read_text(encoding="utf-8")
    for nombre, ayuda in CLAVES:
        actual = re.search(rf"^{nombre}=(.*)$", texto, re.M)
        estado = "ya cargada, Enter para dejarla" if actual and actual.group(1).strip() else "vacía"
        valor = getpass.getpass(f"{ayuda} [{estado}]: ").strip()
        if not valor:
            continue
        linea = f"{nombre}={valor}"
        if actual:
            texto = re.sub(rf"^{nombre}=.*$", lambda _: linea, texto, flags=re.M)
        else:
            texto = texto.rstrip("\n") + f"\n{linea}\n"
        print(f"  {nombre}: cargada ({len(valor)} caracteres)")
    ENV.write_text(texto, encoding="utf-8")  # el archivo existente conserva su dueño
    ENV.chmod(0o600)
    print("Listo.")


if __name__ == "__main__":
    main()
