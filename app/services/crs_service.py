"""CRS analysis, selection, and geometry reprojection service."""

import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pyproj
from pyproj import CRS, Transformer
import shapely
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger(__name__)


@dataclass
class CRSSelectionResult:
    """Outcome of CRS analysis and projected CRS determination."""

    source_crs: str | None
    target_crs: str | None
    is_source_projected: bool
    is_source_geographic: bool
    selection_method: str
    unit_name: str | None = None
    unit_factor: float = 1.0


class CRSService:
    """Service responsible for CRS inspection, UTM zone determination, and geometric transformation."""

    def analyze_and_select_crs(
        self,
        source_crs_str: str | None,
        bounds: tuple[float, float, float, float] | None,
    ) -> CRSSelectionResult:
        """Analyze source CRS and select an appropriate projected metric CRS.

        Args:
            source_crs_str: The source dataset's CRS string (e.g. 'EPSG:4326', 'EPSG:32643').
            bounds: Dataset bounding box (minx, miny, maxx, maxy).

        Returns:
            CRSSelectionResult indicating target CRS and selection rationale.
        """
        if not source_crs_str:
            return CRSSelectionResult(
                source_crs=None,
                target_crs=None,
                is_source_projected=False,
                is_source_geographic=False,
                selection_method="SOURCE_CRS_MISSING",
            )

        try:
            crs_obj = CRS.from_user_input(source_crs_str)
        except Exception as exc:
            logger.warning("Failed to parse source CRS '%s': %s", source_crs_str, exc)
            return CRSSelectionResult(
                source_crs=source_crs_str,
                target_crs=None,
                is_source_projected=False,
                is_source_geographic=False,
                selection_method="INVALID_SOURCE_CRS",
            )

        # 1. If already projected
        if crs_obj.is_projected:
            unit_name = "metre"
            unit_factor = 1.0
            if crs_obj.axis_info:
                unit_name = crs_obj.axis_info[0].unit_name or "metre"
                unit_factor = getattr(crs_obj.axis_info[0], "unit_conversion_factor", 1.0) or 1.0

            normalized_name = source_crs_str
            try:
                epsg = crs_obj.to_epsg()
                if epsg:
                    normalized_name = f"EPSG:{epsg}"
            except Exception:
                pass

            return CRSSelectionResult(
                source_crs=normalized_name,
                target_crs=normalized_name,
                is_source_projected=True,
                is_source_geographic=False,
                selection_method="ALREADY_PROJECTED",
                unit_name=unit_name,
                unit_factor=unit_factor,
            )

        # 2. If geographic (e.g. EPSG:4326)
        if crs_obj.is_geographic:
            if not bounds:
                # Default to UTM zone based on 0,0 if bounds are missing or empty
                target_crs_code = "EPSG:32631"
                method = "GEOGRAPHIC_DEFAULT_UTM_ZONE_31N"
            else:
                target_crs_code, method = self._determine_utm_zone_from_bounds(bounds, crs_obj)

            return CRSSelectionResult(
                source_crs="EPSG:4326" if crs_obj.to_epsg() == 4326 else source_crs_str,
                target_crs=target_crs_code,
                is_source_projected=False,
                is_source_geographic=True,
                selection_method=method,
                unit_name="metre",
                unit_factor=1.0,
            )

        # 3. Fallback for other/compound CRS
        return CRSSelectionResult(
            source_crs=source_crs_str,
            target_crs=None,
            is_source_projected=False,
            is_source_geographic=False,
            selection_method="UNSUPPORTED_CRS_TYPE",
        )

    def _determine_utm_zone_from_bounds(
        self,
        bounds: tuple[float, float, float, float],
        source_crs: CRS,
    ) -> tuple[str, str]:
        """Compute dataset centroid in longitude/latitude and select the appropriate UTM zone EPSG code."""
        minx, miny, maxx, maxy = bounds
        cent_x = (minx + maxx) / 2.0
        cent_y = (miny + maxy) / 2.0

        # If source CRS is not standard long/lat (e.g. axis order issues), transform centroid to EPSG:4326
        if source_crs.to_epsg() != 4326:
            try:
                to_wgs84 = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
                cent_x, cent_y = to_wgs84.transform(cent_x, cent_y)
            except Exception as exc:
                logger.debug("Failed to reproject centroid to WGS84: %s", exc)

        # Clamp longitude [-180, 180] and latitude [-80, 84] for standard UTM
        lon = max(-180.0, min(180.0, float(cent_x)))
        lat = max(-80.0, min(84.0, float(cent_y)))

        zone = int((lon + 180.0) // 6.0) + 1
        zone = max(1, min(60, zone))

        if lat >= 0:
            epsg_code = 32600 + zone
            method = f"UTM_ZONE_{zone}N_FROM_DATASET_CENTROID"
        else:
            epsg_code = 32700 + zone
            method = f"UTM_ZONE_{zone}S_FROM_DATASET_CENTROID"

        return f"EPSG:{epsg_code}", method

    def get_transformer(self, source_crs: str, target_crs: str) -> Transformer:
        """Create a PyProj Transformer configured with always_xy=True."""
        return Transformer.from_crs(source_crs, target_crs, always_xy=True)

    def transform_geometry(self, geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:
        """Reproject a Shapely geometry using vectorised coordinate transform."""
        def _coord_transform(coords: np.ndarray) -> np.ndarray:
            x, y = transformer.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geometry, _coord_transform)


# Global singleton instance
crs_service = CRSService()
