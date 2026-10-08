from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the Geospatial File Measurement API."""

    PROJECT_NAME: str = "Geospatial File Measurement API"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api"
    DEBUG: bool = False

    # Application environment
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    # File storage configuration
    UPLOAD_DIR: Path = Path("storage/uploads")
    MAX_UPLOAD_SIZE_MB: int = 50

    # Database configuration
    DATABASE_URL: str = "sqlite:///./storage/geomeasure.db"

    # Archive extraction safety configuration
    MAX_ARCHIVE_EXTRACTED_SIZE_MB: int = 150
    MAX_ARCHIVE_MEMBERS: int = 100


    @property
    def max_upload_size_bytes(self) -> int:
        """Return maximum upload size in bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_archive_extracted_bytes(self) -> int:
        """Return maximum archive extracted size in bytes."""
        return self.MAX_ARCHIVE_EXTRACTED_SIZE_MB * 1024 * 1024


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()

