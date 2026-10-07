"""Tests for persistent storage, transactions, and server restart simulation."""

import io
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.database import get_db, reset_engine, set_engine_and_sessionmaker
from app.main import create_application
from app.models.file import (
    FeatureMeasurement,
    FileStatus,
    MeasurementStatus,
    MeasurementType,
)
from app.repositories.file_repository import FileRepository
from app.repositories.measurement_repository import MeasurementRepository
from app.services.file_service import FileService, file_service
from tests.test_geospatial import sample_kml_content


def test_database_initialization_tables(tmp_path: Path) -> None:
    """Verify fresh database initializes required tables."""
    db_file = tmp_path / "fresh.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url)

    Base.metadata.create_all(bind=engine)
    table_names = engine.dialect.get_table_names(engine.connect())
    assert "files" in table_names
    assert "measurements" in table_names
    engine.dispose()


def test_file_and_measurement_persistence(
    client: TestClient,
    sample_kml_content: bytes,
    test_db_session: Session,
) -> None:
    """Verify file upload persists FileModel and MeasurementModel records in database."""
    files = {"file": ("cadastre.kml", io.BytesIO(sample_kml_content), "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    # Direct database query via repository
    file_repo = FileRepository(test_db_session)
    meas_repo = MeasurementRepository(test_db_session)

    file_rec = file_repo.get_by_id(file_id)
    assert file_rec is not None
    assert file_rec.original_filename == "cadastre.kml"
    assert file_rec.status == "COMPLETED"
    assert file_rec.source_format == "KML"
    assert file_rec.crs == "EPSG:4326"
    assert file_rec.feature_count == 3

    # Check relational measurements query
    measurements = meas_repo.get_by_file_id(file_id)
    assert len(measurements) == 3
    # Relational foreign key check
    for m in measurements:
        assert m.file_id == file_id
        assert m.measurement_crs == "EPSG:32643"


def test_persistence_survives_application_recreation(
    tmp_path: Path,
    sample_kml_content: bytes,
) -> None:
    """Verify that file metadata and measurements survive application shutdown and recreation."""
    # Shared persistent database and storage path
    shared_db = tmp_path / "shared_geomeasure.db"
    shared_uploads = tmp_path / "shared_uploads"
    shared_uploads.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{shared_db.as_posix()}"

    # 1. Instance 1: Start, upload file, and verify
    engine_1 = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine_1)
    set_engine_and_sessionmaker(engine_1)

    app_1 = create_application()
    file_service.settings = Settings(
        UPLOAD_DIR=shared_uploads,
        DATABASE_URL=db_url,
    )

    with TestClient(app_1) as client_1:
        files = {"file": ("restart_test.kml", io.BytesIO(sample_kml_content), "application/vnd.google-earth.kml+xml")}
        r_upload = client_1.post("/api/files/", files=files)
        assert r_upload.status_code == 201
        uploaded_id = r_upload.json()["id"]

    # Simulate shutdown
    engine_1.dispose()
    reset_engine()

    # 2. Instance 2: Completely fresh app instance connecting to same database
    engine_2 = create_engine(db_url, connect_args={"check_same_thread": False})
    set_engine_and_sessionmaker(engine_2)

    app_2 = create_application()
    file_service.settings = Settings(
        UPLOAD_DIR=shared_uploads,
        DATABASE_URL=db_url,
    )

    with TestClient(app_2) as client_2:
        # GET /api/files/{id}
        r_detail = client_2.get(f"/api/files/{uploaded_id}")
        assert r_detail.status_code == 200
        detail_data = r_detail.json()
        assert detail_data["id"] == uploaded_id
        assert detail_data["filename"] == "restart_test.kml"
        assert detail_data["status"] == "COMPLETED"
        assert detail_data["feature_count"] == 3
        assert detail_data["crs"] == "EPSG:4326"

        # GET /api/files/{id}/measurements/
        r_meas = client_2.get(f"/api/files/{uploaded_id}/measurements/")
        assert r_meas.status_code == 200
        meas_data = r_meas.json()
        assert meas_data["file_id"] == uploaded_id
        assert meas_data["measurement_crs"] == "EPSG:32643"
        assert len(meas_data["results"]) == 3
        assert meas_data["results"][0]["measurement_status"] == "NOT_APPLICABLE"
        assert meas_data["results"][1]["measurement_type"] == "LENGTH"
        assert meas_data["results"][2]["measurement_type"] == "AREA"

    engine_2.dispose()
    reset_engine()


def test_failed_processing_persisted(client: TestClient, test_db_session: Session) -> None:
    """Verify that processing failure reason and FAILED status are saved in database."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "not a shapefile")

    r_post = client.post("/api/files/", files={"file": ("corrupt.zip", io.BytesIO(buf.getvalue()), "application/zip")})
    assert r_post.status_code == 201
    file_id = r_post.json()["id"]

    file_repo = FileRepository(test_db_session)
    rec = file_repo.get_by_id(file_id)
    assert rec is not None
    assert rec.status == "FAILED"
    assert rec.processing_error is not None
    assert "No Shapefile" in rec.processing_error


def test_transaction_rollback_on_database_error(
    test_db_session: Session,
    tmp_path: Path,
) -> None:
    """Verify that database transaction rolls back if an error occurs during measurement batch insert."""
    file_repo = FileRepository(test_db_session)
    f_id = uuid4()
    file_rec = file_repo.create(
        file_id=f_id,
        original_filename="rollback.kml",
        stored_filename=f"{f_id}.kml",
        file_extension=".kml",
        file_size=100,
    )
    assert file_rec is not None

    meas_repo = MeasurementRepository(test_db_session)
    # Attempting to insert an invalid record that violates constraints
    try:
        # None for required non-nullable feature_id causes SQLite IntegrityError
        invalid_measurement = FeatureMeasurement(
            feature_id=None,  # type: ignore
            geometry_type="Polygon",
            measurement_status=MeasurementStatus.SUCCESS,
        )
        meas_repo.create_batch(f_id, [invalid_measurement])
    except Exception:
        test_db_session.rollback()

    # Verify no orphan measurements were saved
    meas = meas_repo.get_by_file_id(f_id)
    assert len(meas) == 0
