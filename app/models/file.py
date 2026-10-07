"""Data and domain models for file entities."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import UUID


class FileStatus(str, Enum):
    """Lifecycle status of an uploaded file."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class FileRecord:
    """Internal domain record representing an uploaded file and its metadata."""

    id: UUID
    original_filename: str
    stored_path: Path
    extension: str
    size_bytes: int
    status: FileStatus = FileStatus.UPLOADED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
