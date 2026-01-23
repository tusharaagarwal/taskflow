from typing import Any, Dict, Optional

from fastapi import HTTPException


class NotFoundException(HTTPException):
    def __init__(self, detail: Any = "Resource not found", headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__(status_code=404, detail=detail, headers=headers)


class ForbiddenException(HTTPException):
    def __init__(self, detail: Any = "Forbidden", headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__(status_code=403, detail=detail, headers=headers)


class ExternalServiceException(HTTPException):
    def __init__(self, detail: Any = "External service error", headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__(status_code=500, detail=detail, headers=headers)


class UnprocessableEntityException(HTTPException):
    def __init__(self, detail: Any = "Unprocessable Entity", headers: Optional[Dict[str, str]] = None) -> None:
        super().__init__(status_code=422, detail=detail, headers=headers)


