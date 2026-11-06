"""Live weather via Open-Meteo (no API key)."""

from __future__ import annotations

from typing import Any

import httpx

WMO_CODES: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


class WeatherError(RuntimeError):
    pass


def _describe(code: int | None) -> str:
    if code is None:
        return "unknown conditions"
    return WMO_CODES.get(int(code), f"weather code {code}")


async def lookup_weather(location: str, units: str = "metric") -> dict[str, Any]:
    place = (location or "").strip()
    if not place or len(place) > 120:
        raise WeatherError("Provide a city or place name (1–120 characters).")
    unit = (units or "metric").lower().strip()
    if unit not in {"metric", "imperial"}:
        unit = "metric"
    temp_unit = "fahrenheit" if unit == "imperial" else "celsius"
    wind_unit = "mph" if unit == "imperial" else "kmh"

    headers = {"User-Agent": "JARVIS-Weather/1.0"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=True, headers=headers) as client:
            geo = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": place, "count": 1, "language": "en", "format": "json"},
            )
            if geo.is_error:
                raise WeatherError(f"Geocoding failed (HTTP {geo.status_code}).")
            geo_data = geo.json()
            results = geo_data.get("results") if isinstance(geo_data, dict) else None
            if not isinstance(results, list) or not results:
                raise WeatherError(f"No matching place found for “{place}”.")
            hit = results[0]
            lat = hit.get("latitude")
            lon = hit.get("longitude")
            if lat is None or lon is None:
                raise WeatherError("Geocoding returned an incomplete location.")
            forecast = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                    "temperature_unit": temp_unit,
                    "wind_speed_unit": wind_unit,
                },
            )
            if forecast.is_error:
                raise WeatherError(f"Forecast failed (HTTP {forecast.status_code}).")
            data = forecast.json()
    except httpx.HTTPError as exc:
        raise WeatherError("Weather service is unreachable right now.") from exc

    current = data.get("current") if isinstance(data, dict) else {}
    daily = data.get("daily") if isinstance(data, dict) else {}
    if not isinstance(current, dict):
        current = {}
    if not isinstance(daily, dict):
        daily = {}

    days: list[dict[str, Any]] = []
    times = daily.get("time") if isinstance(daily.get("time"), list) else []
    for index, day in enumerate(times[:3]):
        days.append({
            "date": day,
            "summary": _describe((daily.get("weather_code") or [None])[index] if isinstance(daily.get("weather_code"), list) else None),
            "high": (daily.get("temperature_2m_max") or [None])[index] if isinstance(daily.get("temperature_2m_max"), list) else None,
            "low": (daily.get("temperature_2m_min") or [None])[index] if isinstance(daily.get("temperature_2m_min"), list) else None,
            "precip_probability": (daily.get("precipitation_probability_max") or [None])[index] if isinstance(daily.get("precipitation_probability_max"), list) else None,
        })

    label_parts = [str(hit.get("name") or place)]
    if hit.get("admin1"):
        label_parts.append(str(hit["admin1"]))
    if hit.get("country"):
        label_parts.append(str(hit["country"]))

    return {
        "provider": "open-meteo",
        "location": ", ".join(label_parts),
        "latitude": lat,
        "longitude": lon,
        "units": unit,
        "current": {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "summary": _describe(current.get("weather_code")),
            "observed_at": current.get("time"),
        },
        "forecast": days,
        "note": "Live weather from Open-Meteo. Treat as factual tool data.",
    }
