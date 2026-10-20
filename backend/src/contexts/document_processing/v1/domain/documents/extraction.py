"""Document-owned extraction state and quality rules, independent of providers.

This is the new owner of extraction results, not a replacement for an IAM model.
The storage adapter assigns the new document's identity on acknowledged creation;
no editing/reprocessing or overlapping document write model is introduced here.
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal


@dataclass(frozen=True)
class SourcePage:
    """Technical parser facts; numbers are one-based and in original PDF order."""

    number: int
    text: str = field(repr=False)


@dataclass(frozen=True)
class PageExtraction:
    """Immutable state projection produced by DocumentExtraction."""

    number: int
    text: str | None = field(repr=False)
    status: Literal["extracted", "pending_fallback", "failed"]
    method: Literal["pdf_text", "vision"]
    failure_code: Literal["unreadable", "fallback_unavailable"] | None = None
    preset_name: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class InvalidDocument:
    reason: Literal["invalid_pages", "invalid_threshold"]


@dataclass(frozen=True)
class InvalidFallback:
    reason: Literal["invalid_transition", "invalid_provenance", "invalid_text", "invalid_failure"]


@dataclass(frozen=True, init=False)
class DocumentExtraction:
    pages: tuple[PageExtraction, ...]
    threshold_percent: float

    def __init__(self) -> None:
        raise TypeError("Use DocumentExtraction.from_pdf")

    @classmethod
    def from_pdf(
        cls, pages: tuple[SourcePage, ...], *, threshold_percent: float,
    ) -> "DocumentExtraction | InvalidDocument":
        """Evaluate each page; strictly exceeding the threshold requires fallback.

        Empty/whitespace-only pages also require fallback. Domain results own
        decisions, adapters only obtain facts. This factory will reject invalid
        input without constructing invalid state. Fallback text must pass this
        same threshold; failed pages discard parser text and never fall back again.
        Quality counts Unicode code points (not grapheme clusters), excluding
        whitespace; only U+FFFD is counted as unreadable by this agreed heuristic.
        """
        if (
            type(threshold_percent) not in (int, float)
            or not 0 <= threshold_percent <= 100
            or not isfinite(threshold_percent)
        ):
            return InvalidDocument("invalid_threshold")
        if not isinstance(pages, tuple) or not pages or any(
            not isinstance(page, SourcePage)
            or type(page.number) is not int or page.number != position
            or not isinstance(page.text, str)
            for position, page in enumerate(pages, start=1)
        ):
            return InvalidDocument("invalid_pages")
        results = []
        for page in pages:
            needs_fallback = cls._requires_fallback(page.text, threshold_percent)
            results.append(PageExtraction(
                page.number, page.text,
                "pending_fallback" if needs_fallback else "extracted", "pdf_text",
            ))
        document = object.__new__(cls)
        object.__setattr__(document, "pages", tuple(results))
        object.__setattr__(document, "threshold_percent", threshold_percent)
        return document

    def complete_fallback(
        self, *, page_number: int, text: str, preset_name: str, model: str,
    ) -> "DocumentExtraction | InvalidFallback":
        """Resolve one pending page, preserving its provenance and all other pages."""
        if type(page_number) is not int or not any(
            page.number == page_number and page.status == "pending_fallback"
            for page in self.pages
        ):
            return InvalidFallback("invalid_transition")
        if not all(isinstance(value, str) and value.strip() for value in (preset_name, model)):
            return InvalidFallback("invalid_provenance")
        if not isinstance(text, str):
            return InvalidFallback("invalid_text")
        if self._requires_fallback(text, self.threshold_percent):
            return self._with_page(PageExtraction(
                page_number, None, "failed", "vision", "unreadable", preset_name, model,
            ))
        return self._with_page(PageExtraction(
            page_number, text, "extracted", "vision",
            preset_name=preset_name, model=model,
        ))

    def fail_fallback(
        self, *, page_number: int,
        code: Literal["unreadable", "fallback_unavailable"],
        preset_name: str, model: str,
    ) -> "DocumentExtraction | InvalidFallback":
        """Resolve a pending page as failed without retaining low-quality text."""
        if type(page_number) is not int or not any(
            page.number == page_number and page.status == "pending_fallback"
            for page in self.pages
        ):
            return InvalidFallback("invalid_transition")
        if not all(isinstance(value, str) and value.strip() for value in (preset_name, model)):
            return InvalidFallback("invalid_provenance")
        if code not in ("unreadable", "fallback_unavailable"):
            return InvalidFallback("invalid_failure")
        return self._with_page(PageExtraction(
            page_number, None, "failed", "vision", code, preset_name, model,
        ))

    @staticmethod
    def _requires_fallback(text: str, threshold_percent: float) -> bool:
        characters = [character for character in text if not character.isspace()]
        return not characters or (
            characters.count("\ufffd") * 100 > threshold_percent * len(characters)
        )

    def _with_page(self, replacement: PageExtraction) -> "DocumentExtraction":
        document = object.__new__(type(self))
        object.__setattr__(document, "pages", tuple(
            replacement if page.number == replacement.number else page
            for page in self.pages
        ))
        object.__setattr__(document, "threshold_percent", self.threshold_percent)
        return document
