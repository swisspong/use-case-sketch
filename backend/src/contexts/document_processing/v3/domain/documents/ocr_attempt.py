"""One user-triggered OCR attempt over pages of an already saved document.

Separate append-only write model: it never changes DocumentExtraction or the
saved extraction.json. It reads only the saved page numbers/suggestions.
Rules owned here: page selection, OCR-text acceptance (same problem-character
rule as extraction) and terminal page transitions.
"""

from dataclasses import dataclass, field
from typing import Literal

from .extraction import valid_percent
from .text_quality import assess_problem_characters


@dataclass(frozen=True)
class SuggestedPage:
    """Saved extraction fact needed for selection; no text is required."""

    number: int
    ocr_suggested: bool


@dataclass(frozen=True)
class OcrPage:
    number: int
    was_suggested: bool  # False = user explicitly requested an unsuggested page
    status: Literal["pending", "extracted", "unreadable", "ocr_unavailable"]
    text: str | None = field(default=None, repr=False)
    problem_character_count: int | None = None
    non_whitespace_character_count: int | None = None
    problem_percent: float | None = None


@dataclass(frozen=True)
class InvalidSavedFacts:
    """Saved extraction facts violate the contract; a system error, not a rejection."""

    reason: Literal["invalid_pages", "invalid_threshold"]


@dataclass(frozen=True)
class InvalidOcrTransition:
    """Only a pending page of this attempt may be recorded, exactly once."""

    reason: Literal["invalid_transition"]


@dataclass(frozen=True)
class InvalidOcrSelection:
    reason: Literal["no_pages_selected", "page_not_found", "duplicate_page", "no_suggested_pages"]


@dataclass(frozen=True, init=False)
class OcrAttempt:
    document_id: str
    preset_name: str
    model: str
    threshold_percent: float
    pages: tuple[OcrPage, ...]

    def __init__(self) -> None:
        raise TypeError("Use OcrAttempt.start")

    @classmethod
    def start(
        cls, *, document_id: str, saved_pages: tuple[SuggestedPage, ...],
        requested: tuple[int, ...] | None, preset_name: str, model: str,
        threshold_percent: float,
    ) -> "OcrAttempt | InvalidOcrSelection | InvalidSavedFacts":
        """None -> all suggested pages; explicit -> exactly those (any saved page)."""
        if not valid_percent(threshold_percent):
            return InvalidSavedFacts("invalid_threshold")
        if not isinstance(saved_pages, tuple) or not saved_pages or any(
            not isinstance(page, SuggestedPage) or type(page.number) is not int
            or page.number != position or type(page.ocr_suggested) is not bool
            for position, page in enumerate(saved_pages, start=1)
        ):
            return InvalidSavedFacts("invalid_pages")
        if requested is None:
            selected = tuple(page for page in saved_pages if page.ocr_suggested)
            if not selected:
                return InvalidOcrSelection("no_suggested_pages")
        else:
            if not requested:
                return InvalidOcrSelection("no_pages_selected")
            numbers = {page.number for page in saved_pages}
            if any(type(number) is not int or number not in numbers for number in requested):
                return InvalidOcrSelection("page_not_found")
            if len(set(requested)) != len(requested):
                return InvalidOcrSelection("duplicate_page")
            selected = tuple(page for page in saved_pages if page.number in requested)
        return cls._build(document_id, preset_name, model, threshold_percent, tuple(
            OcrPage(page.number, page.ocr_suggested, "pending") for page in selected
        ))

    def pending_page_numbers(self) -> tuple[int, ...]:
        return tuple(page.number for page in self.pages if page.status == "pending")

    def record_text(self, *, page_number: int, text: str) -> "OcrAttempt | InvalidOcrTransition":
        """Accept text unless blank or problem % strictly above threshold -> unreadable."""
        if not self._is_pending(page_number):
            return InvalidOcrTransition("invalid_transition")
        problems = assess_problem_characters(text)
        accepted = problems.non_whitespace_count and not problems.exceeds(self.threshold_percent)
        # Rejected OCR text is discarded; its counts remain as diagnostics.
        return self._replace(page_number, status="extracted" if accepted else "unreadable",
                             text=text if accepted else None,
                             problem_character_count=problems.count,
                             non_whitespace_character_count=problems.non_whitespace_count,
                             problem_percent=problems.percent)

    def record_unreadable(self, *, page_number: int) -> "OcrAttempt | InvalidOcrTransition":
        """The model explicitly could not read the page."""
        if not self._is_pending(page_number):
            return InvalidOcrTransition("invalid_transition")
        return self._replace(page_number, status="unreadable")

    def record_unavailable(self, *, page_number: int) -> "OcrAttempt | InvalidOcrTransition":
        """Rendering or provider failed for this page; no text was obtained."""
        if not self._is_pending(page_number):
            return InvalidOcrTransition("invalid_transition")
        return self._replace(page_number, status="ocr_unavailable")

    def _is_pending(self, page_number: int) -> bool:
        return type(page_number) is int and any(
            page.number == page_number and page.status == "pending" for page in self.pages
        )

    @classmethod
    def _build(cls, document_id, preset_name, model, threshold_percent, pages) -> "OcrAttempt":
        attempt = object.__new__(cls)
        for name, value in (
            ("document_id", document_id), ("preset_name", preset_name), ("model", model),
            ("threshold_percent", threshold_percent), ("pages", pages),
        ):
            object.__setattr__(attempt, name, value)
        return attempt

    def _replace(self, page_number: int, **changes) -> "OcrAttempt":
        return self._build(self.document_id, self.preset_name, self.model, self.threshold_percent, tuple(
            OcrPage(page.number, page.was_suggested, **changes) if page.number == page_number else page
            for page in self.pages
        ))
