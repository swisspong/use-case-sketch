"""Semantic output, without provider details, credentials or transport status."""

from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str | None = field(repr=False)
    status: Literal["extracted", "failed"]
    method: Literal["pdf_text", "vision"]
    failure_code: Literal["unreadable", "fallback_unavailable"] | None = None
    preset_name: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class ExtractionSaved:
    document_id: str
    pages: tuple[ExtractedPage, ...]


@dataclass(frozen=True)
class ExtractionRejected:
    code: Literal["invalid_pdf", "encrypted_pdf", "invalid_preset"]


ExtractPdfTextResult = Union[ExtractionSaved, ExtractionRejected]
