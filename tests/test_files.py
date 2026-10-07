"""Tests for the file upload endpoint (POST /api/files/) and storage layer."""

import io
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.file_service import FileService


def test_upload_kml_success(client: TestClient, isolated_file_service: FileService) -> None:
    """Verify successful upload and processing of a valid .kml file."""
    kml_content = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<kml xmlns="http://www.opengis.net/kml/2.2">'
        b'<Document><Placemark><name>Point A</name><Point><coordinates>10,20,0</coordinates></Point></Placemark></Document>'
        b'</kml>'
    )
    files = {"file": ("boundary.kml", io.BytesIO(kml_content), "application/vnd.google-earth.kml+xml")}

    response = client.post("/api/files/", files=files)

    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    file_uuid = UUID(data["id"])
    assert data["filename"] == "boundary.kml"
    assert data["status"] == "COMPLETED"

    # Verify physical file existence and content in isolated storage
    stored_record = isolated_file_service.get_record(file_uuid)
    assert stored_record is not None
    stored_path = isolated_file_service.upload_dir / stored_record.stored_filename
    assert stored_path.exists()
    assert stored_path.read_bytes() == kml_content
    assert stored_record.file_size == len(kml_content)
    assert stored_record.feature_count == 1
    assert stored_record.source_format == "KML"


def test_upload_case_insensitive_extensions(client: TestClient, isolated_file_service: FileService) -> None:
    """Verify uppercase extensions like .KML are accepted, while .SHP is rejected."""
    kml_content = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<kml xmlns="http://www.opengis.net/kml/2.2">'
        b'<Document><Placemark><name>Test</name><Point><coordinates>0,0,0</coordinates></Point></Placemark></Document>'
        b'</kml>'
    )
    resp_kml = client.post(
        "/api/files/",
        files={"file": ("SAMPLE.KML", io.BytesIO(kml_content), "application/octet-stream")},
    )
    assert resp_kml.status_code == 201
    assert resp_kml.json()["filename"] == "SAMPLE.KML"
    assert resp_kml.json()["status"] == "COMPLETED"

    # .SHP uppercase must be rejected at upload validation
    resp_shp = client.post(
        "/api/files/",
        files={"file": ("ROADS.SHP", io.BytesIO(b"fake shapefile"), "application/octet-stream")},
    )
    assert resp_shp.status_code == 400
    assert "Unsupported file type" in resp_shp.json()["detail"]


def test_upload_unsupported_extensions(client: TestClient) -> None:
    """Verify rejected file extensions: .txt, .pdf, .csv, .shp, .exe, .json."""
    unsupported = [
        ("notes.txt", b"some text"),
        ("document.pdf", b"%PDF-1.4"),
        ("points.csv", b"lat,lon\n10,20"),
        ("parcels.shp", b"binary shp data"),
        ("malicious.exe", b"MZ..."),
        ("geo.json", b'{"type":"Point"}'),
    ]

    for filename, content in unsupported:
        response = client.post(
            "/api/files/",
            files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]


def test_upload_empty_file(client: TestClient, isolated_file_service: FileService) -> None:
    """Verify 0-byte file is rejected and leaves no file in storage."""
    files = {"file": ("empty.kml", io.BytesIO(b""), "application/vnd.google-earth.kml+xml")}

    response = client.post("/api/files/", files=files)

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
    assert list(isolated_file_service.upload_dir.glob("*")) == []


def test_upload_oversized_file(client: TestClient, isolated_file_service: FileService) -> None:
    """Verify upload exceeding MAX_UPLOAD_SIZE_MB is rejected without leftover files."""
    isolated_file_service.settings = Settings(
        UPLOAD_DIR=isolated_file_service.upload_dir,
        MAX_UPLOAD_SIZE_MB=1,
    )

    oversized_data = b"X" * (1024 * 1024 + 512 * 1024)
    files = {"file": ("large.zip", io.BytesIO(oversized_data), "application/zip")}

    response = client.post("/api/files/", files=files)

    assert response.status_code == 413
    assert "maximum allowed size of 1 MB" in response.json()["detail"]
    assert list(isolated_file_service.upload_dir.glob("*")) == []


def test_upload_path_traversal_sanitization(client: TestClient, isolated_file_service: FileService) -> None:
    """Verify path traversal patterns in filename are sanitized and cannot escape upload directory."""
    kml_content = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<kml xmlns="http://www.opengis.net/kml/2.2">'
        b'<Document><Placemark><name>Safe</name><Point><coordinates>0,0,0</coordinates></Point></Placemark></Document>'
        b'</kml>'
    )
    malicious_filenames = [
        "../../evil.kml",
        "..\\..\\evil.kml",
        "/etc/passwd.kml",
        "C:\\Windows\\System32\\calc.kml",
    ]

    for malicious_name in malicious_filenames:
        response = client.post(
            "/api/files/",
            files={"file": (malicious_name, io.BytesIO(kml_content), "application/octet-stream")},
        )
        assert response.status_code == 201
        data = response.json()
        file_uuid = UUID(data["id"])
        record = isolated_file_service.get_record(file_uuid)
        assert record is not None

        # Ensure stored file is strictly inside upload_dir
        stored_path = isolated_file_service.upload_dir / record.stored_filename
        assert stored_path.parent.resolve() == isolated_file_service.upload_dir.resolve()
        assert stored_path.exists()
        assert "/" not in record.original_filename
        assert "\\" not in record.original_filename
