"""Pydantic schema for the health check endpoint."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Health check response payload."""

    status: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy"
            }
        }
    )
