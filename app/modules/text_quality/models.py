from dataclasses import dataclass

from sqlalchemy import CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.config import Settings
from app.shared.db import Base


@dataclass(frozen=True)
class Thresholds:
    min_thai_percent: int
    max_garbled_thai_percent: int
    min_text_chars: int
    max_image_percent: int

    @classmethod
    def defaults(cls, settings: Settings) -> "Thresholds":
        return cls(
            settings.text_quality_default_min_thai_percent,
            settings.text_quality_default_max_garbled_thai_percent,
            settings.text_quality_default_min_text_chars,
            settings.text_quality_default_max_image_percent,
        )


class TextQualityThresholds(Base):
    __tablename__ = "text_quality_thresholds"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint(
            "min_thai_percent BETWEEN 0 AND 100", name="min_thai_percent_range"
        ),
        CheckConstraint(
            "max_garbled_thai_percent BETWEEN 0 AND 100",
            name="max_garbled_thai_percent_range",
        ),
        CheckConstraint("min_text_chars >= 0", name="min_text_chars_range"),
        CheckConstraint(
            "max_image_percent BETWEEN 0 AND 100", name="max_image_percent_range"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    min_thai_percent: Mapped[int] = mapped_column(Integer)
    max_garbled_thai_percent: Mapped[int] = mapped_column(Integer)
    min_text_chars: Mapped[int] = mapped_column(Integer)
    max_image_percent: Mapped[int] = mapped_column(Integer)
