import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base

NAME_UNIQUE = "uq_llm_config_presets_name_ci"
ONE_DEFAULT = "uq_llm_config_presets_one_default"


class Preset(Base):
    """Global OpenAI-compatible preset. API keys are encrypted and write-only."""

    __tablename__ = "llm_config_presets"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    model_id: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    __table_args__ = (
        Index(NAME_UNIQUE, func.lower(name), unique=True),
        Index(
            ONE_DEFAULT, "is_default", unique=True, postgresql_where=text("is_default")
        ),
    )
