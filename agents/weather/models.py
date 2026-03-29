"""Pydantic models for the weather agent."""

from datetime import datetime

from pydantic import BaseModel, Field


class CurrentConditions(BaseModel):
    """Snapshot of current weather."""

    temperature_f: float = Field(..., description="Temperature in Fahrenheit")
    feels_like_f: float = Field(..., description="Apparent temperature in Fahrenheit")
    humidity_pct: float = Field(..., description="Relative humidity percentage")
    wind_speed_mph: float = Field(..., description="Wind speed in mph")
    wind_gusts_mph: float | None = Field(None, description="Wind gusts in mph")
    wind_direction: float | None = Field(None, description="Wind direction in degrees")
    precipitation_in: float = Field(0.0, description="Precipitation in inches")
    snowfall_in: float = Field(0.0, description="Snowfall in inches")
    weather_code: int = Field(..., description="WMO weather code")
    weather_description: str = Field(..., description="Human-readable weather")


class DayForecast(BaseModel):
    """Single day forecast summary."""

    date: str = Field(..., description="Date YYYY-MM-DD")
    high_f: float = Field(..., description="High temperature in Fahrenheit")
    low_f: float = Field(..., description="Low temperature in Fahrenheit")
    precip_chance_pct: float | None = Field(None, description="Max precipitation probability")
    precip_total_in: float = Field(0.0, description="Total precipitation in inches")
    snowfall_in: float = Field(0.0, description="Total snowfall in inches")
    wind_max_mph: float = Field(..., description="Max wind speed in mph")
    weather_description: str = Field(..., description="Human-readable weather")


class WeatherAlert(BaseModel):
    """Alert condition detected by the agent."""

    alert_type: str = Field(..., description="Type: extreme_heat, extreme_cold, high_wind, heavy_snow, heavy_rain, storm")
    severity: str = Field(..., description="low, medium, high")
    message: str = Field(..., description="Human-readable alert message")


class WeatherAgentResult(BaseModel):
    """Full result returned by the weather agent."""

    location: str = Field(..., description="Location name")
    latitude: float
    longitude: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    current: CurrentConditions
    forecast: list[DayForecast] = Field(default_factory=list)
    alerts: list[WeatherAlert] = Field(default_factory=list)
    summary: str = Field(..., description="LLM-generated natural language summary")
