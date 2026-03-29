"""Agent execution routes — /agents/{name}/run."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.weather.models import WeatherAgentResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


class WeatherRunRequest(BaseModel):
    """Optional overrides for the weather agent."""

    latitude: float = Field(39.5296, description="Location latitude")
    longitude: float = Field(-119.8138, description="Location longitude")
    location_name: str = Field("Reno, NV", description="Location display name")


@router.post("/weather/run", response_model=WeatherAgentResult)
async def run_weather_agent(
    request: WeatherRunRequest = WeatherRunRequest(),
) -> WeatherAgentResult:
    """Run the weather agent and return structured results."""
    from main import db, llm, search

    from agents.weather import WeatherAgent

    agent = WeatherAgent(llm=llm, db=db, search=search)
    try:
        result = await agent.run(
            latitude=request.latitude,
            longitude=request.longitude,
            location_name=request.location_name,
        )
        return result
    except Exception as exc:
        logger.error("Weather agent failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
