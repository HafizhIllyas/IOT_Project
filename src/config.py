"""Configuration constants and timezone helpers for the Seri Iskandar Weather IoT System."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = BASE_DIR / "docs"
FIGURES_DIR = DOCS_DIR / "figures"
DB_PATH = DATA_DIR / "weather_iot.db"

# Target Location: Seri Iskandar / Universiti Teknologi PETRONAS (UTP), Perak, Malaysia
LOCATION_NAME = "Seri Iskandar, Perak, Malaysia (UTP Campus)"
LATITUDE = 4.3590
LONGITUDE = 100.9849
ELEVATION_M = 36.0
TIMEZONE = "Asia/Kuala_Lumpur"
MYT_TZ = ZoneInfo(TIMEZONE)

# Open-Meteo Endpoints
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

# Forecast horizons (hours ahead) evaluated in the system
FORECAST_HORIZONS = [1, 3, 6, 12, 24, 48]

# Rain classification threshold (mm/h) per WMO / MetMalaysia
RAIN_EVENT_THRESHOLD_MM = 0.1

# WMO Weather interpretation codes (WW)
WMO_WEATHER_CODES: dict[int, tuple[str, str, str]] = {
    0: ("Clear Sky", "☀️", "Clear"),
    1: ("Mainly Clear", "🌤️", "Clear"),
    2: ("Partly Cloudy", "⛅", "Cloudy"),
    3: ("Overcast", "☁️", "Cloudy"),
    45: ("Foggy", "🌫️", "Fog"),
    48: ("Depositing Rime Fog", "🌫️", "Fog"),
    51: ("Light Drizzle", "🌦️", "Rain"),
    53: ("Moderate Drizzle", "🌦️", "Rain"),
    55: ("Dense Drizzle", "🌧️", "Rain"),
    61: ("Slight Rain", "🌦️", "Rain"),
    63: ("Moderate Rain", "🌧️", "Rain"),
    65: ("Heavy Rain", "🌧️", "Heavy Rain"),
    80: ("Slight Rain Showers", "🌦️", "Rain"),
    81: ("Moderate Rain Showers", "🌧️", "Rain"),
    82: ("Violent Rain Showers", "⛈️", "Heavy Rain"),
    95: ("Thunderstorm", "⛈️", "Storm"),
    96: ("Thunderstorm with Hail", "⛈️", "Storm"),
    99: ("Severe Thunderstorm", "⛈️", "Storm"),
}


def now_myt() -> datetime:
    """Return current local time in Asia/Kuala_Lumpur (naive, matching Open-Meteo ISO strings)."""
    return datetime.now(MYT_TZ).replace(tzinfo=None)


def describe_wmo_code(code: int | None) -> tuple[str, str, str]:
    """Return (label, emoji, category) for a WMO weather code."""
    if code is None:
        return ("Unknown", "🌡️", "Unknown")
    return WMO_WEATHER_CODES.get(int(code), ("Variable Clouds / Rain", "🌦️", "Cloudy"))
