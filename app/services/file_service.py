"""File upload, validation, storage, and geospatial processing orchestration service."""

import logging
from pathlib import Path
import re
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    GeospatialProcessingError,
    StorageError,
    UnsupportedFileTypeError,
)
from app.db.database import SessionLocal
from app.db.models import FileModel
from app.models.file import (
    FeatureMeasurement,
    FileMeasurementSet,
    FileStatus,
    MeasurementStatus,
    MeasurementType,
)
from app.repositories.file_repository import FileRepository
from app.repositories.measurement_repository import MeasurementRepository
from app.services.geospatial_service import GeospatialService, geospatial_service
from app.services.measurement_service import MeasurementService, measurement_service

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".kml", ".zip"}
CHUNK_SIZE = 1024 * 1024  # 1 MB chunk


class FileService:
    """Service handling file validation, storage, and persistent metadata management."""

    def __init__(
        self,
        app_settings: Settings = settings,
        geo_service: GeospatialService = geospatial_service,
        meas_service: MeasurementService = measurement_service,
    ) -> None:
        self.settings = app_settings
        self.geo_service = geo_service
        self.measurement_service = meas_service

    @property
    def upload_dir(self) -> Path:
        """Ensure and return the target upload directory."""
        upload_path = self.settings.UPLOAD_DIR
        upload_path.mkdir(parents=True, exist_ok=True)
        return upload_path

    def sanitize_filename(self, filename: str | None) -> str:
        """Sanitize client-provided filename to extract clean basename across POSIX and Windows.

        Treats both '/' and '\\' as path separators regardless of the host OS,
        strips drive prefixes (e.g. C:), and guarantees that directory traversal
        components ('..', '.') and separators are completely stripped.
        """
        if not filename:
            raise UnsupportedFileTypeError("Filename cannot be empty.")

        # Normalize backslashes to forward slashes for universal path handling
        normalized = filename.replace("\\", "/").strip()
        # Remove any leading Windows drive letter prefix (e.g., 'C:/' -> '/')
        normalized = re.sub(r"^[a-zA-Z]:", "", normalized)

        # Extract the pure basename
        parts = [p for p in normalized.split("/") if p and p not in (".", "..")]
        if not parts:
            raise UnsupportedFileTypeError("Invalid filename.")

        safe_name = parts[-1].strip()
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

    async def save_and_process_file(
        self,
        upload_file: UploadFile,
        db: Session | None = None,
    ) -> FileModel:
        """Stream uploaded file to disk and trigger geospatial processing and persistence.

        Transitions:
            UPLOADED -> PROCESSING -> COMPLETED (or FAILED if parsing/persistence errors occur).
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

        # Step 2: Create DB record & process
        session = db if db is not None else SessionLocal()
        should_close = db is None

        try:
            file_repo = FileRepository(session)
            meas_repo = MeasurementRepository(session)

            file_record = file_repo.create(
                file_id=file_id,
                original_filename=safe_filename,
                stored_filename=stored_filename,
                file_extension=extension,
                file_size=total_bytes,
                status=FileStatus.UPLOADED,
            )
            logger.info("Uploaded file accepted: id=%s filename=%s size=%d bytes", file_id, safe_filename, total_bytes)

            # Process geospatial content
            self._process_record(file_record, destination_path, file_repo, meas_repo)
            return file_record

        except Exception:
            session.rollback()
            if destination_path.exists():
                try:
                    destination_path.unlink()
                except OSError as cleanup_err:
                    logger.warning("Failed to clean up file %s on DB error: %s", destination_path, cleanup_err)
            raise
        finally:
            if should_close:
                session.close()

    def _process_record(
        self,
        file_record: FileModel,
        file_path: Path,
        file_repo: FileRepository,
        meas_repo: MeasurementRepository,
    ) -> None:
        """Synchronously parse geospatial file, calculate measurements, and persist in DB."""
        logger.info("Starting geospatial processing for file id=%s (%s)", file_record.id, file_record.original_filename)
        file_repo.update_status(file_record.id, FileStatus.PROCESSING)
        self.geo_service.settings = self.settings

        try:
            geo_file = self.geo_service.parse_file(
                file_path=file_path,
                extension=file_record.file_extension,
                original_filename=file_record.original_filename,
            )

            # Compute measurements
            meas_set = self.measurement_service.measure_dataset(UUID(file_record.id), geo_file)

            # Persist measurements
            meas_repo.create_batch(file_record.id, meas_set.results)

            # Update file record metadata
            file_repo.update_metadata(
                file_id=file_record.id,
                source_format=geo_file.source_format,
                crs=geo_file.crs,
                feature_count=geo_file.feature_count,
                status=FileStatus.COMPLETED,
            )
            logger.info(
                "Completed geospatial processing for file id=%s: format=%s crs=%s features=%d measurements=%d",
                file_record.id,
                geo_file.source_format,
                geo_file.crs,
                geo_file.feature_count,
                len(meas_set.results),
            )

        except GeospatialProcessingError as geo_err:
            logger.warning("Geospatial processing failed for %s: %s", file_record.id, geo_err.detail)
            try:
                meas_repo.delete_by_file_id(file_record.id)
            except Exception as clean_err:
                logger.warning("Failed to clear measurements for failed file %s: %s", file_record.id, clean_err)
            file_repo.update_status(file_record.id, FileStatus.FAILED, processing_error=geo_err.detail)

        except Exception as exc:
            logger.error("Unexpected error parsing file %s: %s", file_record.id, exc, exc_info=True)
            try:
                meas_repo.delete_by_file_id(file_record.id)
            except Exception as clean_err:
                logger.warning("Failed to clear measurements for failed file %s: %s", file_record.id, clean_err)
            file_repo.update_status(
                file_record.id,
                FileStatus.FAILED,
                processing_error="An error occurred during geospatial parsing.",
            )

    def get_record(self, file_id: UUID | str, db: Session | None = None) -> FileModel | None:
        """Retrieve stored file record by ID from database."""
        session = db if db is not None else SessionLocal()
        should_close = db is None
        try:
            repo = FileRepository(session)
            return repo.get_by_id(file_id)
        finally:
            if should_close:
                session.close()

    def get_measurements(
        self,
        file_id: UUID | str,
        db: Session | None = None,
    ) -> FileMeasurementSet | None:
        """Retrieve persistent measurement set for a given file ID."""
        session = db if db is not None else SessionLocal()
        should_close = db is None
        try:
            file_repo = FileRepository(session)
            meas_repo = MeasurementRepository(session)

            file_record = file_repo.get_by_id(file_id)
            if not file_record:
                return None

            db_measurements = meas_repo.get_by_file_id(file_id)
            results = [
                FeatureMeasurement(
                    feature_id=m.feature_id,
                    geometry_type=m.geometry_type,
                    measurement_status=MeasurementStatus(m.measurement_status),
                    measurement_type=MeasurementType(m.measurement_type) if m.measurement_type else None,
                    value=m.value,
                    unit=m.unit,
                    source_crs=m.source_crs,
                    measurement_crs=m.measurement_crs,
                    reason=m.reason,
                )
                for m in db_measurements
            ]

            meas_crs = results[0].measurement_crs if results else None
            return FileMeasurementSet(
                file_id=UUID(file_record.id),
                source_crs=file_record.crs,
                measurement_crs=meas_crs,
                results=results,
            )
        finally:
            if should_close:
                session.close()


# Global singleton instance for application use
file_service = FileService()
