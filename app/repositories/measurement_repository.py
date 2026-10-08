"""Repository for persisting and querying MeasurementModel entities."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import MeasurementModel
from app.models.file import FeatureMeasurement


class MeasurementRepository:
    """Encapsulates database operations for feature measurements."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def delete_by_file_id(self, file_id: UUID | str) -> int:
        """Delete any existing measurements for a given file ID."""
        file_id_str = str(file_id)
        stmt = delete(MeasurementModel).where(MeasurementModel.file_id == file_id_str)
        result = self.db.execute(stmt)
        self.db.commit()
        return result.rowcount  # type: ignore

    def create_batch(
        self,
        file_id: UUID | str,
        measurements: List[FeatureMeasurement],
    ) -> List[MeasurementModel]:
        """Bulk insert measurements for a given file within a single transaction."""
        file_id_str = str(file_id)
        models = [
            MeasurementModel(
                file_id=file_id_str,
                feature_id=m.feature_id,
                geometry_type=m.geometry_type,
                measurement_status=m.measurement_status.value if hasattr(m.measurement_status, "value") else str(m.measurement_status),
                measurement_type=m.measurement_type.value if m.measurement_type and hasattr(m.measurement_type, "value") else (str(m.measurement_type) if m.measurement_type else None),
                value=m.value,
                unit=m.unit,
                source_crs=m.source_crs,
                measurement_crs=m.measurement_crs,
                reason=m.reason,
            )
            for m in measurements
        ]
        self.db.add_all(models)
        self.db.commit()
        return models

    def get_by_file_id(self, file_id: UUID | str) -> List[MeasurementModel]:
        """Retrieve all measurements associated with a file ordered by feature_id."""
        file_id_str = str(file_id)
        stmt = (
            select(MeasurementModel)
            .where(MeasurementModel.file_id == file_id_str)
            .order_by(MeasurementModel.feature_id)
        )
        return list(self.db.scalars(stmt).all())
