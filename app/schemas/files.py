"""Pydantic schemas for file upload requests, responses, and measurement results."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.file import FileStatus, MeasurementStatus, MeasurementType


class FileUploadResponse(BaseModel):
    """Response schema returned after a file is successfully uploaded/processed."""

    id: UUID = Field(..., description="Unique generated identifier for the file")
    filename: str = Field(..., description="Original filename of the uploaded file")
    status: FileStatus = Field(..., description="Current processing/lifecycle status")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "sample.kml",
                "status": "COMPLETED",
            }
        },
    )


class FileDetailResponse(BaseModel):
    """Detailed file response returned by GET /api/files/{id}/."""

    id: UUID = Field(..., description="Unique generated identifier for the file")
    filename: str = Field(..., description="Original filename of the uploaded file")
    status: FileStatus = Field(..., description="Current processing/lifecycle status")
    source_format: str | None = Field(None, description="Identified format of the file (e.g., KML, Shapefile)")
    crs: str | None = Field(None, description="Extracted Coordinate Reference System (e.g., EPSG:4326), or null if missing")
    feature_count: int | None = Field(None, description="Total number of geospatial features extracted")
    processing_error: str | None = Field(None, description="Safe error details if status is FAILED")
    created_at: datetime = Field(..., description="UTC timestamp when the file was uploaded")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "survey.kml",
                "status": "COMPLETED",
                "source_format": "KML",
                "crs": "EPSG:4326",
                "feature_count": 12,
                "processing_error": None,
                "created_at": "2026-10-08T02:00:00Z",
            }
        },
    )


class FileMetadataResponse(FileUploadResponse):
    """Detailed file metadata schema (used for metadata lookups and internal representations)."""

    extension: str = Field(..., description="Normalized file extension")
    size_bytes: int = Field(..., description="File size in bytes")
    created_at: datetime = Field(..., description="UTC timestamp when the file was uploaded")


class FeatureMeasurementResponse(BaseModel):
    """Measurement outcome for an individual geospatial feature."""

    feature_id: int = Field(..., description="Deterministic index/identifier of the feature")
    geometry_type: str | None = Field(None, description="Geometry type (Polygon, LineString, Point, etc.)")
    measurement_status: MeasurementStatus = Field(..., description="Status (SUCCESS, NOT_APPLICABLE, UNAVAILABLE)")
    measurement_type: MeasurementType | None = Field(None, description="Type of measurement (AREA, LENGTH, or null)")
    value: float | None = Field(None, description="Measured numeric value in SI units rounded to 6 decimal places")
    unit: str | None = Field(None, description="Metric unit (m² for area, m for length, or null)")
    source_crs: str | None = Field(None, description="Source CRS of the input dataset")
    measurement_crs: str | None = Field(None, description="Projected metric CRS used for the calculation")
    reason: str | None = Field(None, description="Explanation for NOT_APPLICABLE or UNAVAILABLE status")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "feature_id": 0,
                "geometry_type": "Polygon",
                "measurement_status": "SUCCESS",
                "measurement_type": "AREA",
                "value": 12450.824512,
                "unit": "m²",
                "source_crs": "EPSG:4326",
                "measurement_crs": "EPSG:32643",
                "reason": None,
            }
        },
    )


class FileMeasurementsResponse(BaseModel):
    """Top-level response returned by GET /api/files/{id}/measurements/."""

    file_id: UUID = Field(..., description="Identifier of the measured file")
    source_crs: str | None = Field(None, description="Identified source CRS of the file")
    measurement_crs: str | None = Field(None, description="Projected metric CRS selected for measurement")
    results: list[FeatureMeasurementResponse] = Field(..., description="List of feature measurement results")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "file_id": "550e8400-e29b-41d4-a716-446655440000",
                "source_crs": "EPSG:4326",
                "measurement_crs": "EPSG:32643",
                "results": [
                    {
                        "feature_id": 0,
                        "geometry_type": "Polygon",
                        "measurement_status": "SUCCESS",
                        "measurement_type": "AREA",
                        "value": 12450.824512,
                        "unit": "m²",
                        "source_crs": "EPSG:4326",
                        "measurement_crs": "EPSG:32643",
                        "reason": None,
                    }
                ],
            }
        },
    )


class ErrorResponse(BaseModel):
    """Consistent error payload schema."""

    detail: str = Field(..., description="Human-readable description of the error")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "File not found."
            }
        }
    )
