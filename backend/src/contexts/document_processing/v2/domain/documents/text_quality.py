"""Report-only heuristic detection for document extraction.

Owned by document processing's documents domain. These are signal projections,
not proof of misspellings or validated page state. DocumentExtraction remains
responsible for threshold decisions and page transitions.

Threshold comparison is strictly greater than the configured percentage.
Assessment refers only to parser raw text, never fallback text.
Assessment is explicitly enabled by a configured suspicious threshold; no numeric default.
Detection must not change text, normalize offsets, or request fallback.
"""

from dataclasses import dataclass, field
from typing import Literal
from unicodedata import category, name


SuspicionReason = Literal[
    "latin_adjacent_to_thai",
    "thai_mark_sequence",
    "replacement_character",
    "unexpected_control",
    "private_use_character",
]


@dataclass(frozen=True)
class SuspiciousTextSpan:
    """One signal: [start, end) Unicode code-point offsets into exact raw text.

    Only suspect positions belong in the span, not surrounding context. Different
    reasons may overlap; overlapping positions must not inflate the eventual
    suspicious-character count. No document text is duplicated in this projection.
    A finding means suspicious, not necessarily incorrect (e.g. วิตามินC).
    """

    start: int
    end: int
    reason: SuspicionReason


@dataclass(frozen=True)
class TextQualitySignals:
    """Detector facts for one source text; threshold/flag decisions are separate.

    The three groups are isolated Latin adjacent to Thai, invalid Thai mark
    sequences, and unusual characters (U+FFFD, unexpected controls, private use).
    Normal newlines/tabs are not unexpected controls. English words/codes such as
    COVID-19 and B12 must not be reported as isolated Latin substitutions.
    No dictionary, font inspection, model invocation or automatic repair.
    """

    spans: tuple[SuspiciousTextSpan, ...]


@dataclass(frozen=True)
class RawPageQuality:
    """Immutable raw-source projection created by DocumentExtraction.

    Keep raw text for offset interpretation even when terminal page text is replaced
    or discarded by the existing fallback workflow. Counts use non-whitespace code
    points, with the union of suspect positions counted once. A blank source has
    zero suspicious percent; the existing blank-page fallback rule remains separate.
    flagged is a heuristic threshold decision, not a correctness/confidence score.
    """

    number: int
    raw_text: str = field(repr=False)
    spans: tuple[SuspiciousTextSpan, ...]
    suspicious_character_count: int
    non_whitespace_character_count: int
    suspicious_percent: float
    threshold_percent: float
    flagged: bool


def _is_latin_letter(character: str) -> bool:
    return category(character).startswith("L") and "LATIN" in name(character, "")


def detect_text_signals(raw_text: str) -> TextQualitySignals:
    """Pure local heuristic detection, not a complete Thai language validator.

    The caller supplies the unchanged parser text. Offsets always refer to this
    same string, including its whitespace. No I/O, logging or text rewriting.
    Thai rules cover orphan marks, repeated identical marks and multiple tone
    marks on one base; they do not certify all Thai spelling/mark-order rules.
    """
    spans = []
    for position, character in enumerate(raw_text):
        if not _is_latin_letter(character):
            continue
        neighbors = raw_text[max(0, position - 1):position] + raw_text[position + 1:position + 2]
        if any(_is_latin_letter(neighbor) or neighbor.isdecimal() for neighbor in neighbors):
            continue
        if any("\u0e00" <= neighbor <= "\u0e7f" and category(neighbor)[0] in "LM"
               for neighbor in neighbors):
            spans.append(SuspiciousTextSpan(position, position + 1, "latin_adjacent_to_thai"))
    has_base = False
    first_mark: dict[str, int] = {}
    first_tone: int | None = None
    for position, character in enumerate(raw_text):
        if "\u0e01" <= character <= "\u0e2e":
            has_base = True
            first_mark = {}
            first_tone = None
        elif "\u0e00" <= character <= "\u0e7f" and category(character) == "Mn":
            if not has_base:
                spans.append(SuspiciousTextSpan(position, position + 1, "thai_mark_sequence"))
            # Only the first conflicting occurrence is needed: later ones have
            # already been reported. Avoid rescanning an unbounded mark sequence.
            conflicts = []
            if character in first_mark:
                conflicts.append(first_mark[character])
            if "\u0e48" <= character <= "\u0e4b":
                if first_tone is not None:
                    conflicts.append(first_tone)
                else:
                    first_tone = position
            if conflicts:
                for suspect in (*conflicts, position):
                    spans.append(SuspiciousTextSpan(suspect, suspect + 1, "thai_mark_sequence"))
            first_mark.setdefault(character, position)
        else:
            has_base = False
            first_mark = {}
            first_tone = None
    for position, character in enumerate(raw_text):
        reason: SuspicionReason | None = None
        if character == "\ufffd":
            reason = "replacement_character"
        elif category(character) == "Cc" and character not in "\r\n\t":
            reason = "unexpected_control"
        elif category(character) == "Co":
            reason = "private_use_character"
        if reason is not None:
            spans.append(SuspiciousTextSpan(position, position + 1, reason))
    return TextQualitySignals(tuple(sorted(set(spans), key=lambda span: (span.start, span.end, span.reason))))
