"""Pydantic schemas for file upload requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.file import FileStatus


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
