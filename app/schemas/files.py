"""Pydantic schemas for file upload requests and responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.file import FileStatus


class FileUploadResponse(BaseModel):
    """Response schema returned after a file is successfully uploaded."""

    id: UUID = Field(..., description="Unique generated identifier for the file")
    filename: str = Field(..., description="Original filename of the uploaded file")
    status: FileStatus = Field(..., description="Current processing/lifecycle status")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "sample.kml",
                "status": "UPLOADED",
            }
        },
    )


class FileMetadataResponse(FileUploadResponse):
    """Detailed file metadata schema (used for metadata lookups and internal representations)."""

    extension: str = Field(..., description="Normalized file extension")
    size_bytes: int = Field(..., description="File size in bytes")
    created_at: datetime = Field(..., description="UTC timestamp when the file was uploaded")
