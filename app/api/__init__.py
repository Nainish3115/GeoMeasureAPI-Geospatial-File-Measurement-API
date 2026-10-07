"""API root router aggregating all route modules."""

from fastapi import APIRouter

from app.api.routes import files, health
from app.core.config import settings

api_router = APIRouter()

# Health router at root level: /health
api_router.include_router(health.router)

# Versioned/prefixed routes: /api/files/
api_router.include_router(files.router, prefix=settings.API_V1_PREFIX)
