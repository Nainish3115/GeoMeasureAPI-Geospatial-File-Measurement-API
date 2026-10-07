"""File upload, retrieval, and measurement routes."""

from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.exceptions import FileNotFoundHTTPError
from app.models.file import FileStatus
from app.schemas.files import (
    FeatureMeasurementResponse,
    FileDetailResponse,
    FileMeasurementsResponse,
    FileUploadResponse,
)
from app.services.file_service import file_service
from app.services.measurement_service import measurement_service

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


@router.get(
    "/{file_id}/measurements/",
    response_model=FileMeasurementsResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate and retrieve geospatial measurements",
    description="Computes Polygon areas (m²) and LineString lengths (m) using automated projected CRS reprojection.",
)
async def get_file_measurements(file_id: UUID) -> FileMeasurementsResponse:
    """Compute and retrieve CRS-aware measurements for all features in the file."""
    record = file_service.get_record(file_id)
    if record is None:
        raise FileNotFoundHTTPError("File not found.")

    if record.status == FileStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Measurements unavailable because file processing failed: {record.processing_error or 'Unknown error'}",
        )

    if record.geo_data is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File has not completed geospatial processing.",
        )

    measurement_set = measurement_service.measure_dataset(file_id, record.geo_data)

    results = [
        FeatureMeasurementResponse(
            feature_id=r.feature_id,
            geometry_type=r.geometry_type,
            measurement_status=r.measurement_status,
            measurement_type=r.measurement_type,
            value=r.value,
            unit=r.unit,
            source_crs=r.source_crs,
            measurement_crs=r.measurement_crs,
            reason=r.reason,
        )
        for r in measurement_set.results
    ]

    return FileMeasurementsResponse(
        file_id=measurement_set.file_id,
        source_crs=measurement_set.source_crs,
        measurement_crs=measurement_set.measurement_crs,
        results=results,
    )
