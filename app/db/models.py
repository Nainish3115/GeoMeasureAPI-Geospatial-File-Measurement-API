"""SQLAlchemy database models for file records and measurement entities."""

from datetime import datetime, timezone
from typing import List, Optional
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FileModel(Base):
    """Persistent database model for uploaded geospatial files."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    source_format: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UPLOADED", index=True)
    crs: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship to measurements with cascade delete
    measurements: Mapped[List["MeasurementModel"]] = relationship(
        "MeasurementModel",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="MeasurementModel.feature_id",
        lazy="selectin",
    )


class MeasurementModel(Base):
    """Persistent relational model for feature measurements."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_id: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    measurement_status: Mapped[str] = mapped_column(String(32), nullable=False)
    measurement_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_crs: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    measurement_crs: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file: Mapped["FileModel"] = relationship("FileModel", back_populates="measurements")
