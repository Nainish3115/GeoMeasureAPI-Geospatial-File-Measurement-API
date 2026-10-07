"""File upload and retrieval routes."""

from uuid import UUID

from fastapi import APIRouter, File, UploadFile, status

from app.core.exceptions import FileNotFoundHTTPError
from app.schemas.files import FileDetailResponse, FileUploadResponse
from app.services.file_service import file_service

router = APIRouter(prefix="/files", tags=["Files"])


@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest geospatial file",
    description="Upload a .kml file or a .zip file containing a Shapefile to extract features and CRS.",
)
async def upload_file(
    file: UploadFile = File(..., description="Geospatial file (.kml or .zip)"),
) -> FileUploadResponse:
    """Accept, securely store, and ingest uploaded geospatial file."""
    record = await file_service.save_and_process_file(file)
    return FileUploadResponse(
        id=record.id,
        filename=record.original_filename,
        status=record.status,
    )


@router.get(
    "/{file_id}",
    response_model=FileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get geospatial file details",
    description="Retrieve processing status, CRS, and feature count for an uploaded geospatial file.",
)
async def get_file_details(file_id: UUID) -> FileDetailResponse:
    """Retrieve metadata, CRS, and feature count of a processed geospatial file."""
    record = file_service.get_record(file_id)
    if record is None:
        raise FileNotFoundHTTPError("File not found.")

    geo_data = record.geo_data
    return FileDetailResponse(
        id=record.id,
        filename=record.original_filename,
        status=record.status,
        source_format=geo_data.source_format if geo_data else None,
        crs=geo_data.crs if geo_data else None,
        feature_count=geo_data.feature_count if geo_data else None,
        processing_error=record.processing_error,
        created_at=record.created_at,
    )
