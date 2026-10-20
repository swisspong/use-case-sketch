from dataclasses import asdict

from pydantic import BaseModel

from app.modules.text_quality.models import Thresholds


class ThresholdValues(BaseModel):
    max_thai_percent: int
    max_garbled_thai_percent: int
    min_text_chars: int
    max_image_percent: int


class ThresholdsOut(ThresholdValues):
    defaults: ThresholdValues

    @classmethod
    def of(cls, t: Thresholds, defaults: Thresholds) -> "ThresholdsOut":
        return cls(**asdict(t), defaults=ThresholdValues(**asdict(defaults)))
