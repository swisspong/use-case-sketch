"""Document-owned extraction state and OCR-suggestion rules, independent of providers.

This is the new owner of extraction results, not a replacement for an IAM model.
The storage adapter assigns the new document's identity on acknowledged creation.
Extraction never invokes a model: it only suggests pages for a separate,
user-triggered OCR use case. Parser text is always kept unchanged.
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal

from .text_quality import RawPageQuality, assess_problem_characters


@dataclass(frozen=True)
class SourcePage:
    """Technical parser facts; numbers are one-based and in original PDF order."""

    number: int
    text: str = field(repr=False)


@dataclass(frozen=True)
class PageExtraction:
    """Immutable page projection produced by DocumentExtraction.

    problem_character_count is the union of non-whitespace positions found by
    every local signal (U+FFFD, font-substitution Latin, Thai mark/syllable
    errors, controls, private use), each position counted once.
    ocr_suggested is a recommendation only, never an automatic OCR transition.
    """

    number: int
    text: str = field(repr=False)
    ocr_suggested: bool
    ocr_reason: Literal["blank_page", "problem_characters"] | None
    problem_character_count: int
    non_whitespace_character_count: int
    problem_percent: float


@dataclass(frozen=True)
class InvalidDocument:
    reason: Literal["invalid_pages", "invalid_threshold", "invalid_suspicious_threshold"]


def valid_percent(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value <= 100 and isfinite(value)


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
        """Evaluate each page; problem percentage strictly above threshold suggests OCR.

        Empty/whitespace-only pages are also suggested. Counts use Unicode code
        points (not grapheme clusters), excluding whitespace. Invalid input is
        rejected without constructing state.

        Optional suspicious threshold is independently validated in [0, 100]
        and only adds the report-only raw_text_quality projection. None leaves
        it empty (not assessed); OCR suggestion is computed either way.
        """
        if not valid_percent(threshold_percent):
            return InvalidDocument("invalid_threshold")
        if suspicious_threshold_percent is not None and not valid_percent(suspicious_threshold_percent):
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
            problems = assess_problem_characters(page.text)
            if not problems.non_whitespace_count:
                reason = "blank_page"
            elif problems.exceeds(threshold_percent):
                reason = "problem_characters"
            else:
                reason = None
            results.append(PageExtraction(
                page.number, page.text, reason is not None, reason, problems.count,
                problems.non_whitespace_count, problems.percent,
            ))
            if suspicious_threshold_percent is not None:
                raw_text_quality.append(RawPageQuality(
                    page.number, page.text, problems.spans, problems.count,
                    problems.non_whitespace_count, problems.percent,
                    suspicious_threshold_percent, problems.exceeds(suspicious_threshold_percent),
                ))
        document = object.__new__(cls)
        object.__setattr__(document, "pages", tuple(results))
        object.__setattr__(document, "threshold_percent", threshold_percent)
        object.__setattr__(document, "raw_text_quality", tuple(raw_text_quality))
        return document
