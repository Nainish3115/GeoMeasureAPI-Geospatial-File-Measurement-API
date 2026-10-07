"""Tests for geospatial ingestion: KML, Shapefile archives, CRS, features, and ZIP safety."""

import io
import zipfile
from pathlib import Path
from uuid import UUID

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, Polygon

from app.core.config import Settings
from app.models.file import GeometryState
from app.services.file_service import FileService


@pytest.fixture
def sample_kml_content() -> bytes:
    """Provide valid KML with Point, LineString, and Polygon in EPSG:4326."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Survey Point</name>
      <description>Reference marker</description>
      <Point>
        <coordinates>77.5946,12.9716,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Boundary Line</name>
      <description>Road segment</description>
      <LineString>
        <coordinates>77.5946,12.9716,0 77.5950,12.9720,0 77.5960,12.9730,0</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Estate Polygon</name>
      <description>Zone A</description>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.5950,12.9700,0
              77.5950,12.9750,0
              77.5900,12.9750,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>""".encode("utf-8")


def create_polygon_shapefile_zip(
    tmp_path: Path,
    crs: str | None = "EPSG:4326",
    stem_name: str = "cadastre",
    include_files: list[str] | None = None,
    extra_members: dict[str, bytes] | None = None,
) -> bytes:
    """Helper to generate an in-memory Shapefile ZIP archive with Polygons and MultiPolygons."""
    poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    poly2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)])
    poly3 = Polygon([(4, 4), (5, 4), (5, 5), (4, 5), (4, 4)])
    multi_poly = MultiPolygon([poly2, poly3])

    data = {
        "name": ["Parcel 1", "Parcel Cluster"],
        "code": [101, 102],
        "rating": [4.5, 3.8],
        "active": [True, False],
        "geometry": [poly1, multi_poly],
    }

    gdf = gpd.GeoDataFrame(data, crs=crs)

    shp_dir = tmp_path / f"shp_gen_{stem_name}"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / f"{stem_name}.shp"
    gdf.to_file(shp_path)

    # Pack into zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in shp_dir.iterdir():
            if include_files is None or file.name in include_files or file.suffix in include_files:
                zf.write(file, arcname=file.name)
        if extra_members:
            for arcname, content in extra_members.items():
                zf.writestr(arcname, content)

    return zip_buffer.getvalue()


# ---------------------------------------------------------------------------
# KML INGESTION TESTS
# ---------------------------------------------------------------------------


def test_kml_ingestion_features_and_crs(
    client: TestClient,
    isolated_file_service: FileService,
    sample_kml_content: bytes,
) -> None:
    """Verify KML ingestion correctly extracts features, geometry types, attributes, and CRS."""
    files = {"file": ("cadastre.kml", io.BytesIO(sample_kml_content), "application/vnd.google-earth.kml+xml")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "COMPLETED"

    # Query GET /api/files/{id}
    detail_resp = client.get(f"/api/files/{file_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["id"] == file_id
    assert data["filename"] == "cadastre.kml"
    assert data["status"] == "COMPLETED"
    assert data["source_format"] == "KML"
    assert data["feature_count"] == 3
    assert data["crs"] == "EPSG:4326"
    assert data["processing_error"] is None

    # Verify extracted and persisted domain records
    record = isolated_file_service.get_record(UUID(file_id))
    assert record is not None
    assert record.feature_count == 3
    assert record.source_format == "KML"
    assert record.crs == "EPSG:4326"

    # Verify persisted measurements
    meas_set = isolated_file_service.get_measurements(UUID(file_id))
    assert meas_set is not None
    features = meas_set.results
    assert len(features) == 3

    geom_types = {f.geometry_type for f in features}
    assert "Point" in geom_types
    assert "LineString" in geom_types
    assert "Polygon" in geom_types


# ---------------------------------------------------------------------------
# SHAPEFILE ZIP INGESTION TESTS
# ---------------------------------------------------------------------------


def test_shapefile_zip_ingestion_success(
    client: TestClient,
    isolated_file_service: FileService,
    tmp_path: Path,
) -> None:
    """Verify valid Shapefile ZIP ingestion with projected CRS (e.g., EPSG:3857)."""
    zip_bytes = create_polygon_shapefile_zip(tmp_path, crs="EPSG:3857", stem_name="parcels")
    files = {"file": ("parcels.zip", io.BytesIO(zip_bytes), "application/zip")}

    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "COMPLETED"

    detail_resp = client.get(f"/api/files/{file_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "COMPLETED"
    assert detail["source_format"] == "Shapefile"
    assert detail["feature_count"] == 2
    assert detail["crs"] == "EPSG:3857"

    record = isolated_file_service.get_record(UUID(file_id))
    assert record is not None
    assert record.feature_count == 2
    assert record.source_format == "Shapefile"
    assert record.crs == "EPSG:3857"

    meas_set = isolated_file_service.get_measurements(UUID(file_id))
    assert meas_set is not None
    types = [f.geometry_type for f in meas_set.results]
    assert "Polygon" in types
    assert "MultiPolygon" in types


def test_shapefile_zip_missing_crs(
    client: TestClient,
    isolated_file_service: FileService,
    tmp_path: Path,
) -> None:
    """Verify Shapefile without .prj / CRS preserves crs=null without inventing EPSG:4326."""
    # Write valid shapefile then exclude .prj from the archive
    zip_bytes = create_polygon_shapefile_zip(
        tmp_path,
        crs="EPSG:4326",
        stem_name="unprojected",
        include_files=[".shp", ".shx", ".dbf"],  # Omits .prj
    )
    files = {"file": ("unprojected.zip", io.BytesIO(zip_bytes), "application/zip")}

    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    detail_resp = client.get(f"/api/files/{file_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "COMPLETED"
    assert detail_resp.json()["crs"] is None


# ---------------------------------------------------------------------------
# ZIP ARCHIVE SECURITY & VALIDATION TESTS
# ---------------------------------------------------------------------------


def test_zip_archive_no_shapefile(client: TestClient) -> None:
    """Verify ZIP with no .shp file is marked FAILED with clear message."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("notes.txt", "just text")
    zip_bytes = zip_buffer.getvalue()

    files = {"file": ("empty_shp.zip", io.BytesIO(zip_bytes), "application/zip")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    detail_resp = client.get(f"/api/files/{file_id}")
    assert detail_resp.json()["status"] == "FAILED"
    assert "No Shapefile (.shp) found" in detail_resp.json()["processing_error"]


def test_zip_archive_missing_companion_files(client: TestClient, tmp_path: Path) -> None:
    """Verify ZIP with .shp but missing required .shx/.dbf fails validation."""
    zip_bytes = create_polygon_shapefile_zip(tmp_path, stem_name="broken", include_files=[".shp"])
    files = {"file": ("broken.zip", io.BytesIO(zip_bytes), "application/zip")}

    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    detail_resp = client.get(f"/api/files/{file_id}")
    assert "missing required companion files" in detail_resp.json()["processing_error"]


def test_zip_archive_multiple_shapefiles(client: TestClient, tmp_path: Path) -> None:
    """Verify ZIP containing multiple Shapefiles returns a clear deterministic error."""
    zip_bytes1 = create_polygon_shapefile_zip(tmp_path, stem_name="layer1")
    zip_bytes2 = create_polygon_shapefile_zip(tmp_path, stem_name="layer2")

    combined_buffer = io.BytesIO()
    with zipfile.ZipFile(combined_buffer, "w") as out_zip:
        for b in [zip_bytes1, zip_bytes2]:
            with zipfile.ZipFile(io.BytesIO(b), "r") as in_zip:
                for item in in_zip.infolist():
                    out_zip.writestr(item.filename, in_zip.read(item.filename))

    files = {"file": ("multi.zip", io.BytesIO(combined_buffer.getvalue()), "application/zip")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    detail_resp = client.get(f"/api/files/{file_id}")
    assert "Multiple Shapefiles found in archive" in detail_resp.json()["processing_error"]


def test_zip_slip_path_traversal_prevention(client: TestClient) -> None:
    """Verify Zip Slip path traversal member is caught and safely rejected."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../etc/evil.txt", "payload")

    files = {"file": ("malicious.zip", io.BytesIO(zip_buffer.getvalue()), "application/zip")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    detail_resp = client.get(f"/api/files/{file_id}")
    assert "path traversal" in detail_resp.json()["processing_error"].lower()


def test_zip_bomb_uncompressed_limit(client: TestClient, isolated_file_service: FileService) -> None:
    """Verify uncompressed archive exceeding MAX_ARCHIVE_EXTRACTED_SIZE_MB is rejected."""
    isolated_file_service.settings = Settings(
        UPLOAD_DIR=isolated_file_service.upload_dir,
        MAX_ARCHIVE_EXTRACTED_SIZE_MB=1,  # 1 MB extracted limit
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("large.txt", b"0" * (1500 * 1024))

    files = {"file": ("bomb.zip", io.BytesIO(zip_buffer.getvalue()), "application/zip")}
    upload_resp = client.post("/api/files/", files=files)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]
    assert upload_resp.json()["status"] == "FAILED"

    detail_resp = client.get(f"/api/files/{file_id}")
    assert "maximum limit" in detail_resp.json()["processing_error"]


# ---------------------------------------------------------------------------
# API GET /api/files/{id} TESTS
# ---------------------------------------------------------------------------


def test_get_file_not_found(client: TestClient) -> None:
    """Verify GET /api/files/{id} returns 404 for an unknown UUID."""
    unknown_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/api/files/{unknown_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found."
