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
    quality_status: Literal["not_checked"] = "not_checked"
    # null means no assessment; zero would incorrectly claim every page passed.
    ocr_suggested_count: int | None = None


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    total: int


class UploadResult(BaseModel):
    document: DocumentSummary
    duration_ms: int
