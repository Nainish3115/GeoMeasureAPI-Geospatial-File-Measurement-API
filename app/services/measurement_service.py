"""CRS-aware measurement engine for Polygon area and LineString length."""

import logging
from typing import Any
from uuid import UUID

import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.models.file import (
    FeatureMeasurement,
    FileMeasurementSet,
    GeometryState,
    MeasurementStatus,
    MeasurementType,
    ProcessedGeoFile,
)
from app.services.crs_service import CRSService, crs_service

logger = logging.getLogger(__name__)

SUPPORTED_AREA_TYPES = {"Polygon", "MultiPolygon"}
SUPPORTED_LENGTH_TYPES = {"LineString", "MultiLineString"}
NO_MEASUREMENT_TYPES = {"Point", "MultiPoint"}


class MeasurementService:
    """Service responsible for calculating area and length with mandatory projected CRS transformations."""

    def __init__(self, crs_svc: CRSService = crs_service) -> None:
        self.crs_service = crs_svc

    def measure_dataset(self, file_id: UUID, geo_data: ProcessedGeoFile) -> FileMeasurementSet:
        """Process all features in a dataset and return calculated measurements."""
        source_crs = geo_data.crs

        # 1. Compute overall bounding box from all valid geometries to select appropriate target CRS
        bounds = self._compute_dataset_bounds(geo_data)

        # 2. Select target projected CRS
        crs_selection = self.crs_service.analyze_and_select_crs(source_crs, bounds)
        target_crs = crs_selection.target_crs

        # 3. Create transformer if reprojection is required
        transformer = None
        if crs_selection.is_source_geographic and target_crs and source_crs:
            try:
                transformer = self.crs_service.get_transformer(source_crs, target_crs)
            except Exception as exc:
                logger.error("Failed to initialize transformer from %s to %s: %s", source_crs, target_crs, exc)

        results: list[FeatureMeasurement] = []
        for feature in geo_data.features:
            measurement = self._measure_feature(
                feature=feature,
                source_crs=source_crs,
                crs_selection=crs_selection,
                transformer=transformer,
            )
            results.append(measurement)

        return FileMeasurementSet(
            file_id=file_id,
            source_crs=source_crs,
            measurement_crs=target_crs,
            results=results,
        )

    def _compute_dataset_bounds(self, geo_data: ProcessedGeoFile) -> tuple[float, float, float, float] | None:
        """Compute the cumulative (minx, miny, maxx, maxy) bounds across all valid features."""
        minx, miny, maxx, maxy = float("inf"), float("inf"), float("-inf"), float("-inf")
        found = False

        for f in geo_data.features:
            if f.geometry and f.geometry_state == GeometryState.VALID:
                try:
                    geom = shape(f.geometry)
                    if not geom.is_empty:
                        b = geom.bounds
                        minx = min(minx, b[0])
                        miny = min(miny, b[1])
                        maxx = max(maxx, b[2])
                        maxy = max(maxy, b[3])
                        found = True
                except Exception:
                    continue

        if not found:
            return None
        return (minx, miny, maxx, maxy)

    def _measure_feature(
        self,
        feature: Any,
        source_crs: str | None,
        crs_selection: Any,
        transformer: Any,
    ) -> FeatureMeasurement:
        """Evaluate a single feature, apply CRS transformation, and compute measurement."""
        f_id = feature.feature_id
        geom_type = feature.geometry_type

        # Handle Points and MultiPoints: Explicitly not measured
        if geom_type in NO_MEASUREMENT_TYPES:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.NOT_APPLICABLE,
                measurement_type=None,
                value=None,
                unit=None,
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
                reason=f"{geom_type} geometries do not require measurement.",
            )

        # Handle Missing or Empty geometries
        if feature.geometry_state == GeometryState.NULL or feature.geometry is None:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.UNAVAILABLE,
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
                reason="Geometry is null or missing.",
            )

        if feature.geometry_state == GeometryState.EMPTY:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.UNAVAILABLE,
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
                reason="Geometry is empty.",
            )

        if feature.geometry_state == GeometryState.INVALID:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.UNAVAILABLE,
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
                reason="Geometry is topologically invalid.",
            )

        # Handle GeometryCollection or other unhandled geometry types
        if geom_type not in SUPPORTED_AREA_TYPES and geom_type not in SUPPORTED_LENGTH_TYPES:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.UNAVAILABLE,
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
                reason=f"Measurement not supported for geometry type '{geom_type}'.",
            )

        # Handle Missing Source CRS: metric calculation cannot be performed safely
        if not source_crs or crs_selection.target_crs is None:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.UNAVAILABLE,
                source_crs=source_crs,
                measurement_crs=None,
                reason="Source CRS is missing; metric measurement cannot be performed safely.",
            )

        # Deserialize geometry
        try:
            geom = shape(feature.geometry)
        except Exception as exc:
            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.UNAVAILABLE,
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
                reason=f"Failed to parse geometry: {exc}",
            )

        # Transform geometry if source was geographic
        meas_geom: BaseGeometry = geom
        if crs_selection.is_source_geographic:
            if not transformer:
                return FeatureMeasurement(
                    feature_id=f_id,
                    geometry_type=geom_type,
                    measurement_status=MeasurementStatus.UNAVAILABLE,
                    source_crs=source_crs,
                    measurement_crs=crs_selection.target_crs,
                    reason="Could not initialize transformation to projected metric CRS.",
                )
            try:
                meas_geom = self.crs_service.transform_geometry(geom, transformer)
            except Exception as exc:
                return FeatureMeasurement(
                    feature_id=f_id,
                    geometry_type=geom_type,
                    measurement_status=MeasurementStatus.UNAVAILABLE,
                    source_crs=source_crs,
                    measurement_crs=crs_selection.target_crs,
                    reason=f"Error transforming geometry to {crs_selection.target_crs}: {exc}",
                )

        # Calculate Area for Polygon / MultiPolygon
        if geom_type in SUPPORTED_AREA_TYPES:
            # INVARIANT: meas_geom is guaranteed to be in a projected metric CRS
            raw_area = float(meas_geom.area)
            # Apply unit conversion factor if source projected CRS had non-metre units
            metric_area = raw_area * (crs_selection.unit_factor ** 2)
            rounded_area = round(metric_area, 6)

            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.SUCCESS,
                measurement_type=MeasurementType.AREA,
                value=rounded_area,
                unit="m²",
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
            )

        # Calculate Length for LineString / MultiLineString
        if geom_type in SUPPORTED_LENGTH_TYPES:
            # INVARIANT: meas_geom is guaranteed to be in a projected metric CRS
            raw_length = float(meas_geom.length)
            metric_length = raw_length * crs_selection.unit_factor
            rounded_length = round(metric_length, 6)

            return FeatureMeasurement(
                feature_id=f_id,
                geometry_type=geom_type,
                measurement_status=MeasurementStatus.SUCCESS,
                measurement_type=MeasurementType.LENGTH,
                value=rounded_length,
                unit="m",
                source_crs=source_crs,
                measurement_crs=crs_selection.target_crs,
            )

        return FeatureMeasurement(
            feature_id=f_id,
            geometry_type=geom_type,
            measurement_status=MeasurementStatus.UNAVAILABLE,
            source_crs=source_crs,
            measurement_crs=crs_selection.target_crs,
            reason=f"Unhandled measurement rule for {geom_type}",
        )


# Global singleton instance
measurement_service = MeasurementService()
