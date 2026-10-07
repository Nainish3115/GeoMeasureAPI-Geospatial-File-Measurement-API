"""Health check router."""

from fastapi import APIRouter, status

from app.schemas.health import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
    description="Returns the health status of the API.",
)
async def get_health() -> HealthResponse:
    """Return application health status."""
    return HealthResponse(status="healthy")
