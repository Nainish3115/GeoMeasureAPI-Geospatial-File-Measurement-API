"""Geospatial processing service for parsing KML and Shapefile archives."""

import logging
import math
import shutil
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping

from app.core.config import Settings, settings
from app.core.exceptions import (
    ArchiveSecurityError,
    GeospatialProcessingError,
)
from app.models.file import (
    GeoFeature,
    GeometryState,
    ProcessedGeoFile,
)

logger = logging.getLogger(__name__)

# Ensure Fiona KML driver support is enabled if Fiona backend is queried
try:
    import fiona
    if hasattr(fiona, "drvsupport") and "KML" not in fiona.drvsupport.supported_drivers:
        fiona.drvsupport.supported_drivers["KML"] = "rw"
        fiona.drvsupport.supported_drivers["LIBKML"] = "rw"
except Exception as driver_err:
    logger.debug("Fiona driver registration notice: %s", driver_err)


class GeospatialService:
    """Service responsible for reading, validating, and extracting geospatial features."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings

    def parse_file(self, file_path: Path, extension: str, original_filename: str) -> ProcessedGeoFile:
        """Parse geospatial file and return normalized ProcessedGeoFile representation."""
        ext_lower = extension.lower()
        if ext_lower == ".kml":
            return self._parse_kml(file_path, original_filename)
        elif ext_lower == ".zip":
            return self._parse_shapefile_zip(file_path, original_filename)
        else:
            raise GeospatialProcessingError(f"Unsupported geospatial format: {extension}")

    def _parse_kml(self, file_path: Path, original_filename: str) -> ProcessedGeoFile:
        """Read and normalize a KML file."""
        try:
            # Try pyogrio engine first, then fall back to default/fiona
            try:
                gdf = gpd.read_file(file_path, engine="pyogrio")
            except Exception:
                gdf = gpd.read_file(file_path)
        except Exception as exc:
            logger.warning("Failed to parse KML file %s: %s", original_filename, exc)
            raise GeospatialProcessingError(f"Failed to parse KML file: {str(exc)}") from exc

        return self._normalize_geodataframe(
            gdf=gdf,
            source_filename=original_filename,
            source_format="KML",
        )

    def _parse_shapefile_zip(self, file_path: Path, original_filename: str) -> ProcessedGeoFile:
        """Safely extract and parse a Shapefile from a ZIP archive."""
        with tempfile.TemporaryDirectory(prefix="geomeasure_zip_") as temp_dir_str:
            temp_dir = Path(temp_dir_str).resolve()
            extracted_shp = self._safe_extract_shapefile(file_path, temp_dir)

            try:
                try:
                    gdf = gpd.read_file(extracted_shp, engine="pyogrio")
                except Exception:
                    gdf = gpd.read_file(extracted_shp)
            except Exception as exc:
                logger.warning("Failed to parse Shapefile %s: %s", original_filename, exc)
                raise GeospatialProcessingError(f"Failed to read Shapefile: {str(exc)}") from exc

            return self._normalize_geodataframe(
                gdf=gdf,
                source_filename=original_filename,
                source_format="Shapefile",
            )

    def _safe_extract_shapefile(self, zip_path: Path, target_dir: Path) -> Path:
        """Inspect and safely extract a ZIP archive containing exactly one valid Shapefile.

        Enforces:
        - Path traversal / Zip Slip prevention.
        - Configured max member count and total uncompressed size limit.
        - Strict Shapefile component matching (.shp, .shx, .dbf sharing the same basename).
        - Deterministic single-Shapefile policy.
        """
        if not zipfile.is_zipfile(zip_path):
            raise ArchiveSecurityError("The uploaded archive is not a valid or readable ZIP file.")

        total_extracted_bytes = 0
        max_bytes = self.settings.max_archive_extracted_bytes
        max_members = self.settings.MAX_ARCHIVE_MEMBERS

        with zipfile.ZipFile(zip_path, "r") as archive:
            members = archive.infolist()

            if len(members) > max_members:
                raise ArchiveSecurityError(
                    f"ZIP archive contains {len(members)} entries, exceeding the maximum allowed limit of {max_members}."
                )

            # Pre-scan members for path traversal and cumulative uncompressed size
            for member in members:
                member_path = Path(member.filename)
                # Check for absolute path or path traversal components
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ArchiveSecurityError(f"Potential path traversal detected in archive entry: {member.filename}")

                resolved_dest = (target_dir / member.filename).resolve()
                if not (resolved_dest == target_dir or target_dir in resolved_dest.parents):
                    raise ArchiveSecurityError(f"Path traversal detected in archive entry: {member.filename}")

                total_extracted_bytes += member.file_size
                if total_extracted_bytes > max_bytes:
                    raise ArchiveSecurityError(
                        f"Uncompressed archive size exceeds the maximum limit of {self.settings.MAX_ARCHIVE_EXTRACTED_SIZE_MB} MB."
                    )

            # Extract archive safely
            for member in members:
                archive.extract(member, path=target_dir)

        # Locate all .shp files in the extracted tree
        shp_files = list(target_dir.rglob("*.shp"))
        # Also check uppercase .SHP if on case-sensitive filesystem
        if not shp_files:
            shp_files = [p for p in target_dir.rglob("*") if p.suffix.lower() == ".shp"]

        if not shp_files:
            raise GeospatialProcessingError("No Shapefile (.shp) found in the ZIP archive.")

        # Group components by directory and basename
        valid_shapefiles: list[Path] = []
        for shp_path in shp_files:
            parent = shp_path.parent
            stem = shp_path.stem

            shx_candidates = [f for f in parent.glob("*") if f.stem.lower() == stem.lower() and f.suffix.lower() == ".shx"]
            dbf_candidates = [f for f in parent.glob("*") if f.stem.lower() == stem.lower() and f.suffix.lower() == ".dbf"]

            if shx_candidates and dbf_candidates:
                valid_shapefiles.append(shp_path)

        if not valid_shapefiles:
            raise GeospatialProcessingError(
                "Invalid Shapefile archive: missing required companion files (.shx and .dbf) matching the .shp basename."
            )

        if len(valid_shapefiles) > 1:
            names = [f.name for f in valid_shapefiles]
            raise GeospatialProcessingError(
                f"Multiple Shapefiles found in archive ({', '.join(names)}). The archive must contain exactly one valid Shapefile."
            )

        return valid_shapefiles[0]

    def _normalize_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        source_filename: str,
        source_format: str,
    ) -> ProcessedGeoFile:
        """Extract features, geometries, attributes, and CRS into normalized ProcessedGeoFile."""
        # Extract CRS
        crs_str: str | None = None
        if gdf.crs is not None:
            try:
                crs_str = gdf.crs.to_string()
            except Exception:
                crs_str = str(gdf.crs)

        feature_list: list[GeoFeature] = []
        geom_col_name = gdf.geometry.name if hasattr(gdf, "geometry") and gdf.geometry is not None else "geometry"

        for idx, row in gdf.iterrows():
            geom = row.get(geom_col_name, None)

            # Determine geometry state, type, and GeoJSON mapping
            geometry_state = GeometryState.VALID
            geom_type: str | None = None
            geom_dict: dict[str, Any] | None = None

            if geom is None or pd.isna(geom):
                geometry_state = GeometryState.NULL
            elif hasattr(geom, "is_empty") and geom.is_empty:
                geometry_state = GeometryState.EMPTY
                geom_type = geom.geom_type
            else:
                geom_type = getattr(geom, "geom_type", None)
                if hasattr(geom, "is_valid") and not geom.is_valid:
                    geometry_state = GeometryState.INVALID

                try:
                    geom_dict = mapping(geom)
                except Exception as map_err:
                    logger.debug("Failed to map geometry at index %s: %s", idx, map_err)
                    geom_dict = None
                    geometry_state = GeometryState.INVALID

            # Extract properties (all non-geometry columns)
            properties: dict[str, Any] = {}
            for col_name, value in row.items():
                if col_name == geom_col_name:
                    continue
                properties[str(col_name)] = self._sanitize_property_value(value)

            feature_list.append(
                GeoFeature(
                    feature_id=int(idx) if isinstance(idx, (int, np.integer)) else len(feature_list),
                    geometry_type=geom_type,
                    geometry=geom_dict,
                    crs=crs_str,
                    properties=properties,
                    geometry_state=geometry_state,
                )
            )

        return ProcessedGeoFile(
            source_filename=source_filename,
            source_format=source_format,
            crs=crs_str,
            feature_count=len(feature_list),
            features=feature_list,
        )

    def _sanitize_property_value(self, value: Any) -> Any:
        """Convert NumPy/Pandas and custom types to JSON-serializable Python primitives."""
        if value is None or pd.isna(value):
            return None
        if isinstance(value, (np.integer, int)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            if math.isnan(value) or math.isinf(value):
                return None
            return float(value)
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        if isinstance(value, (pd.Timestamp, np.datetime64)):
            return pd.to_datetime(value).isoformat()
        if isinstance(value, (bytes, bytearray)):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.hex()
        return str(value)


# Global singleton instance
geospatial_service = GeospatialService()
