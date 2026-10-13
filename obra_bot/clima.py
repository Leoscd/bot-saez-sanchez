"""Clima del día por ubicación de la obra (Open-Meteo, gratis y sin API key)."""
import logging
from datetime import date

import httpx

from . import config

log = logging.getLogger(__name__)

# Códigos WMO resumidos
WMO = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Niebla", 48: "Niebla", 51: "Llovizna", 53: "Llovizna", 55: "Llovizna intensa",
    61: "Lluvia débil", 63: "Lluvia", 65: "Lluvia fuerte", 80: "Chaparrones", 81: "Chaparrones",
    82: "Chaparrones fuertes", 95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo",
}


async def del_dia(lat: float, lon: float, dia: date) -> dict | None:
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "hourly": "weather_code",
        "timezone": str(config.TZ),
        "start_date": dia.isoformat(),
        "end_date": dia.isoformat(),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get("https://api.open-meteo.com/v1/forecast", params=params)
            r.raise_for_status()
            d = r.json()
    except httpx.HTTPError as e:
        log.warning("No se pudo obtener el clima: %s", e)
        return None

    codigos = d["hourly"]["weather_code"]
    # Mañana: peor código entre 8 y 12 h; tarde: entre 13 y 18 h
    manana = max(codigos[8:13])
    tarde = max(codigos[13:19])
    return {
        "clima_manana": WMO.get(manana, f"Código {manana}"),
        "clima_tarde": WMO.get(tarde, f"Código {tarde}"),
        "temp_max": d["daily"]["temperature_2m_max"][0],
        "temp_min": d["daily"]["temperature_2m_min"][0],
        "lluvia_mm": d["daily"]["precipitation_sum"][0],
        "fuente": "Open-Meteo",
    }
