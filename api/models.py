"""Pydantic models for API request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ServiceHealth(BaseModel):
    """Health status for an individual service."""

    name: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status: ok, degraded, or down")
    latency_ms: float | None = Field(None, description="Last check latency in ms")
    last_checked: datetime | None = Field(None, description="Timestamp of last health check")
    detail: str | None = Field(None, description="Additional status info")


class StatusResponse(BaseModel):
    """Response schema for the /status endpoint."""

    status: str = Field(..., description="Overall platform status: ok, degraded, or down")
    version: str = Field(..., description="API version string")
    uptime_seconds: float = Field(..., description="Seconds since server start")
    hostname: str = Field(..., description="Machine hostname")
    services: list[ServiceHealth] = Field(default_factory=list, description="Per-service health")
