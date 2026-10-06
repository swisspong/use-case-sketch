"""Document-owned extraction state and quality rules, independent of providers.

This is the new owner of extraction results, not a replacement for an IAM model.
The storage adapter assigns the new document's identity on acknowledged creation;
no editing/reprocessing or overlapping document write model is introduced here.
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal

from .text_quality import RawPageQuality, detect_text_signals


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
    reason: Literal["invalid_pages", "invalid_threshold", "invalid_suspicious_threshold"]


@dataclass(frozen=True)
class InvalidFallback:
    reason: Literal["invalid_transition", "invalid_provenance", "invalid_text", "invalid_failure"]


@dataclass(frozen=True, init=False)
class DocumentExtraction:
    pages: tuple[PageExtraction, ...]
    threshold_percent: float
    raw_text_quality: tuple[RawPageQuality, ...]

    def __init__(self) -> None:
        raise TypeError("Use DocumentExtraction.from_pdf")

    @classmethod
    def from_pdf(
        cls, pages: tuple[SourcePage, ...], *, threshold_percent: float,
        suspicious_threshold_percent: float | None = None,
    ) -> "DocumentExtraction | InvalidDocument":
        """Evaluate each page; strictly exceeding the threshold requires fallback.

        Empty/whitespace-only pages also require fallback. Domain results own
        decisions, adapters only obtain facts. This factory will reject invalid
        input without constructing invalid state. Fallback text must pass this
        same threshold; failed terminal pages discard text and never fall back again.
        The separate raw-source projection, when assessed, is intentionally retained.
        Quality counts Unicode code points (not grapheme clusters), excluding
        whitespace; only U+FFFD is counted as unreadable by this agreed heuristic.

        Optional suspicious threshold is independently validated in [0, 100].
        Local signals assess raw parser text only; their union of non-whitespace
        positions determines a report-only flag, never fallback or a text change.
        Preserve raw source/reports across every existing terminal transition.
        None leaves raw_text_quality empty (not assessed), preserving the old path.
        """
        if (
            type(threshold_percent) not in (int, float)
            or not 0 <= threshold_percent <= 100
            or not isfinite(threshold_percent)
        ):
            return InvalidDocument("invalid_threshold")
        if suspicious_threshold_percent is not None and (
            type(suspicious_threshold_percent) not in (int, float)
            or not 0 <= suspicious_threshold_percent <= 100
            or not isfinite(suspicious_threshold_percent)
        ):
            return InvalidDocument("invalid_suspicious_threshold")
        if not isinstance(pages, tuple) or not pages or any(
            not isinstance(page, SourcePage)
            or type(page.number) is not int or page.number != position
            or not isinstance(page.text, str)
            for position, page in enumerate(pages, start=1)
        ):
            return InvalidDocument("invalid_pages")
        results = []
        raw_text_quality = []
        for page in pages:
            if suspicious_threshold_percent is not None:
                signals = detect_text_signals(page.text)
                positions = {position for span in signals.spans
                             for position in range(span.start, span.end)
                             if not page.text[position].isspace()}
                character_count = sum(not character.isspace() for character in page.text)
                suspicious_percent = len(positions) * 100 / character_count if character_count else 0.0
                raw_text_quality.append(RawPageQuality(
                    page.number, page.text, signals.spans, len(positions), character_count,
                    suspicious_percent, suspicious_threshold_percent,
                    len(positions) * 100 > suspicious_threshold_percent * character_count,
                ))
            needs_fallback = cls._requires_fallback(page.text, threshold_percent)
            results.append(PageExtraction(
                page.number, page.text,
                "pending_fallback" if needs_fallback else "extracted", "pdf_text",
            ))
        document = object.__new__(cls)
        object.__setattr__(document, "pages", tuple(results))
        object.__setattr__(document, "threshold_percent", threshold_percent)
        object.__setattr__(document, "raw_text_quality", tuple(raw_text_quality))
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
        """Fail terminal page text while retaining any separate raw-source reports."""
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
        object.__setattr__(document, "raw_text_quality", self.raw_text_quality)
        return document
