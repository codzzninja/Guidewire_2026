"""OpenWeatherMap + WAQI with mock fallback for hackathon demo."""

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


@dataclass
class WeatherSnapshot:
    rain_mm_day: float
    rain_mm_hour: float
    temp_c: float
    heat_trigger: bool
    rain_trigger: bool
    source: str


@dataclass
class AQISnapshot:
    aqi_us: float
    severe_pollution: bool
    source: str


async def fetch_openweather(lat: float, lon: float) -> WeatherSnapshot:
    key = settings.openweather_api_key
    if not key:
        return _mock_weather()
    url = "https://api.openweathermap.org/data/2.5/weather"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            url,
            params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
        )
        r.raise_for_status()
        data = r.json()
    rain = data.get("rain") or {}
    mm_h = float(rain.get("1h", 0) or rain.get("3h", 0) or 0)
    if mm_h > 0 and "3h" in rain:
        mm_h = float(rain["3h"]) / 3.0
    temp = float(data["main"]["temp"])
    # Approximate daily rain from weather condition + pop not in free current; use 1h as proxy scale
    mm_day = mm_h * 8.0  # rough demo scaling
    rain_tr = mm_day > 50 or mm_h > 20
    heat_tr = temp > 40
    return WeatherSnapshot(
        rain_mm_day=mm_day,
        rain_mm_hour=mm_h,
        temp_c=temp,
        heat_trigger=heat_tr,
        rain_trigger=rain_tr,
        source="openweathermap",
    )


def _mock_weather() -> WeatherSnapshot:
    return WeatherSnapshot(
        rain_mm_day=12.0,
        rain_mm_hour=2.0,
        temp_c=36.0,
        heat_trigger=False,
        rain_trigger=False,
        source="mock",
    )


async def fetch_waqi(lat: float, lon: float) -> AQISnapshot:
    token = settings.waqi_api_token
    if not token:
        return AQISnapshot(aqi_us=80.0, severe_pollution=False, source="mock")
    url = f"https://api.waqi.info/feed/geo:{lat};{lon}/"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, params={"token": token})
        r.raise_for_status()
        j = r.json()
    if j.get("status") != "ok":
        return AQISnapshot(aqi_us=120.0, severe_pollution=False, source="waqi_error")
    aqi = float(j["data"]["aqi"])
    return AQISnapshot(aqi_us=aqi, severe_pollution=aqi > 300, source="waqi")


async def fetch_all_triggers(lat: float, lon: float) -> dict[str, Any]:
    """Aggregate environmental triggers (3 of 5 automated triggers)."""
    w = await fetch_openweather(lat, lon)
    a = await fetch_waqi(lat, lon)
    return {
        "weather": {
            "rain_mm_day": w.rain_mm_day,
            "rain_mm_hour": w.rain_mm_hour,
            "temp_c": w.temp_c,
            "rain_trigger": w.rain_trigger,
            "heat_trigger": w.heat_trigger,
            "source": w.source,
        },
        "aqi": {
            "aqi_us": a.aqi_us,
            "severe_pollution": a.severe_pollution,
            "source": a.source,
        },
    }
