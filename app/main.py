"""FastAPI Application entrypoint."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.core.config import settings
from app.core.exceptions import FileServiceError
from app.db.database import init_db

# Configure centralized application logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("geomeasure")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Execute startup and shutdown lifecycle tasks."""
    logger.info("Initializing GeoMeasureAPI application (environment=%s)...", settings.ENVIRONMENT)
    # Initialize database tables on application startup
    init_db()
    yield
    logger.info("Shutting down GeoMeasureAPI application.")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=(
            "A production-quality REST API for ingesting geospatial files (.kml and Shapefile .zip archives), "
            "inspecting geometries and coordinate reference systems (CRS), and computing metric area and length "
            "measurements using projected coordinate reference systems."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 1. Custom domain FileServiceError handler
    @application.exception_handler(FileServiceError)
    async def file_service_error_handler(request: Request, exc: FileServiceError) -> JSONResponse:
        logger.warning("Domain exception on %s %s: status=%s detail=%s", request.method, request.url.path, exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # 2. General Starlette/FastAPI HTTPException handler
    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.warning("HTTP exception on %s %s: status=%s detail=%s", request.method, request.url.path, exc.status_code, exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    # 3. Request Validation Error handler
    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.info("Validation error on %s %s: %s", request.method, request.url.path, exc.errors())
        # Use HTTP_422_UNPROCESSABLE_CONTENT where supported to eliminate deprecation warning
        status_code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", status.HTTP_422_UNPROCESSABLE_ENTITY)
        return JSONResponse(
            status_code=status_code,
            content={"detail": exc.errors()},
        )

    # 4. Global Uncaught Exception handler: Prevents stack trace leakage to clients
    @application.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled server exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )

    application.include_router(api_router)

    return application


app = create_application()

