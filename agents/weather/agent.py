"""Weather Agent — fetches conditions + forecast, analyzes with Haiku.

Follows the standard agent pattern:
  1. Fetch data (Open-Meteo API)
  2. Analyze with Haiku
  3. Store results (Supabase — when ready)
  4. Return structured result
"""

import json
import logging
from typing import Any

from agents.weather import api
from agents.weather.models import (
    CurrentConditions,
    DayForecast,
    WeatherAgentResult,
    WeatherAlert,
)
from core.db import DBClient
from core.llm import LLMClient
from core.search import SearchClient

logger = logging.getLogger(__name__)

# Reno, NV coordinates
RENO_LAT = 39.5296
RENO_LON = -119.8138
RENO_NAME = "Reno, NV"

SUMMARY_SYSTEM_PROMPT = """You are a personal weather assistant for someone in Reno, Nevada.
Given the current conditions and 7-day forecast data, produce a concise natural language summary.
Include:
- Current conditions in one sentence
- Notable upcoming weather (storms, snow, extreme heat/cold, high wind)
- Anything actionable (bring a jacket, roads may be icy, UV is high)
Keep it under 150 words. Be direct and practical, not chatty."""

ALERT_THRESHOLDS = {
    "extreme_heat": 100.0,     # °F
    "extreme_cold": 10.0,      # °F
    "high_wind": 50.0,         # mph
    "heavy_snow": 3.0,         # inches/day
    "heavy_rain": 1.0,         # inches/day
}


class WeatherAgent:
    def __init__(self, llm: LLMClient, db: DBClient, search: SearchClient) -> None:
        self.llm = llm
        self.db = db
        self.search = search

    async def run(
        self,
        latitude: float = RENO_LAT,
        longitude: float = RENO_LON,
        location_name: str = RENO_NAME,
    ) -> WeatherAgentResult:
        """Execute the full weather agent pipeline."""

        # 1. Fetch data from Open-Meteo
        logger.info("Weather agent: fetching data for %s", location_name)
        current_data, forecast_data = await self._fetch_data(latitude, longitude)

        # 2. Parse into structured models
        current = self._parse_current(current_data)
        forecast = self._parse_forecast(forecast_data)

        # 3. Detect alert conditions
        alerts = self._check_alerts(current, forecast)

        # 4. Analyze with Haiku
        summary = await self._generate_summary(
            location_name, current, forecast, alerts
        )

        result = WeatherAgentResult(
            location=location_name,
            latitude=latitude,
            longitude=longitude,
            current=current,
            forecast=forecast,
            alerts=alerts,
            summary=summary,
        )

        # 5. Store results (when Supabase is configured)
        await self._store_result(result)

        logger.info(
            "Weather agent complete: %s, %d alerts", location_name, len(alerts)
        )
        return result

    async def should_alert(self) -> bool:
        """Check if current conditions warrant a notification."""
        current_data, forecast_data = await self._fetch_data(RENO_LAT, RENO_LON)
        current = self._parse_current(current_data)
        forecast = self._parse_forecast(forecast_data)
        alerts = self._check_alerts(current, forecast)
        return any(a.severity == "high" for a in alerts)

    # -- private helpers ------------------------------------------------------

    async def _fetch_data(
        self, lat: float, lon: float
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch current weather and 7-day forecast concurrently."""
        import asyncio

        current_task = asyncio.create_task(api.get_current_weather(lat, lon))
        forecast_task = asyncio.create_task(api.get_daily_forecast(lat, lon))
        current_data, forecast_data = await asyncio.gather(
            current_task, forecast_task
        )
        return current_data, forecast_data

    def _parse_current(self, data: dict[str, Any]) -> CurrentConditions:
        """Convert raw API response to CurrentConditions model."""
        c = data["current"]
        return CurrentConditions(
            temperature_f=c["temperature_2m"],
            feels_like_f=c["apparent_temperature"],
            humidity_pct=c["relative_humidity_2m"],
            wind_speed_mph=c["wind_speed_10m"],
            wind_gusts_mph=c.get("wind_gusts_10m"),
            wind_direction=c.get("wind_direction_10m"),
            precipitation_in=c.get("precipitation", 0.0),
            snowfall_in=c.get("snowfall", 0.0),
            weather_code=c["weather_code"],
            weather_description=c["weather_description"],
        )

    def _parse_forecast(self, data: dict[str, Any]) -> list[DayForecast]:
        """Convert raw API response to list of DayForecast models."""
        d = data["daily"]
        days = []
        for i in range(len(d.get("time", []))):
            days.append(
                DayForecast(
                    date=d["time"][i],
                    high_f=d["temperature_2m_max"][i],
                    low_f=d["temperature_2m_min"][i],
                    precip_chance_pct=d.get("precipitation_probability_max", [None])[i]
                    if i < len(d.get("precipitation_probability_max", []))
                    else None,
                    precip_total_in=d.get("precipitation_sum", [0.0])[i],
                    snowfall_in=d.get("snowfall_sum", [0.0])[i],
                    wind_max_mph=d["wind_speed_10m_max"][i],
                    weather_description=d["weather_description"][i],
                )
            )
        return days

    def _check_alerts(
        self, current: CurrentConditions, forecast: list[DayForecast]
    ) -> list[WeatherAlert]:
        """Evaluate thresholds against current + forecast data."""
        alerts: list[WeatherAlert] = []

        # Current temperature extremes
        if current.temperature_f >= ALERT_THRESHOLDS["extreme_heat"]:
            alerts.append(WeatherAlert(
                alert_type="extreme_heat",
                severity="high",
                message=f"Extreme heat: {current.temperature_f}°F",
            ))
        if current.temperature_f <= ALERT_THRESHOLDS["extreme_cold"]:
            alerts.append(WeatherAlert(
                alert_type="extreme_cold",
                severity="high",
                message=f"Extreme cold: {current.temperature_f}°F — watch for ice",
            ))

        # Current wind
        gusts = current.wind_gusts_mph or current.wind_speed_mph
        if gusts >= ALERT_THRESHOLDS["high_wind"]:
            alerts.append(WeatherAlert(
                alert_type="high_wind",
                severity="high",
                message=f"High wind gusts: {gusts} mph",
            ))

        # Forecast-based alerts (next 3 days)
        for day in forecast[:3]:
            if day.snowfall_in >= ALERT_THRESHOLDS["heavy_snow"]:
                alerts.append(WeatherAlert(
                    alert_type="heavy_snow",
                    severity="high" if day.snowfall_in >= 6.0 else "medium",
                    message=f"{day.date}: {day.snowfall_in}\" snow expected",
                ))
            if day.precip_total_in >= ALERT_THRESHOLDS["heavy_rain"] and day.snowfall_in < 0.1:
                alerts.append(WeatherAlert(
                    alert_type="heavy_rain",
                    severity="medium",
                    message=f"{day.date}: {day.precip_total_in}\" rain expected",
                ))
            if day.high_f >= ALERT_THRESHOLDS["extreme_heat"]:
                alerts.append(WeatherAlert(
                    alert_type="extreme_heat",
                    severity="medium",
                    message=f"{day.date}: high of {day.high_f}°F forecast",
                ))
            if day.low_f <= ALERT_THRESHOLDS["extreme_cold"]:
                alerts.append(WeatherAlert(
                    alert_type="extreme_cold",
                    severity="medium",
                    message=f"{day.date}: low of {day.low_f}°F forecast",
                ))

        return alerts

    async def _generate_summary(
        self,
        location: str,
        current: CurrentConditions,
        forecast: list[DayForecast],
        alerts: list[WeatherAlert],
    ) -> str:
        """Use Haiku to generate a natural language weather summary."""
        prompt = (
            f"Location: {location}\n\n"
            f"Current conditions:\n{current.model_dump_json(indent=2)}\n\n"
            f"7-day forecast:\n{json.dumps([d.model_dump() for d in forecast], indent=2)}\n\n"
            f"Active alerts:\n{json.dumps([a.model_dump() for a in alerts], indent=2)}"
        )
        try:
            summary = await self.llm.ask(
                prompt, system=SUMMARY_SYSTEM_PROMPT, max_tokens=300
            )
            return summary.strip()
        except Exception as exc:
            logger.warning("LLM summary failed, using fallback: %s", exc)
            return (
                f"{location}: {current.weather_description}, "
                f"{current.temperature_f}°F (feels like {current.feels_like_f}°F). "
                f"Wind {current.wind_speed_mph} mph."
            )

    async def _store_result(self, result: WeatherAgentResult) -> None:
        """Persist the result to Supabase (best-effort)."""
        try:
            await self.db.upsert(
                "weather_runs",
                {
                    "location": result.location,
                    "data": result.model_dump_json(),
                    "timestamp": result.timestamp.isoformat(),
                },
            )
        except Exception as exc:
            logger.debug("Skipping DB store (not configured): %s", exc)
