"""File upload and retrieval routes."""

from fastapi import APIRouter, File, UploadFile, status

from app.schemas.files import FileUploadResponse
from app.services.file_service import file_service

router = APIRouter(prefix="/files", tags=["Files"])


@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload geospatial file",
    description="Upload a .kml file or a .zip file containing a Shapefile for future geospatial measurement.",
)
async def upload_file(
    file: UploadFile = File(..., description="Geospatial file (.kml or .zip)"),
) -> FileUploadResponse:
    """Accept and securely store uploaded geospatial file."""
    record = await file_service.save_uploaded_file(file)
    return FileUploadResponse(
        id=record.id,
        filename=record.original_filename,
        status=record.status,
    )
