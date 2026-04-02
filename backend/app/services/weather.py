"""OpenWeatherMap (current + 24h forecast) + WAQI — real APIs; mocks only if ALLOW_MOCKS=true."""

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.services.errors import IntegrationError


@dataclass
class WeatherSnapshot:
    rain_mm_day: float
    rain_mm_hour: float
    temp_c: float
    heat_trigger: bool
    rain_trigger: bool
    source: str
    forecast_rain_24h_mm: float
    max_temp_next_24h: float


@dataclass
class AQISnapshot:
    aqi_us: float
    severe_pollution: bool
    source: str


def _mock_weather() -> WeatherSnapshot:
    return WeatherSnapshot(
        rain_mm_day=12.0,
        rain_mm_hour=2.0,
        temp_c=36.0,
        heat_trigger=False,
        rain_trigger=False,
        source="mock",
        forecast_rain_24h_mm=10.0,
        max_temp_next_24h=35.0,
    )


def _mock_aqi() -> AQISnapshot:
    return AQISnapshot(aqi_us=80.0, severe_pollution=False, source="mock")


async def fetch_openweather(lat: float, lon: float) -> WeatherSnapshot:
    key = settings.openweather_api_key
    if not key:
        if settings.allow_mocks:
            return _mock_weather()
        raise IntegrationError(
            "Set OPENWEATHER_API_KEY in .env for live weather (or ALLOW_MOCKS=true for dev).",
            "openweather",
        )

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r_cur = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
            )
            r_cur.raise_for_status()
            cur = r_cur.json()

            r_fc = await client.get(
                "https://api.openweathermap.org/data/2.5/forecast",
                params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
            )
            r_fc.raise_for_status()
            fc = r_fc.json()
    except httpx.HTTPStatusError as e:
        raise IntegrationError(
            f"OpenWeather HTTP {e.response.status_code} — invalid key, billing, or API not enabled for this key.",
            "openweather",
        ) from e
    except httpx.RequestError as e:
        raise IntegrationError(f"OpenWeather network error: {e}", "openweather") from e

    rain_cur = cur.get("rain") or {}
    mm_h = float(rain_cur.get("1h", 0) or 0)
    if mm_h == 0 and rain_cur.get("3h"):
        mm_h = float(rain_cur["3h"]) / 3.0

    temp_now = float(cur["main"]["temp"])

    # Next 24h = first 8 slots × 3h
    slots = fc.get("list", [])[:8]
    rain_24 = 0.0
    max_t_24 = temp_now
    temps_above_40 = 0
    max_3h_rain = 0.0
    for it in slots:
        main = it.get("main") or {}
        max_t_24 = max(max_t_24, float(main.get("temp_max", main.get("temp", 0))))
        tavg = float(main.get("temp", temp_now))
        if tavg > 40:
            temps_above_40 += 1
        rn = it.get("rain") or {}
        h3 = float(rn.get("3h", 0) or 0)
        rain_24 += h3
        max_3h_rain = max(max_3h_rain, h3)

    # README: heavy rain >50mm/day OR >20mm/hr (use max 3h rate as mm/h proxy)
    mm_h_rate = max(mm_h, max_3h_rain / 3.0 if max_3h_rain else 0.0)
    rain_tr = rain_24 > 50 or mm_h_rate > 20
    # README: extreme heat >40°C sustained 3+ hours → ≥2 consecutive 3h slots above 40°C (6h)
    heat_tr = temps_above_40 >= 2 or max_t_24 > 42

    return WeatherSnapshot(
        rain_mm_day=max(rain_24, mm_h * 8.0),
        rain_mm_hour=mm_h_rate,
        temp_c=temp_now,
        heat_trigger=heat_tr,
        rain_trigger=rain_tr,
        source="openweathermap",
        forecast_rain_24h_mm=round(rain_24, 2),
        max_temp_next_24h=round(max_t_24, 2),
    )


async def fetch_waqi(lat: float, lon: float) -> AQISnapshot:
    token = settings.waqi_api_token
    if not token:
        if settings.allow_mocks:
            return _mock_aqi()
        raise IntegrationError(
            "Set WAQI_API_TOKEN in .env for live AQI (or ALLOW_MOCKS=true for dev).",
            "waqi",
        )

    url = f"https://api.waqi.info/feed/geo:{lat};{lon}/"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, params={"token": token})
            r.raise_for_status()
            j = r.json()
    except Exception as e:
        raise IntegrationError(f"WAQI HTTP error: {e}", "waqi") from e

    if j.get("status") != "ok":
        # Very common: no monitoring station near this GPS — do not fail whole /monitoring/live
        return AQISnapshot(
            aqi_us=0.0,
            severe_pollution=False,
            source="waqi_no_station",
        )

    data = j.get("data")
    if not isinstance(data, dict):
        return AQISnapshot(0.0, False, "waqi_bad_payload")

    raw_aq = data.get("aqi")
    if raw_aq in (None, "-", ""):
        return AQISnapshot(0.0, False, "waqi_no_reading")
    try:
        aqi = float(raw_aq)
    except (TypeError, ValueError):
        return AQISnapshot(0.0, False, "waqi_unparseable")

    return AQISnapshot(aqi_us=aqi, severe_pollution=aqi > 300, source="waqi")


async def fetch_openweather_air_pollution(lat: float, lon: float) -> AQISnapshot | None:
    """
    Free tier: same OPENWEATHER_API_KEY as weather.
    https://openweathermap.org/api/air-pollution
    Used when WAQI has no station nearby.
    """
    key = settings.openweather_api_key
    if not key:
        return None
    url = "https://api.openweathermap.org/data/2.5/air_pollution"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url, params={"lat": lat, "lon": lon, "appid": key})
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None
    lst = data.get("list") or []
    if not lst:
        return None
    item = lst[0]
    main = item.get("main") or {}
    comp = item.get("components") or {}
    # OWM index 1=good … 5=very poor — map to rough US AQI scale for UI
    owm_idx = int(main.get("aqi", 1))
    approx_us = {1: 45.0, 2: 95.0, 3: 145.0, 4: 205.0, 5: 320.0}.get(owm_idx, 100.0)
    pm25 = float(comp.get("pm2_5") or 0)
    # Align severe air trigger with README (AQI > 300) using PM2.5 / index
    severe = approx_us > 300 or owm_idx >= 5 or pm25 > 125.4
    return AQISnapshot(
        aqi_us=approx_us,
        severe_pollution=severe,
        source="openweather_air_pollution",
    )


async def fetch_all_triggers(lat: float, lon: float) -> dict[str, Any]:
    w = await fetch_openweather(lat, lon)
    a = await fetch_waqi(lat, lon)
    # Free fallback when no WAQI station (same OpenWeather key)
    if (
        a.source in ("waqi_no_station", "waqi_no_reading", "waqi_bad_payload", "waqi_unparseable")
        or (a.aqi_us == 0.0 and not a.severe_pollution)
    ):
        ow_air = await fetch_openweather_air_pollution(lat, lon)
        if ow_air is not None:
            a = ow_air
    return {
        "weather": {
            "rain_mm_day": w.rain_mm_day,
            "rain_mm_hour": w.rain_mm_hour,
            "temp_c": w.temp_c,
            "forecast_rain_24h_mm": w.forecast_rain_24h_mm,
            "max_temp_next_24h": w.max_temp_next_24h,
            "rain_trigger": w.rain_trigger,
            "heat_trigger": w.heat_trigger,
            "source": w.source,
        },
        "aqi": {
            "aqi_us": a.aqi_us,
            "severe_pollution": a.severe_pollution,
            "source": a.source,
            "pm2_5_estimated": a.source == "openweather_air_pollution",
        },
    }
