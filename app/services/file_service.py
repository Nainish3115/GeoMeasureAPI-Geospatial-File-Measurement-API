"""File upload, validation, and storage service."""

import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.core.config import Settings, settings
from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    StorageError,
    UnsupportedFileTypeError,
)
from app.models.file import FileRecord, FileStatus

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".kml", ".zip"}
CHUNK_SIZE = 1024 * 1024  # 1 MB chunk


class FileService:
    """Service handling file validation, storage, and metadata management."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
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
        # Path(filename).name strips directory paths (e.g., ../../evil.kml -> evil.kml)
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

    async def save_uploaded_file(self, upload_file: UploadFile) -> FileRecord:
        """Stream uploaded file to disk with size validation and return metadata record.

        Raises:
            UnsupportedFileTypeError: If extension is unsupported or filename is invalid.
            EmptyFileError: If file is 0 bytes.
            FileTooLargeError: If file exceeds maximum configured size.
            StorageError: If an unexpected error occurs during disk write.
        """
        raw_filename = upload_file.filename
        safe_filename = self.sanitize_filename(raw_filename)
        extension = self.validate_extension(safe_filename)

        file_id = uuid4()
        # Stored filename uses UUID + lowercase extension to prevent path traversal or collision
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
            return record

        except (UnsupportedFileTypeError, EmptyFileError, FileTooLargeError):
            # Clean up partial/empty file if created
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

    def get_record(self, file_id: UUID) -> FileRecord | None:
        """Retrieve stored file record by ID."""
        return self._records.get(file_id)


# Global singleton instance for application use
file_service = FileService()
