"""Las pruebas corren sobre una carpeta de datos temporal con las obras demo y su historial.

No llaman a ninguna API real: el modelo de IA, el clima, la transcripción y la API de WhatsApp
se reemplazan por dobles de prueba.
"""
import os
import sys
import tempfile
from pathlib import Path

DATOS = tempfile.mkdtemp(prefix="obra_bot_tests_")
os.environ.update({
    "DATA_DIR": DATOS,
    "MIN_FOTOS": "1",
    "LLM_PROVIDER": "openai",
    "WHATSAPP_TOKEN": "token-de-prueba",
    "WHATSAPP_PHONE_NUMBER_ID": "111",
    "WHATSAPP_APP_SECRET": "secreto-de-prueba",
    "WHATSAPP_VERIFY_TOKEN": "verificacion-de-prueba",
})
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import pytest  # noqa: E402

import seed_demo  # noqa: E402
from obra_bot import clima  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def datos_demo():
    sys.argv = ["seed_demo.py", "--historial"]
    seed_demo.main()


@pytest.fixture(autouse=True)
def sin_clima(monkeypatch):
    async def clima_fijo(lat, lon, dia):
        return {"manana": "soleado", "tarde": "soleado", "temp_max": 28, "temp_min": 16, "lluvia_mm": 0}
    monkeypatch.setattr(clima, "del_dia", clima_fijo)
