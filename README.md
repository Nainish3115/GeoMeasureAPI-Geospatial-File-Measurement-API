# Geospatial File Measurement API

A production-quality backend service built with FastAPI for processing geospatial files (`.kml` and `.zip` Shapefiles) and computing measurements (area, distance) with CRS re-projection.

## Current Project Status

> **Phase 4: CRS-Aware Measurement Engine (Completed & Verified)**
>
> Phase 4 implements the complete measurement engine. It calculates Polygon/MultiPolygon areas (in m²) and LineString/MultiLineString lengths (in m). Crucially, **geographic coordinates (degrees, e.g. EPSG:4326) are never directly measured**; they are automatically reprojected to an optimal projected metric CRS (such as UTM zones computed from dataset bounds). Points are flagged as `NOT_APPLICABLE`, missing CRS as `UNAVAILABLE`, and measurements are exposed via `GET /api/files/{id}/measurements/`.

---

## Tech Stack

- **Language:** Python 3.11+ (Python 3.12 compatible)
- **Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Data Validation & Settings:** Pydantic v2 & Pydantic Settings
- **Multipart Form Uploads:** python-multipart
- **Geospatial Processing & Measurements:** GeoPandas, Shapely 2.0+, PyProj, Pyogrio, Fiona
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
│   │       ├── files.py            # POST /api/files/, GET /api/files/{id}/, GET /api/files/{id}/measurements/
│   │       └── health.py           # GET /health health check route
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Settings (upload limits, archive limits)
│   │   └── exceptions.py           # Domain HTTP exceptions (400, 404, 413, 500)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── files.py                # Upload, Detail, and Measurement response schemas
│   │   └── health.py               # HealthResponse schema
│   ├── services/
│   │   ├── __init__.py
│   │   ├── crs_service.py          # CRS analysis, UTM zone selection, and vector reprojection
│   │   ├── file_service.py         # File streaming, upload orchestration & metadata
│   │   ├── geospatial_service.py   # KML & Shapefile ingestion, ZIP safety, CRS & feature extraction
│   │   └── measurement_service.py  # CRS-aware Polygon area and LineString length engine
│   └── models/
│       ├── __init__.py
│       └── file.py                 # Domain models (FileRecord, GeoFeature, FeatureMeasurement, FileMeasurementSet)
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Isolated temporary storage test fixtures
│   ├── test_e2e_measurements.py    # End-to-end API tests for measurement endpoints
│   ├── test_files.py               # Upload tests (validation, sizes, extensions, traversal)
│   ├── test_geospatial.py          # Ingestion tests (KML, Shapefile, CRS, ZIP safety)
│   ├── test_health.py              # Health check and app initialization tests
│   └── test_measurements.py        # Numerical precision, units, and edge-case measurement tests
│
├── .gitignore                      # Ignores storage/ uploads and virtual envs
├── requirements.txt                # Production and dev dependencies
├── README.md                       # Comprehensive documentation
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

Interactive documentation:
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

---

## Running Tests

Run the full pytest suite (33 tests covering foundation, security, ingestion, CRS reprojection, and numerical precision):

```bash
python -m pytest
```

---

## API Endpoints

### 1. Health Check

```text
GET /health
```

### 2. Upload and Ingest Geospatial File

```text
POST /api/files/
```
Accepts `.kml` or `.zip` (Shapefile archive).

### 3. Get File Details

```text
GET /api/files/{id}/
```
Returns file metadata, format, CRS, and feature count.

### 4. Calculate Geospatial Measurements

```text
GET /api/files/{id}/measurements/
```

#### Example Response (HTTP 200)

```json
{
  "file_id": "47e874ad-83b1-40f8-adc3-172684b9aa0c",
  "source_crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "results": [
    {
      "feature_id": 0,
      "geometry_type": "Point",
      "measurement_status": "NOT_APPLICABLE",
      "measurement_type": null,
      "value": null,
      "unit": null,
      "source_crs": "EPSG:4326",
      "measurement_crs": "EPSG:32643",
      "reason": "Point geometries do not require measurement."
    },
    {
      "feature_id": 1,
      "geometry_type": "LineString",
      "measurement_status": "SUCCESS",
      "measurement_type": "LENGTH",
      "value": 542.8028,
      "unit": "m",
      "source_crs": "EPSG:4326",
      "measurement_crs": "EPSG:32643",
      "reason": null
    },
    {
      "feature_id": 2,
      "geometry_type": "Polygon",
      "measurement_status": "SUCCESS",
      "measurement_type": "AREA",
      "value": 300422.799789,
      "unit": "m²",
      "source_crs": "EPSG:4326",
      "measurement_crs": "EPSG:32643",
      "reason": null
    }
  ]
}
```

---

## Measurement & CRS Strategy

### 1. Invariant: No Degree-Based Calculations
Geographic coordinate systems like `EPSG:4326` express coordinates in angular degrees ($^\circ$). Calculating `.area` or `.length` directly on geographic coordinates yields meaningless degree$^2$ or degree values that vary drastically depending on latitude. The measurement engine strictly enforces that all measurements must occur in a projected metric coordinate system.

### 2. Detection of Geographic CRS
`pyproj.CRS.is_geographic` is used to detect geographic coordinate reference systems.

### 3. Automated Projected CRS Selection
- **Localized Datasets:** When geographic data is encountered, the dataset's collective bounding box is computed to find the geographic centroid $(\text{lon}_{\text{cent}}, \text{lat}_{\text{cent}})$.
- **UTM Calculation:**
  $$\text{UTM Zone} = \lfloor(\text{lon}_{\text{cent}} + 180) / 6\rfloor + 1$$
  - Northern Hemisphere ($\text{lat}_{\text{cent}} \ge 0$): $\text{EPSG} = 32600 + \text{zone}$
  - Southern Hemisphere ($\text{lat}_{\text{cent}} < 0$): $\text{EPSG} = 32700 + \text{zone}$
- **Why Not EPSG:3857 (Web Mercator)?** Web Mercator introduces severe area distortion increasing with latitude (up to hundreds of percent error away from the equator). UTM projections provide conformal, metric representations with distortion typically $< 0.1\%$ within the zone.

### 4. Pre-Projected Datasets
If the input dataset is already projected (e.g., `EPSG:32643`), the source CRS is preserved directly. If linear units are non-metric (e.g. US survey feet), linear and areal conversion factors are applied to guarantee SI metric outputs.

### 5. Missing CRS Handling
If a dataset has `crs = None` (e.g., a Shapefile lacking a `.prj` file), metric measurement cannot be safely performed without guessing. The engine sets `measurement_status = "UNAVAILABLE"` with `reason = "Source CRS is missing; metric measurement cannot be performed safely."` and never invents or assumes EPSG:4326.

### 6. Supported Geometry Types & Units
- **Polygon:** Area in square metres (`m²`)
- **MultiPolygon:** Total combined area in square metres (`m²`)
- **LineString:** Length in metres (`m`)
- **MultiLineString:** Total combined length in metres (`m`)
- **Point / MultiPoint:** `NOT_APPLICABLE` (`value = null`, `unit = null`)
- **Empty / Null / Invalid Geometries:** `UNAVAILABLE` with an explanatory reason without failing the entire file
