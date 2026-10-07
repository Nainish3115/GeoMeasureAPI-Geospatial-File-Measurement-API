"""Data and domain models for geospatial entities and file records."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


class FileStatus(str, Enum):
    """Lifecycle status of an uploaded file."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class GeometryState(str, Enum):
    """State classification for a feature's geometry."""

    VALID = "VALID"
    EMPTY = "EMPTY"
    NULL = "NULL"
    INVALID = "INVALID"


@dataclass
class GeoFeature:
    """Normalized domain representation of an extracted geospatial feature."""

    feature_id: int
    geometry_type: str | None
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any] = field(default_factory=dict)
    geometry_state: GeometryState = GeometryState.VALID


@dataclass
class ProcessedGeoFile:
    """Normalized representation of a parsed geospatial file."""

    source_filename: str
    source_format: str
    crs: str | None
    feature_count: int
    features: list[GeoFeature] = field(default_factory=list)


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
    geo_data: ProcessedGeoFile | None = None
    processing_error: str | None = None
