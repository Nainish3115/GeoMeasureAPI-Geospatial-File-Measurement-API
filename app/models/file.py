"""Data and domain models for geospatial entities, measurements, and file records."""

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


class MeasurementStatus(str, Enum):
    """Status of a feature measurement operation."""

    SUCCESS = "SUCCESS"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MeasurementType(str, Enum):
    """Type of geometric measurement calculated."""

    AREA = "AREA"
    LENGTH = "LENGTH"


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
class FeatureMeasurement:
    """Domain model representing a single feature's measurement result."""

    feature_id: int
    geometry_type: str | None
    measurement_status: MeasurementStatus
    measurement_type: MeasurementType | None = None
    value: float | None = None
    unit: str | None = None
    source_crs: str | None = None
    measurement_crs: str | None = None
    reason: str | None = None


@dataclass
class FileMeasurementSet:
    """Domain model aggregating all feature measurements for a file."""

    file_id: UUID
    source_crs: str | None
    measurement_crs: str | None
    results: list[FeatureMeasurement] = field(default_factory=list)


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
