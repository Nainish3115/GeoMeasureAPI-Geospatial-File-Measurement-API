"""Repository for persisting and querying FileModel entities."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FileModel
from app.models.file import FileStatus


class FileRepository:
    """Encapsulates database operations for uploaded files."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        file_id: UUID,
        original_filename: str,
        stored_filename: str,
        file_extension: str,
        file_size: int,
        status: FileStatus = FileStatus.UPLOADED,
    ) -> FileModel:
        """Create and persist a new FileModel record."""
        record = FileModel(
            id=str(file_id),
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_extension=file_extension,
            file_size=file_size,
            status=status.value if hasattr(status, "value") else str(status),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, file_id: UUID | str) -> Optional[FileModel]:
        """Query a single file by primary key."""
        str_id = str(file_id)
        stmt = select(FileModel).where(FileModel.id == str_id)
        return self.db.scalars(stmt).first()

    def update_status(
        self,
        file_id: UUID | str,
        status: FileStatus,
        processing_error: Optional[str] = None,
    ) -> Optional[FileModel]:
        """Update file status and optional error message."""
        record = self.get_by_id(file_id)
        if record:
            record.status = status.value if hasattr(status, "value") else str(status)
            record.processing_error = processing_error
            self.db.commit()
            self.db.refresh(record)
        return record

    def update_metadata(
        self,
        file_id: UUID | str,
        source_format: str,
        crs: Optional[str],
        feature_count: int,
        status: FileStatus = FileStatus.COMPLETED,
    ) -> Optional[FileModel]:
        """Update geospatial processing metadata and mark status as COMPLETED."""
        record = self.get_by_id(file_id)
        if record:
            record.source_format = source_format
            record.crs = crs
            record.feature_count = feature_count
            record.status = status.value if hasattr(status, "value") else str(status)
            record.processing_error = None
            self.db.commit()
            self.db.refresh(record)
        return record
