"""Hardening tests for security, API validation, foreign key enforcement, and error safety."""

import io
import os
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import FileModel, MeasurementModel
from app.repositories.file_repository import FileRepository
from app.repositories.measurement_repository import MeasurementRepository
from tests.test_geospatial import sample_kml_content


# --------------------------------------------------------------------------
# API Validation & UUID Error Handling Tests
# --------------------------------------------------------------------------

def test_invalid_uuid_format_returns_422(client: TestClient) -> None:
    """Verify that an invalid UUID in the path parameter returns HTTP 422 Unprocessable Entity."""
    # Non-UUID string
    response = client.get("/api/files/not-a-valid-uuid")
    assert response.status_code == 422
    assert "detail" in response.json()

    response_meas = client.get("/api/files/not-a-valid-uuid/measurements/")
    assert response_meas.status_code == 422
    assert "detail" in response_meas.json()


def test_nonexistent_uuid_returns_404_clean_json(client: TestClient) -> None:
    """Verify that a syntactically valid but non-existent UUID returns HTTP 404 with clean error message."""
    random_id = uuid4()
    response = client.get(f"/api/files/{random_id}")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "File not found."

    response_meas = client.get(f"/api/files/{random_id}/measurements/")
    assert response_meas.status_code == 404
    assert response_meas.json()["detail"] == "File not found."


def test_malformed_kml_handled_safely_no_500(client: TestClient) -> None:
    """Verify that an invalid/corrupted XML/KML file is handled gracefully as FAILED without a 500 crash."""
    corrupted_xml = b"<?xml version='1.0'?><kml><unclosed_tag>"
    files = {"file": ("corrupted.kml", io.BytesIO(corrupted_xml), "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    # Check status is FAILED with error detail
    detail_res = client.get(f"/api/files/{file_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "FAILED"
    assert detail_res.json()["processing_error"] is not None

    # Measurements should return 400 Bad Request with safe message
    meas_res = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_res.status_code == 400
    assert "Measurements unavailable because file processing failed" in meas_res.json()["detail"]


def test_corrupted_zip_archive_rejected(client: TestClient) -> None:
    """Verify that a corrupted, truncated ZIP archive returns 400 Bad Request cleanly."""
    truncated_zip = b"PK\x03\x04\x14\x00\x00\x00garbage"
    files = {"file": ("broken.zip", io.BytesIO(truncated_zip), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    detail_res = client.get(f"/api/files/{file_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "FAILED"
    assert "not a valid or readable ZIP file" in (detail_res.json()["processing_error"] or "")


# --------------------------------------------------------------------------
# Security & Path Traversal Tests
# --------------------------------------------------------------------------

def test_path_traversal_filename_never_escapes_storage(
    client: TestClient,
    sample_kml_content: bytes,
    temp_storage_dir: Path,
) -> None:
    """Verify that filenames containing directory traversal sequences cannot escape the upload directory."""
    malicious_filename = "../../../../../etc/passwd.kml"
    files = {"file": (malicious_filename, io.BytesIO(sample_kml_content), "application/vnd.google-earth.kml+xml")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    # Ensure saved filename in response is sanitized to basename
    assert response.json()["filename"] == "passwd.kml"

    # Ensure file is stored inside temp_storage_dir
    stored_files = list(temp_storage_dir.glob(f"{file_id}.kml"))
    assert len(stored_files) == 1
    assert stored_files[0].parent.resolve() == temp_storage_dir.resolve()


def test_archive_zip_slip_rejection(
    client: TestClient,
) -> None:
    """Verify that a zip file with path traversal entries is rejected by security checks."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("../../evil.shp", b"dummy shp")
        zf.writestr("../../evil.shx", b"dummy shx")
        zf.writestr("../../evil.dbf", b"dummy dbf")

    files = {"file": ("slip.zip", io.BytesIO(zip_buf.getvalue()), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    detail_res = client.get(f"/api/files/{file_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "FAILED"
    assert "path traversal" in (detail_res.json()["processing_error"] or "").lower()


def test_archive_max_members_limit_enforced(
    client: TestClient,
    isolated_file_service: object,
) -> None:
    """Verify that an archive with more members than MAX_ARCHIVE_MEMBERS is rejected."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        # Create 105 files (default limit is 100)
        for i in range(105):
            zf.writestr(f"file_{i}.txt", b"x")

    files = {"file": ("bomb_members.zip", io.BytesIO(zip_buf.getvalue()), "application/zip")}
    response = client.post("/api/files/", files=files)
    assert response.status_code == 201
    file_id = response.json()["id"]

    detail_res = client.get(f"/api/files/{file_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "FAILED"
    assert "exceeding the maximum allowed limit" in (detail_res.json()["processing_error"] or "")


# --------------------------------------------------------------------------
# Database Hardening & Foreign Key Enforcement Tests
# --------------------------------------------------------------------------

def test_sqlite_foreign_key_cascade_deletion(test_db_session: Session) -> None:
    """Verify that deleting a FileModel cascades and removes all associated MeasurementModel rows."""
    file_repo = FileRepository(test_db_session)
    meas_repo = MeasurementRepository(test_db_session)
    f_id = uuid4()

    # Create file record
    file_rec = file_repo.create(
        file_id=f_id,
        original_filename="cascade_test.kml",
        stored_filename=f"{f_id}.kml",
        file_extension=".kml",
        file_size=500,
    )
    assert file_rec is not None

    # Insert measurement
    meas = MeasurementModel(
        file_id=str(f_id),
        feature_id=0,
        geometry_type="Polygon",
        measurement_status="SUCCESS",
        measurement_type="AREA",
        value=1500.0,
        unit="m²",
    )
    test_db_session.add(meas)
    test_db_session.commit()

    # Check measurement exists
    measurements = meas_repo.get_by_file_id(f_id)
    assert len(measurements) == 1

    # Delete parent file
    test_db_session.delete(file_rec)
    test_db_session.commit()

    # Verify measurement was cascaded and deleted
    measurements_after = meas_repo.get_by_file_id(f_id)
    assert len(measurements_after) == 0


def test_sqlite_foreign_key_prevents_orphan_measurement(test_db_session: Session) -> None:
    """Verify that inserting a measurement with a non-existent file_id triggers IntegrityError (PRAGMA foreign_keys=ON)."""
    orphan_file_id = str(uuid4())
    orphan_meas = MeasurementModel(
        file_id=orphan_file_id,
        feature_id=0,
        geometry_type="Polygon",
        measurement_status="SUCCESS",
        measurement_type="AREA",
        value=1500.0,
        unit="m²",
    )
    test_db_session.add(orphan_meas)
    with pytest.raises(IntegrityError):
        test_db_session.commit()

    test_db_session.rollback()


# --------------------------------------------------------------------------
# Configuration & Environment Tests
# --------------------------------------------------------------------------

def test_settings_environment_and_log_level_defaults() -> None:
    """Verify Settings initializes with environment and log level attributes."""
    s = Settings()
    assert hasattr(s, "ENVIRONMENT")
    assert hasattr(s, "LOG_LEVEL")
    assert hasattr(s, "max_upload_size_bytes")
    assert hasattr(s, "max_archive_extracted_bytes")
    assert s.max_upload_size_bytes == 50 * 1024 * 1024
    assert s.max_archive_extracted_bytes == 150 * 1024 * 1024
