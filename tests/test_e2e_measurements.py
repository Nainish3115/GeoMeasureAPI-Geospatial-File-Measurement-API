"""End-to-end API integration tests for GET /api/files/{id}/measurements/."""

import io
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.models.file import MeasurementStatus, MeasurementType
from tests.test_geospatial import create_polygon_shapefile_zip, sample_kml_content


def test_e2e_kml_measurements(
    client: TestClient,
    sample_kml_content: bytes,
) -> None:
    """End-to-End: Upload KML and verify measurements endpoint.

    Contains:
    - Point -> NOT_APPLICABLE
    - LineString -> LENGTH in m
    - Polygon -> AREA in m²
    """
    files = {"file": ("cadastre.kml", io.BytesIO(sample_kml_content), "application/vnd.google-earth.kml+xml")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    data = meas_resp.json()

    assert data["file_id"] == file_id
    assert data["source_crs"] == "EPSG:4326"
    assert data["measurement_crs"] == "EPSG:32643"
    assert len(data["results"]) == 3

    results_by_type = {r["geometry_type"]: r for r in data["results"]}

    # Point: NOT_APPLICABLE
    pt_res = results_by_type["Point"]
    assert pt_res["measurement_status"] == MeasurementStatus.NOT_APPLICABLE
    assert pt_res["value"] is None
    assert pt_res["unit"] is None

    # LineString: LENGTH
    line_res = results_by_type["LineString"]
    assert line_res["measurement_status"] == MeasurementStatus.SUCCESS
    assert line_res["measurement_type"] == MeasurementType.LENGTH
    assert line_res["unit"] == "m"
    assert line_res["value"] > 0
    assert line_res["measurement_crs"] == "EPSG:32643"

    # Polygon: AREA
    poly_res = results_by_type["Polygon"]
    assert poly_res["measurement_status"] == MeasurementStatus.SUCCESS
    assert poly_res["measurement_type"] == MeasurementType.AREA
    assert poly_res["unit"] == "m²"
    assert poly_res["value"] > 0
    assert poly_res["measurement_crs"] == "EPSG:32643"


def test_e2e_shapefile_measurements(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """End-to-End: Upload Shapefile ZIP and verify measurements endpoint with projected CRS."""
    zip_bytes = create_polygon_shapefile_zip(tmp_path, crs="EPSG:32643", stem_name="parcels")
    files = {"file": ("parcels.zip", io.BytesIO(zip_bytes), "application/zip")}

    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 200
    data = meas_resp.json()

    assert data["file_id"] == file_id
    assert data["source_crs"] == "EPSG:32643"
    assert data["measurement_crs"] == "EPSG:32643"
    assert len(data["results"]) == 2

    for r in data["results"]:
        assert r["measurement_status"] == MeasurementStatus.SUCCESS
        assert r["measurement_type"] == MeasurementType.AREA
        assert r["unit"] == "m²"
        assert r["value"] > 0
        assert r["measurement_crs"] == "EPSG:32643"


def test_e2e_measurements_unknown_file(client: TestClient) -> None:
    """Verify GET /api/files/{id}/measurements/ returns 404 for an unknown file ID."""
    unknown_id = "00000000-0000-0000-0000-000000000000"
    resp = client.get(f"/api/files/{unknown_id}/measurements/")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "File not found."


def test_e2e_measurements_failed_file(client: TestClient) -> None:
    """Verify GET /api/files/{id}/measurements/ returns 400 if ingestion previously failed."""
    # Upload an empty zip archive that triggers ingestion failure
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("test.txt", "not a shapefile")
    
    upload_resp = client.post("/api/files/", files={"file": ("failed.zip", io.BytesIO(buf.getvalue()), "application/zip")})
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    meas_resp = client.get(f"/api/files/{file_id}/measurements/")
    assert meas_resp.status_code == 400
    assert "Measurements unavailable" in meas_resp.json()["detail"]
