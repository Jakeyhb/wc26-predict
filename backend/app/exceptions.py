from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status


@dataclass(slots=True)
class AppError(Exception):
    message: str
    status_code: int = status.HTTP_400_BAD_REQUEST


class NotFoundError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message=message, status_code=status.HTTP_404_NOT_FOUND)


class AuthorizationError(AppError):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message=message, status_code=status.HTTP_401_UNAUTHORIZED)


def to_http_exception(error: AppError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)

