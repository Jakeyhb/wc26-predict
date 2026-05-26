from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.exceptions import AuthorizationError

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def require_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None or credentials.credentials != settings.admin_token:
        raise AuthorizationError()
    return credentials.credentials

