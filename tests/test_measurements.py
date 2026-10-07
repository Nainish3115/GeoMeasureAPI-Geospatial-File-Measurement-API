"""Unit and numerical precision tests for the CRS-aware measurement engine."""

import pytest
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.models.file import (
    GeoFeature,
    GeometryState,
    MeasurementStatus,
    MeasurementType,
    ProcessedGeoFile,
)
from app.services.crs_service import crs_service
from app.services.measurement_service import measurement_service
from uuid import uuid4


def test_projected_polygon_exact_area() -> None:
    """Test 1: Projected Polygon in EPSG:32643 (100m x 50m) produces 5000 m²."""
    poly = box(500000, 1000000, 500100, 1000050)
    feat = GeoFeature(
        feature_id=0,
        geometry_type="Polygon",
        geometry={"type": "Polygon", "coordinates": [list(poly.exterior.coords)]},
        crs="EPSG:32643",
    )
    geo_file = ProcessedGeoFile(
        source_filename="test.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    assert len(res.results) == 1
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.SUCCESS
    assert m.measurement_type == MeasurementType.AREA
    assert m.unit == "m²"
    assert m.measurement_crs == "EPSG:32643"
    assert pytest.approx(m.value, rel=1e-5) == 5000.0


def test_projected_linestring_exact_length() -> None:
    """Test 2: Projected LineString in EPSG:32643 (300m, 400m right triangle) produces 500 m."""
    line = LineString([(500000, 1000000), (500300, 1000400)])
    feat = GeoFeature(
        feature_id=0,
        geometry_type="LineString",
        geometry={"type": "LineString", "coordinates": list(line.coords)},
        crs="EPSG:32643",
    )
    geo_file = ProcessedGeoFile(
        source_filename="test.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    assert len(res.results) == 1
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.SUCCESS
    assert m.measurement_type == MeasurementType.LENGTH
    assert m.unit == "m"
    assert m.measurement_crs == "EPSG:32643"
    assert pytest.approx(m.value, rel=1e-5) == 500.0


def test_geographic_polygon_transformed_area() -> None:
    """Test 3: EPSG:4326 Polygon must NOT calculate area in square degrees.

    Must automatically select UTM (e.g. Zone 43N EPSG:32643 for Bengaluru: 77.59, 12.97)
    and yield positive metric area in m².
    """
    poly = box(77.5900, 12.9700, 77.5950, 12.9750)
    # Degrees area would be 0.005 * 0.005 = 0.000025 (degrees²)
    feat = GeoFeature(
        feature_id=0,
        geometry_type="Polygon",
        geometry={"type": "Polygon", "coordinates": [list(poly.exterior.coords)]},
        crs="EPSG:4326",
    )
    geo_file = ProcessedGeoFile(
        source_filename="test.kml",
        source_format="KML",
        crs="EPSG:4326",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    assert len(res.results) == 1
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.SUCCESS
    assert m.measurement_type == MeasurementType.AREA
    assert m.unit == "m²"
    assert m.measurement_crs == "EPSG:32643"
    # ~550m x ~550m box -> around 300,000 m² (definitely not 0.000025!)
    assert m.value > 100000.0
    assert m.value < 500000.0


def test_geographic_linestring_transformed_length() -> None:
    """Test 4: EPSG:4326 LineString transformed to UTM with positive length in metres."""
    line = LineString([(77.5900, 12.9700), (77.5950, 12.9700)])
    # 0.005 degrees of longitude at ~13 deg latitude is ~540 metres
    feat = GeoFeature(
        feature_id=0,
        geometry_type="LineString",
        geometry={"type": "LineString", "coordinates": list(line.coords)},
        crs="EPSG:4326",
    )
    geo_file = ProcessedGeoFile(
        source_filename="test.kml",
        source_format="KML",
        crs="EPSG:4326",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.SUCCESS
    assert m.measurement_type == MeasurementType.LENGTH
    assert m.unit == "m"
    assert m.measurement_crs == "EPSG:32643"
    assert m.value > 500.0
    assert m.value < 600.0


def test_point_and_multipoint_not_applicable() -> None:
    """Test 5: Point and MultiPoint must have status NOT_APPLICABLE and value=null."""
    pt = Point(77.59, 12.97)
    mpt = MultiPoint([(77.59, 12.97), (77.60, 12.98)])

    features = [
        GeoFeature(
            feature_id=0,
            geometry_type="Point",
            geometry={"type": "Point", "coordinates": [77.59, 12.97]},
            crs="EPSG:4326",
        ),
        GeoFeature(
            feature_id=1,
            geometry_type="MultiPoint",
            geometry={"type": "MultiPoint", "coordinates": [[77.59, 12.97], [77.60, 12.98]]},
            crs="EPSG:4326",
        ),
    ]
    geo_file = ProcessedGeoFile(
        source_filename="points.kml",
        source_format="KML",
        crs="EPSG:4326",
        feature_count=2,
        features=features,
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    for m in res.results:
        assert m.measurement_status == MeasurementStatus.NOT_APPLICABLE
        assert m.value is None
        assert m.unit is None
        assert "do not require measurement" in (m.reason or "")


def test_multipolygon_total_area() -> None:
    """Test 6: MultiPolygon area must equal sum of its constituent polygons."""
    p1 = box(500000, 1000000, 500050, 1000050)  # 50 x 50 = 2500 m²
    p2 = box(500100, 1000000, 500200, 1000050)  # 100 x 50 = 5000 m²
    mp = MultiPolygon([p1, p2])

    feat = GeoFeature(
        feature_id=0,
        geometry_type="MultiPolygon",
        geometry={
            "type": "MultiPolygon",
            "coordinates": [[list(p1.exterior.coords)], [list(p2.exterior.coords)]],
        },
        crs="EPSG:32643",
    )
    geo_file = ProcessedGeoFile(
        source_filename="mp.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.SUCCESS
    assert m.measurement_type == MeasurementType.AREA
    assert pytest.approx(m.value, rel=1e-5) == 7500.0


def test_multilinestring_total_length() -> None:
    """Test 7: MultiLineString length must equal sum of constituent lines."""
    l1 = LineString([(500000, 1000000), (500100, 1000000)])  # 100 m
    l2 = LineString([(500000, 1000000), (500000, 1000200)])  # 200 m
    mls = MultiLineString([l1, l2])

    feat = GeoFeature(
        feature_id=0,
        geometry_type="MultiLineString",
        geometry={"type": "MultiLineString", "coordinates": [list(l1.coords), list(l2.coords)]},
        crs="EPSG:32643",
    )
    geo_file = ProcessedGeoFile(
        source_filename="lines.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.SUCCESS
    assert m.measurement_type == MeasurementType.LENGTH
    assert pytest.approx(m.value, rel=1e-5) == 300.0


def test_missing_crs_unavailable_status() -> None:
    """Test 8: If source CRS is missing (None), measurement status must be UNAVAILABLE."""
    poly = box(0, 0, 10, 10)
    feat = GeoFeature(
        feature_id=0,
        geometry_type="Polygon",
        geometry={"type": "Polygon", "coordinates": [list(poly.exterior.coords)]},
        crs=None,
    )
    geo_file = ProcessedGeoFile(
        source_filename="nocrs.shp",
        source_format="Shapefile",
        crs=None,
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    assert res.measurement_crs is None
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.UNAVAILABLE
    assert m.value is None
    assert "Source CRS is missing" in (m.reason or "")


def test_invalid_geometry_graceful_handling() -> None:
    """Test 9: Invalid/self-intersecting geometry returns UNAVAILABLE without crashing."""
    feat = GeoFeature(
        feature_id=0,
        geometry_type="Polygon",
        geometry={"type": "Polygon", "coordinates": [[[0, 0], [10, 10], [0, 10], [10, 0], [0, 0]]]},
        crs="EPSG:32643",
        geometry_state=GeometryState.INVALID,
    )
    geo_file = ProcessedGeoFile(
        source_filename="invalid.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.UNAVAILABLE
    assert "invalid" in (m.reason or "").lower()


def test_empty_and_null_geometry_graceful_handling() -> None:
    """Test 10: Empty and null geometries return UNAVAILABLE without crashing."""
    f_empty = GeoFeature(
        feature_id=0,
        geometry_type="Polygon",
        geometry={"type": "Polygon", "coordinates": []},
        crs="EPSG:32643",
        geometry_state=GeometryState.EMPTY,
    )
    f_null = GeoFeature(
        feature_id=1,
        geometry_type=None,
        geometry=None,
        crs="EPSG:32643",
        geometry_state=GeometryState.NULL,
    )
    geo_file = ProcessedGeoFile(
        source_filename="empty.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=2,
        features=[f_empty, f_null],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    assert res.results[0].measurement_status == MeasurementStatus.UNAVAILABLE
    assert "empty" in (res.results[0].reason or "").lower()
    assert res.results[1].measurement_status == MeasurementStatus.UNAVAILABLE
    assert "null or missing" in (res.results[1].reason or "").lower()


def test_unsupported_geometry_collection() -> None:
    """Test 11: GeometryCollection returns UNAVAILABLE without crashing."""
    feat = GeoFeature(
        feature_id=0,
        geometry_type="GeometryCollection",
        geometry={"type": "GeometryCollection", "geometries": []},
        crs="EPSG:32643",
    )
    geo_file = ProcessedGeoFile(
        source_filename="collection.shp",
        source_format="Shapefile",
        crs="EPSG:32643",
        feature_count=1,
        features=[feat],
    )

    res = measurement_service.measure_dataset(uuid4(), geo_file)
    m = res.results[0]
    assert m.measurement_status == MeasurementStatus.UNAVAILABLE
    assert "not supported" in (m.reason or "")
