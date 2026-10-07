"""Exceptions for file upload and storage operations."""

from fastapi import HTTPException, status


class FileServiceError(HTTPException):
    """Base exception for file service errors."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)


class UnsupportedFileTypeError(FileServiceError):
    """Raised when an uploaded file's extension is not supported."""

    def __init__(self, detail: str = "Unsupported file type. Only .kml and .zip files are accepted.") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class EmptyFileError(FileServiceError):
    """Raised when an uploaded file is empty (0 bytes)."""

    def __init__(self, detail: str = "Uploaded file cannot be empty.") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class FileTooLargeError(FileServiceError):
    """Raised when an uploaded file exceeds the configured size limit."""

    def __init__(self, max_size_mb: int) -> None:
        detail = f"File exceeds maximum allowed size of {max_size_mb} MB."
        super().__init__(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=detail)


class StorageError(FileServiceError):
    """Raised when an internal storage failure occurs."""

    def __init__(self, detail: str = "An error occurred while saving the uploaded file.") -> None:
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
