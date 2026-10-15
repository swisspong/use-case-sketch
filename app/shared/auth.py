"""Public auth contract used by every module. Token issuing lives in modules/auth."""

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.shared.config import Settings, get_settings
from app.shared.errors import Unauthorized

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: str


async def current_user(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CurrentUser:
    if cred is None:
        raise Unauthorized("missing token")
    try:
        claims = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise Unauthorized("invalid token") from e
    return CurrentUser(id=claims["sub"], role=claims.get("role", "member"))


UserDep = Annotated[CurrentUser, Depends(current_user)]
