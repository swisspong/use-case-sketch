"""Semantic output, without provider details, credentials or transport status."""

from dataclasses import dataclass, field
from typing import Literal, Union

from ....domain.documents.text_quality import RawPageQuality


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str = field(repr=False)
    ocr_suggested: bool
    ocr_reason: Literal["blank_page", "problem_characters"] | None
    problem_character_count: int
    non_whitespace_character_count: int
    problem_percent: float


@dataclass(frozen=True)
class ExtractionSaved:
    document_id: str
    pages: tuple[ExtractedPage, ...]
    # Semantic raw-source projections, not a formatted view.
    raw_text_quality: tuple[RawPageQuality, ...] = ()


@dataclass(frozen=True)
class ExtractionRejected:
    code: Literal["invalid_pdf", "encrypted_pdf"]


ExtractPdfTextResult = Union[ExtractionSaved, ExtractionRejected]
