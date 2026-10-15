from datetime import UTC, datetime, timedelta

import jwt

from app.shared.config import get_settings


def bearer(user_id: str = "u1", role: str = "member") -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode({"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(minutes=5)},
                       get_settings().jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
