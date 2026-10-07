"""File upload, validation, storage, and geospatial processing orchestration service."""

import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import Settings, settings
from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    GeospatialProcessingError,
    StorageError,
    UnsupportedFileTypeError,
)
from app.models.file import FileRecord, FileStatus
from app.services.geospatial_service import GeospatialService, geospatial_service

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".kml", ".zip"}
CHUNK_SIZE = 1024 * 1024  # 1 MB chunk


class FileService:
    """Service handling file validation, storage, and metadata management."""

    def __init__(
        self,
        app_settings: Settings = settings,
        geo_service: GeospatialService = geospatial_service,
    ) -> None:
        self.settings = app_settings
        self.geo_service = geo_service
        self._records: dict[UUID, FileRecord] = {}

    @property
    def upload_dir(self) -> Path:
        """Ensure and return the target upload directory."""
        upload_path = self.settings.UPLOAD_DIR
        upload_path.mkdir(parents=True, exist_ok=True)
        return upload_path

    def sanitize_filename(self, filename: str | None) -> str:
        """Sanitize client-provided filename to extract clean basename."""
        if not filename:
            raise UnsupportedFileTypeError("Filename cannot be empty.")
        safe_name = Path(filename).name.strip()
        if not safe_name:
            raise UnsupportedFileTypeError("Invalid filename.")
        return safe_name

    def validate_extension(self, filename: str) -> str:
        """Validate that file extension is supported (case-insensitive)."""
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                "Unsupported file type. Only .kml and .zip files are accepted."
            )
        return suffix

    async def save_and_process_file(self, upload_file: UploadFile) -> FileRecord:
        """Stream uploaded file to disk and trigger geospatial processing synchronously.

        Transitions:
            UPLOADED -> PROCESSING -> COMPLETED (or FAILED if parsing errors occur).
        """
        raw_filename = upload_file.filename
        safe_filename = self.sanitize_filename(raw_filename)
        extension = self.validate_extension(safe_filename)

        file_id = uuid4()
        stored_filename = f"{file_id}{extension}"
        destination_path = self.upload_dir / stored_filename

        total_bytes = 0
        max_bytes = self.settings.max_upload_size_bytes

        try:
            with open(destination_path, "wb") as buffer:
                while chunk := await upload_file.read(CHUNK_SIZE):
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise FileTooLargeError(self.settings.MAX_UPLOAD_SIZE_MB)
                    buffer.write(chunk)

            if total_bytes == 0:
                raise EmptyFileError()

            record = FileRecord(
                id=file_id,
                original_filename=safe_filename,
                stored_path=destination_path,
                extension=extension,
                size_bytes=total_bytes,
                status=FileStatus.UPLOADED,
            )
            self._records[file_id] = record

        except (UnsupportedFileTypeError, EmptyFileError, FileTooLargeError):
            if destination_path.exists():
                try:
                    destination_path.unlink()
                except OSError as cleanup_err:
                    logger.warning("Failed to clean up file %s: %s", destination_path, cleanup_err)
            raise

        except Exception as exc:
            logger.error("Unexpected error saving file %s: %s", raw_filename, exc, exc_info=True)
            if destination_path.exists():
                try:
                    destination_path.unlink()
                except OSError as cleanup_err:
                    logger.warning("Failed to clean up file %s: %s", destination_path, cleanup_err)
            raise StorageError() from exc

        finally:
            await upload_file.close()

        # Step 2: Ingest and parse geospatial content synchronously
        self._process_record(record)
        return record

    def _process_record(self, record: FileRecord) -> None:
        """Synchronously process stored geospatial file and update record status."""
        record.status = FileStatus.PROCESSING
        self.geo_service.settings = self.settings
        try:
            geo_file = self.geo_service.parse_file(
                file_path=record.stored_path,
                extension=record.extension,
                original_filename=record.original_filename,
            )
            record.geo_data = geo_file
            record.status = FileStatus.COMPLETED
            record.processing_error = None
        except GeospatialProcessingError as geo_err:
            record.status = FileStatus.FAILED
            record.processing_error = geo_err.detail
        except Exception as exc:
            logger.error("Unexpected error parsing file %s: %s", record.id, exc, exc_info=True)
            record.status = FileStatus.FAILED
            record.processing_error = "An error occurred during geospatial parsing."

    def get_record(self, file_id: UUID) -> FileRecord | None:
        """Retrieve stored file record by ID."""
        return self._records.get(file_id)


# Global singleton instance for application use
file_service = FileService()
