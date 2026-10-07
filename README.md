# Geospatial File Measurement API

A production-quality backend service built with FastAPI for processing geospatial files (`.kml` and `.zip` Shapefiles) and computing measurements (area, distance) with CRS re-projection.

## Current Project Status

> **Phase 2: File Upload Foundation (Completed & Verified)**
>
> Phase 2 establishes a secure, validated file upload and storage boundary for `.kml` and `.zip` archives.
>
> *Note: Geospatial parsing and measurement (GeoPandas, Shapely, PyProj, KML parsing, Shapefile extraction/inspection, CRS transformation, and measurement calculations) will be implemented incrementally in subsequent phases.*

---

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Data Validation & Settings:** Pydantic v2 & Pydantic Settings
- **Multipart Form Uploads:** python-multipart
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
│   │       ├── files.py            # POST /api/files/ upload endpoint
│   │       └── health.py           # GET /health health check route
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py               # Pydantic Settings (upload dir, size limits)
│   │   └── exceptions.py           # Domain HTTP exceptions
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── files.py                # FileUploadResponse & FileMetadataResponse
│   │   └── health.py               # HealthResponse schema
│   ├── services/
│   │   ├── __init__.py
│   │   └── file_service.py         # File streaming, validation, storage, and cleanup
│   └── models/
│       ├── __init__.py
│       └── file.py                 # FileRecord domain model and FileStatus enum
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Isolated temporary storage test fixtures
│   ├── test_files.py               # Upload tests (validation, sizes, extensions, traversal)
│   └── test_health.py              # Health check and app initialization tests
│
├── .gitignore
├── requirements.txt
├── README.md
└── pyproject.toml
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

Configuration values can be configured via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `UPLOAD_DIR` | `storage/uploads` | Path to store uploaded files |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum allowed file upload size in MB |
| `API_V1_PREFIX` | `/api` | Base API prefix |
| `DEBUG` | `False` | Debug mode |

---

## Running the Server

Start the development server with Uvicorn:

```bash
python -m uvicorn app.main:app --reload
```

The service will be accessible at:
- **API Documentation (Swagger):** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`
- **Health Check:** `http://127.0.0.1:8000/health`

---

## Running Tests

Execute the automated test suite with pytest:

```bash
python -m pytest
```

All upload tests use isolated temporary directories and automatically clean up after execution.

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

### 2. File Upload

```text
POST /api/files/
```

- **Content-Type:** `multipart/form-data`
- **Form Field:** `file`
- **Accepted File Extensions (case-insensitive):** `.kml`, `.zip`
- **Rejected File Extensions:** Raw `.shp`, `.txt`, `.pdf`, `.csv`, `.exe`, etc.
- **Maximum File Size:** Configured via `MAX_UPLOAD_SIZE_MB` (default: 50 MB)

#### Example Request

```bash
curl -X POST \
  -F "file=@boundary.kml" \
  http://127.0.0.1:8000/api/files/
```

#### Example Response (HTTP 201)

```json
{
  "id": "1804aab7-d630-4a9f-929a-2f8b31fc30e8",
  "filename": "boundary.kml",
  "status": "UPLOADED"
}
```

---

## Storage & Security Design

- **Path Traversal Protection:** Input filenames are treated as untrusted and stripped of directory paths (`../../evil.kml` $\to$ `evil.kml`).
- **Cryptographic Storage Names:** Files are stored on disk as `<UUID4>.<ext>` inside the configured upload directory, preventing collisions and arbitrary filesystem overwrites.
- **Chunked Streaming & Size Enforcement:** Files are streamed in 1 MB chunks to prevent unbounded memory usage. If a file exceeds the limit, streaming aborts immediately and the partial file is removed.
- **Empty File Rejection:** 0-byte files are rejected with HTTP 400.
- **Automatic Failure Cleanup:** Any upload that fails validation or encounters a disk error is automatically unlinked from the filesystem.
