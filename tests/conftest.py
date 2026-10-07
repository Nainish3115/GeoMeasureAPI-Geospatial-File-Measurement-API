"""Pytest configuration and shared fixtures with isolated SQLite database."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.database import get_db, reset_engine, set_engine_and_sessionmaker
from app.main import app
from app.services.file_service import FileService, file_service


@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide an isolated temporary directory for file uploads during tests."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    yield upload_dir


@pytest.fixture
def test_db_session(tmp_path: Path) -> Generator[Session, None, None]:
    """Provide an isolated, file-based SQLite database for each test run."""
    db_file = tmp_path / "test_geomeasure.db"
    db_url = f"sqlite:///{db_file.as_posix()}"

    test_engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)

    # Set globally active test engine and sessionmaker
    set_engine_and_sessionmaker(test_engine)

    TestSessionLocal = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    session = TestSessionLocal()

    # Override get_db dependency in FastAPI app
    def override_get_db() -> Generator[Session, None, None]:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield session

    session.close()
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)
    reset_engine()


@pytest.fixture
def isolated_file_service(
    temp_storage_dir: Path,
    test_db_session: Session,
) -> Generator[FileService, None, None]:
    """Configure file_service with isolated temp storage and database settings."""
    original_settings = file_service.settings

    db_path = temp_storage_dir.parent / "test_geomeasure.db"
    test_settings = Settings(
        UPLOAD_DIR=temp_storage_dir,
        DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
        MAX_UPLOAD_SIZE_MB=50,
    )

    file_service.settings = test_settings

    yield file_service

    file_service.settings = original_settings


@pytest.fixture
def client(
    isolated_file_service: FileService,
    test_db_session: Session,
) -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated storage and database session."""
    with TestClient(app) as test_client:
        yield test_client
