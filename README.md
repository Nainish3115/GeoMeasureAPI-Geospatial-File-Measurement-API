# Geospatial File Measurement API

A production-quality backend service built with FastAPI for processing geospatial files (.kml and .zip Shapefiles) and computing measurements (area, distance) with CRS re-projection.

## Current Project Status

> **Phase 1: Project Foundation (Completed)**
>
> In this phase, the core application structure, configuration management, health check endpoint, and automated test suite are established.
>
> *Note: Geospatial processing (GeoPandas, Shapely, PyProj, KML/Shapefile parsing, CRS transformation, and file measurement endpoints) will be implemented incrementally in subsequent phases.*

---

## Tech Stack (Phase 1)

- **Language:** Python 3.11+
- **Framework:** FastAPI
- **ASGI Server:** Uvicorn
- **Data Validation & Settings:** Pydantic v2 & Pydantic Settings
- **Testing:** pytest & httpx

---

## Project Structure

```text
geospatial-measurement-api/
│
├── app/
│   ├── __init__.py
│   ├── main.py                     # Application entrypoint & factory
│   ├── api/
│   │   ├── __init__.py             # API router aggregator
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py           # Health check route
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py               # Application configuration (Pydantic Settings)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── health.py               # Pydantic models for health check
│   ├── services/
│   │   └── __init__.py             # Business logic layer (reserved for future phases)
│   └── models/
│       └── __init__.py             # Domain/persistence models (reserved for future phases)
│
├── tests/
│   ├── __init__.py
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

## Running the Server

Start the development server with Uvicorn:

```bash
uvicorn app.main:app --reload
```

The service will be accessible at:
- **Health check:** `http://127.0.0.1:8000/health`
- **Interactive API Docs (Swagger):** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

---

## Running Tests

Execute the automated test suite with pytest:

```bash
pytest
```

---

## API Endpoints (Phase 1)

| Method | Endpoint | Description | Response Model |
|--------|----------|-------------|----------------|
| `GET`  | `/health`| Service health check | `{"status": "healthy"}` |
