"""Pytest configuration and shared fixtures."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.services.file_service import FileService, file_service


@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide an isolated temporary directory for file uploads during tests."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    yield upload_dir


@pytest.fixture
def isolated_file_service(temp_storage_dir: Path) -> Generator[FileService, None, None]:
    """Temporarily replace the global file_service with an isolated instance pointing to temp storage."""
    original_settings = file_service.settings
    original_records = file_service._records

    # Create isolated settings
    test_settings = Settings(
        UPLOAD_DIR=temp_storage_dir,
        MAX_UPLOAD_SIZE_MB=50,
    )

    file_service.settings = test_settings
    file_service._records = {}

    yield file_service

    # Restore original settings and records
    file_service.settings = original_settings
    file_service._records = original_records


@pytest.fixture
def client(isolated_file_service: FileService) -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated storage."""
    with TestClient(app) as test_client:
        yield test_client
