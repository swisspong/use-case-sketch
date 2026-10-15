import io
from datetime import UTC, datetime, timedelta

import jwt
from PIL import Image, ImageDraw

from app.shared.config import get_settings


def bearer(user_id: str = "u1", role: str = "member") -> dict[str, str]:
    now = datetime.now(UTC)
    token = jwt.encode({"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(minutes=5)},
                       get_settings().jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


# Synthetic scanned page for edit-mark detection (no real documents in the repo).
W, H = 1000, 1400


def words(draw, x, y, count):
    """Glyph-like ink: blocks 14 px wide, 20 px tall, 4 px apart; returns the right edge."""
    for i in range(count):
        draw.rectangle([x + i * 18, y, x + i * 18 + 13, y + 19], fill=0)
    return x + count * 18 - 4


def page(paint) -> bytes:
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 52, 1350], fill=0)  # table borders: page-long verticals
    draw.rectangle([948, 50, 950, 1350], fill=0)
    paint(draw)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
