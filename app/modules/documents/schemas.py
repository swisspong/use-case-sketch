import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    size_bytes: int
    page_count: int
    uploaded_at: datetime
    quality_status: Literal["not_checked", "checked"] = "not_checked"
    # null means no assessment; zero would incorrectly claim every page passed.
    ocr_suggested_count: int | None = None


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    total: int


class UploadResult(BaseModel):
    document: DocumentSummary
    duration_ms: int


class PageSummary(BaseModel):
    number: int
    ocr_suggested: bool
    has_ocr: bool = False


class DocumentDetail(DocumentSummary):
    pages: list[PageSummary]


class CommonThresholdSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_garbled_thai_percent: int
    min_text_chars: int
    max_image_percent: int


class ThresholdSnapshot(CommonThresholdSnapshot):
    max_thai_percent: int


class LegacyThresholdSnapshot(CommonThresholdSnapshot):
    # Old persisted assessments retain their original minimum-Thai semantics.
    min_thai_percent: int


class Quality(BaseModel):
    thai_percent: float
    garbled_thai_percent: float
    text_chars: int
    image_percent: float
    failed: list[
        Literal[
            "max_thai_percent",
            "min_thai_percent",
            "max_garbled_thai_percent",
            "min_text_chars",
            "max_image_percent",
        ]
    ]
    passed: bool


class ParserResult(BaseModel):
    text: str
    quality: Quality


class OcrOutput(BaseModel):
    preset_name: str
    model_id: str
    created_at: datetime
    text: str
    quality: Quality


class PageResult(BaseModel):
    number: int
    thresholds: ThresholdSnapshot | LegacyThresholdSnapshot
    parser: ParserResult
    ocr: OcrOutput | None = None
