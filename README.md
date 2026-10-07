# Geospatial File Measurement API

A production-quality backend service built with FastAPI for processing geospatial files (`.kml` and `.zip` Shapefiles) and computing measurements (area, distance) with CRS re-projection.

## Current Project Status

> **Phase 3: Geospatial Ingestion (Completed & Verified)**
>
> Phase 3 implements the geospatial ingestion and parsing layer for `.kml` and `.zip` Shapefiles using GeoPandas, PyProj, Shapely, Pyogrio, and Fiona. It extracts features, geometry types, GeoJSON geometries, CRS, and non-spatial attributes into a unified internal domain representation. It provides `GET /api/files/{id}/` for querying file status, format, CRS, and feature counts.
>
> *Note: Measurement calculations (polygon area, linestring length) and CRS reprojection for measurements are intentionally NOT implemented in this phase and will be added in subsequent phases.*

---

## Tech Stack

- **Language:** Python 3.11+ (Python 3.12 compatible)
- **Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Data Validation & Settings:** Pydantic v2 & Pydantic Settings
- **Multipart Form Uploads:** python-multipart
- **Geospatial Processing:** GeoPandas, Shapely 2.0+, PyProj, Pyogrio, Fiona
- **Testing:** pytest & httpx

---

## Project Structure

```text
geospatial-measurement-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application factory and instance
│   ├── api/
│   │   ├── __init__.py             # API router aggregating routes
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── files.py            # POST /api/files/ & GET /api/files/{id}/
│   │       └── health.py           # GET /health health check route
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Settings (upload limits, archive extraction limits)
│   │   └── exceptions.py           # Domain HTTP exceptions (400, 404, 413, 500)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── files.py                # FileUploadResponse & FileDetailResponse
│   │   └── health.py               # HealthResponse schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── file_service.py         # File streaming, upload orchestration & metadata
│   │   └── geospatial_service.py   # KML & Shapefile ingestion, ZIP safety, CRS & feature extraction
│   └── models/
│       ├── __init__.py
│       └── file.py                 # FileRecord, ProcessedGeoFile, GeoFeature, GeometryState
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # TestClient & isolated temporary storage fixtures
│   ├── test_files.py               # Upload tests (validation, sizes, extensions, traversal)
│   ├── test_geospatial.py          # Geospatial ingestion tests (KML, Shapefiles, CRS, ZIP safety)
│   └── test_health.py              # Health check and app initialization tests
│
├── .gitignore                      # Ignores storage/ uploads and virtual envs
├── requirements.txt                # Production and dev dependencies
├── README.md                       # Documentation
└── pyproject.toml                  # Project config and pytest settings
```

---

## Local Setup

### 1. Prerequisites

- Python 3.11+ installed

### 2. Environment Setup

Create and activate a virtual environment:

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Configuration

Configuration values can be overridden via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_DIR` | `storage/uploads` | Path to store uploaded files |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload size in MB |
| `MAX_ARCHIVE_EXTRACTED_SIZE_MB` | `150` | Maximum uncompressed archive extraction size in MB |
| `MAX_ARCHIVE_MEMBERS` | `100` | Maximum number of files permitted in a ZIP archive |
| `API_V1_PREFIX` | `/api` | Base API prefix |
| `DEBUG` | `False` | Debug mode |

---

## Running the Server

Start the development server with Uvicorn:

```bash
python -m uvicorn app.main:app --reload
```

The service will be accessible at:
- **API Documentation (Swagger UI):** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`
- **Health Check:** `http://127.0.0.1:8000/health`

---

## Running Tests

Execute the automated test suite with pytest:

```bash
python -m pytest
```

All tests execute in isolated temporary directories and automatically clean up after execution.

---

## API Endpoints

### 1. Health Check

```text
GET /health
```

**Response (HTTP 200):**
```json
{
  "status": "healthy"
}
```

### 2. Upload and Ingest Geospatial File

```text
POST /api/files/
```

- **Content-Type:** `multipart/form-data`
- **Form Field:** `file`
- **Accepted File Extensions:** `.kml`, `.zip` (case-insensitive)
- **Rejected:** Raw `.shp`, `.txt`, `.pdf`, `.csv`, `.exe`, etc.

#### Example Request

```bash
curl -X POST \
  -F "file=@survey.kml" \
  http://127.0.0.1:8000/api/files/
```

#### Example Response (HTTP 201)

```json
{
  "id": "c9370f2f-b8a9-4b91-8c1e-e56b0846cbfd",
  "filename": "survey.kml",
  "status": "COMPLETED"
}
```

### 3. Get File Information

```text
GET /api/files/{id}/
```

#### Example Response (HTTP 200 - Successful Ingestion)

```json
{
  "id": "c9370f2f-b8a9-4b91-8c1e-e56b0846cbfd",
  "filename": "survey.kml",
  "status": "COMPLETED",
  "source_format": "KML",
  "crs": "EPSG:4326",
  "feature_count": 12,
  "processing_error": null,
  "created_at": "2026-10-08T02:00:00Z"
}
```

#### Example Response (HTTP 200 - Failed Ingestion)

```json
{
  "id": "0d2e3a4b-6557-47aa-b71d-7b5b8c74c06b",
  "filename": "corrupt.zip",
  "status": "FAILED",
  "source_format": null,
  "crs": null,
  "feature_count": null,
  "processing_error": "No Shapefile (.shp) found in the ZIP archive.",
  "created_at": "2026-10-08T02:00:00Z"
}
```

---

## Geospatial Ingestion Architecture

### 1. Unified Domain Representation
Both `.kml` and Shapefile `.zip` formats are mapped into the same internal `ProcessedGeoFile` model:
- `source_filename` and `source_format` (`KML` or `Shapefile`).
- `crs`: String identifier (e.g., `EPSG:4326`, `EPSG:32643`) or `null` if the dataset lacks CRS metadata. The service never invents or defaults to EPSG:4326 when missing.
- `feature_count`: Total features extracted.
- `features`: List of `GeoFeature` objects containing:
  - `feature_id`: Deterministic integer index.
  - `geometry_type`: String (e.g., `Point`, `LineString`, `Polygon`, `MultiPolygon`).
  - `geometry`: GeoJSON-compatible mapping (`{"type": "...", "coordinates": [...]}`).
  - `properties`: Sanitized dictionary of attributes with NumPy/Pandas types safely coerced into standard JSON primitives (integers, floats, booleans, ISO datetime strings, `None` for NaNs).
  - `geometry_state`: Explicit state tracking (`VALID`, `EMPTY`, `NULL`, `INVALID`).

### 2. KML Processing Flow
- KML files are read using GeoPandas with explicit pyogrio/Fiona driver registration.
- Handles points, lines, polygons, and attributes without crashing on unprojected coordinates.

### 3. Shapefile ZIP Validation & Security
- **Zip Slip Prevention:** Rejects entries with absolute paths, `..` segments, or paths resolving outside the temporary extraction sandbox.
- **Archive Size & Member Limits:** Enforces configurable extraction limits (`MAX_ARCHIVE_EXTRACTED_SIZE_MB`, `MAX_ARCHIVE_MEMBERS`) to prevent ZIP bomb denial-of-service attacks.
- **Companion File Matching:** Verifies that `.shp`, `.shx`, and `.dbf` share the exact same basename (e.g., `parcels.shp`, `parcels.shx`, `parcels.dbf`).
- **Single Shapefile Policy:** If multiple Shapefiles exist in an archive, parsing deterministically fails with a clear message requesting an archive containing exactly one Shapefile.
- **Automatic Sandbox Cleanup:** All extractions occur inside isolated `tempfile.TemporaryDirectory()` sandboxes that are cleaned up immediately following ingestion.
