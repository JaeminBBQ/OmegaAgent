"""
Async Open-Meteo Weather API client.

Provides functions to fetch current conditions, hourly forecasts, daily
forecasts, historical weather, air quality, geocoding, and elevation data
from the free Open-Meteo API (https://open-meteo.com).
No API key required.
"""

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
CLIMATE_URL = "https://climate-api.open-meteo.com/v1/climate"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

# WMO Weather interpretation codes (WW)
WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def decode_weather_code(code: int) -> str:
    """Translate a WMO weather code to a human-readable description."""
    return WMO_CODES.get(code, f"Unknown ({code})")


async def _make_request(url: str, params: dict) -> dict:
    """Send an async GET request to an Open-Meteo endpoint and return parsed JSON."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise ValueError(f"Open-Meteo API error: {data.get('reason')}")
        return data


# ---------------------------------------------------------------------------
# Tool-ready async functions
# ---------------------------------------------------------------------------

async def get_current_weather(
    latitude: float, longitude: float, temperature_unit: str = "fahrenheit"
) -> dict:
    """Get current weather conditions for a location."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "is_day",
            "precipitation",
            "rain",
            "snowfall",
            "weather_code",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        ]),
        "temperature_unit": temperature_unit,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Los_Angeles",
    }
    data = await _make_request(FORECAST_URL, params)
    current = data["current"]
    current["weather_description"] = decode_weather_code(
        current.get("weather_code", -1)
    )
    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "elevation": data.get("elevation"),
        "timezone": data.get("timezone"),
        "current": current,
        "current_units": data.get("current_units", {}),
    }


async def get_daily_forecast(
    latitude: float,
    longitude: float,
    forecast_days: int = 7,
    temperature_unit: str = "fahrenheit",
) -> dict:
    """Get a daily weather forecast for a location."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "apparent_temperature_max",
            "apparent_temperature_min",
            "sunrise",
            "sunset",
            "uv_index_max",
            "precipitation_sum",
            "rain_sum",
            "snowfall_sum",
            "precipitation_hours",
            "precipitation_probability_max",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant",
        ]),
        "temperature_unit": temperature_unit,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Los_Angeles",
        "forecast_days": forecast_days,
    }
    data = await _make_request(FORECAST_URL, params)
    daily = data["daily"]
    daily["weather_description"] = [
        decode_weather_code(c) for c in daily.get("weather_code", [])
    ]
    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "elevation": data.get("elevation"),
        "timezone": data.get("timezone"),
        "daily": daily,
        "daily_units": data.get("daily_units", {}),
    }


async def get_hourly_forecast(
    latitude: float,
    longitude: float,
    forecast_hours: int = 24,
    temperature_unit: str = "fahrenheit",
) -> dict:
    """Get an hourly weather forecast for a location."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "precipitation_probability",
            "precipitation",
            "rain",
            "snowfall",
            "snow_depth",
            "weather_code",
            "visibility",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "uv_index",
        ]),
        "temperature_unit": temperature_unit,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "America/Los_Angeles",
        "forecast_hours": forecast_hours,
    }
    data = await _make_request(FORECAST_URL, params)
    hourly = data["hourly"]
    hourly["weather_description"] = [
        decode_weather_code(c) for c in hourly.get("weather_code", [])
    ]
    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "elevation": data.get("elevation"),
        "timezone": data.get("timezone"),
        "hourly": hourly,
        "hourly_units": data.get("hourly_units", {}),
    }


async def get_air_quality(
    latitude: float, longitude: float, forecast_hours: int = 24
) -> dict:
    """Get current and forecast air quality data for a location."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join([
            "us_aqi",
            "pm10",
            "pm2_5",
            "carbon_monoxide",
            "nitrogen_dioxide",
            "sulphur_dioxide",
            "ozone",
            "uv_index",
            "uv_index_clear_sky",
        ]),
        "hourly": ",".join([
            "pm10",
            "pm2_5",
            "us_aqi",
            "us_aqi_pm2_5",
            "us_aqi_pm10",
            "us_aqi_ozone",
        ]),
        "timezone": "America/Los_Angeles",
        "forecast_hours": forecast_hours,
    }
    data = await _make_request(AIR_QUALITY_URL, params)
    return {
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "current": data.get("current", {}),
        "current_units": data.get("current_units", {}),
        "hourly": data.get("hourly", {}),
        "hourly_units": data.get("hourly_units", {}),
    }


async def geocode_location(name: str, count: int = 5) -> list:
    """Search for a location by name and return matching results with coordinates."""
    params = {"name": name, "count": count, "language": "en", "format": "json"}
    data = await _make_request(GEOCODING_URL, params)
    return data.get("results", [])
