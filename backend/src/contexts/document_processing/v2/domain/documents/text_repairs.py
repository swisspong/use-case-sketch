"""Read-only text-repair values; never change DocumentExtraction's owned state.

Offsets always use Unicode code points into exact parser text. These structural
invariants apply whenever repair values are created, not only one adapter path.
A validated proposal is still an unapproved suggestion, not semantic correctness.
"""

from dataclasses import dataclass, field
from typing import Literal, get_args

from .text_quality import SuspicionReason, SuspiciousTextSpan


@dataclass(frozen=True)
class InvalidRepairSourceText:
    reason: Literal["invalid_text", "invalid_spans"]


@dataclass(frozen=True, init=False)
class RepairSourceText:
    raw_text: str = field(repr=False)
    spans: tuple[SuspiciousTextSpan, ...]

    def __init__(self) -> None:
        raise TypeError("Use RepairSourceText.create")

    @classmethod
    def create(
        cls, *, raw_text: str, spans: tuple[SuspiciousTextSpan, ...],
    ) -> "RepairSourceText | InvalidRepairSourceText":
        if not isinstance(raw_text, str) or not raw_text.strip():
            return InvalidRepairSourceText("invalid_text")
        if not isinstance(spans, tuple) or not spans or any(
            not isinstance(span, SuspiciousTextSpan)
            or type(span.start) is not int or type(span.end) is not int
            or not 0 <= span.start < span.end <= len(raw_text)
            or span.reason not in get_args(SuspicionReason)
            for span in spans
        ):
            return InvalidRepairSourceText("invalid_spans")
        source = object.__new__(cls)
        object.__setattr__(source, "raw_text", raw_text)
        object.__setattr__(source, "spans", spans)
        return source


@dataclass(frozen=True)
class RepairEditCandidate:
    """Unvalidated proposed facts, not a valid domain edit."""

    start: int
    end: int
    replacement: str = field(repr=False)


@dataclass(frozen=True)
class InvalidRepairSuggestions:
    reason: Literal["invalid_edits", "out_of_bounds", "outside_signals", "overlapping_edits"]


@dataclass(frozen=True, init=False)
class PageRepairSuggestions:
    source: RepairSourceText = field(repr=False)
    edits: tuple[RepairEditCandidate, ...]

    def __init__(self) -> None:
        raise TypeError("Use PageRepairSuggestions.create")

    @classmethod
    def create(
        cls, *, source: RepairSourceText, edits: tuple[RepairEditCandidate, ...],
    ) -> "PageRepairSuggestions | InvalidRepairSuggestions":
        """Expanded ranges may touch any signal; proposed edits must not overlap.

        Preserve exact text/spans and edit order. Empty replacement may remove a
        corrupt character; it is different from an empty proposal (no edit records).
        """
        if not isinstance(source, RepairSourceText) or not isinstance(edits, tuple) or not edits or any(
            not isinstance(edit, RepairEditCandidate)
            or type(edit.start) is not int or type(edit.end) is not int
            or not isinstance(edit.replacement, str)
            for edit in edits
        ):
            return InvalidRepairSuggestions("invalid_edits")
        if any(not 0 <= edit.start < edit.end <= len(source.raw_text) for edit in edits):
            return InvalidRepairSuggestions("out_of_bounds")
        if any(not any(edit.start < span.end and span.start < edit.end for span in source.spans)
               for edit in edits):
            return InvalidRepairSuggestions("outside_signals")
        ordered = sorted(edits, key=lambda edit: edit.start)
        if any(left.end > right.start for left, right in zip(ordered, ordered[1:])):
            return InvalidRepairSuggestions("overlapping_edits")
        proposal = object.__new__(cls)
        object.__setattr__(proposal, "source", source)
        object.__setattr__(proposal, "edits", edits)
        return proposal
