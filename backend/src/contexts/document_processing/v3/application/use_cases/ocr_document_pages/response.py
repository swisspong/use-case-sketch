"""Semantic outcomes; no provider details, credentials or transport status."""

from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass(frozen=True)
class OcrPageResult:
    number: int
    was_suggested: bool
    status: Literal["extracted", "unreadable", "ocr_unavailable"]
    text: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class OcrAttemptSaved:
    """Attempt saved; NOT a claim that every page was read successfully."""

    document_id: str
    attempt_id: str
    pages: tuple[OcrPageResult, ...]


@dataclass(frozen=True)
class OcrRejected:
    code: Literal[
        "invalid_preset", "document_not_found",
        "no_pages_selected", "page_not_found", "duplicate_page", "no_suggested_pages",
    ]


OcrDocumentPagesResult = Union[OcrAttemptSaved, OcrRejected]
