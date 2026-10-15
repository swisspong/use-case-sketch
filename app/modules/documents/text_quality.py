"""Pure detector ported from backend document_processing/v3/domain/documents/text_quality.py.

Keep the historical backend baseline unchanged. Detects suspicious extraction
characters, not dictionary misspellings. Text and offsets are never rewritten;
percentage thresholds are supplied by the document quality policy.
"""

import re
from dataclasses import dataclass
from typing import Literal
from unicodedata import category, name

SuspicionReason = Literal[
    "latin_adjacent_to_thai",
    "thai_mark_sequence",
    "replacement_character",
    "unexpected_control",
    "private_use_character",
    "split_thai_syllable",
]

_THAI_FOLLOWER = "[\u0e01-\u0e3a\u0e40-\u0e4e]"
# Only syllables that cannot legally end before whitespace, so ordinary
# word-final marks such as ได้/แก่/แพทย์/กรณี followed by a space are not reported:
# 1. consonant + tone mark with no vowel and no leading vowel (ป่ วย, ฝ่ าย);
# 2. leading เ + consonant(s) + ิ/ี/ึ/ื [+ tone], which needs a final (เปิ ด).
_SPLIT_SYLLABLE = re.compile(
    "(?:(?<![\u0e40-\u0e44])[\u0e01-\u0e2e](?P<tone>[\u0e48-\u0e4b])"
    "|\u0e40[\u0e01-\u0e2e]{1,2}[\u0e34-\u0e37](?P<vowel_tone>[\u0e48-\u0e4b])?)"
    f"(?P<gap>[ \t]+)(?={_THAI_FOLLOWER})"
)


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

    The groups are isolated Latin adjacent to Thai, invalid Thai mark
    sequences, whitespace splitting a Thai syllable, and unusual characters (U+FFFD, unexpected controls, private use).
    Normal newlines/tabs are not unexpected controls. English words/codes such as
    COVID-19 and B12 must not be reported as isolated Latin substitutions.
    No dictionary, font inspection, model invocation or automatic repair.
    """

    spans: tuple[SuspiciousTextSpan, ...]


def _is_latin_letter(character: str) -> bool:
    return category(character).startswith("L") and "LATIN" in name(character, "")


def detect_text_signals(raw_text: str) -> TextQualitySignals:
    """Pure local heuristic detection, not a complete Thai language validator.

    The caller supplies the unchanged parser text. Offsets always refer to this
    same string, including its whitespace. No I/O, logging or text rewriting.
    Thai rules cover orphan marks, repeated identical marks, multiple tone
    marks on one base and whitespace inserted inside a syllable that cannot end
    there; they do not certify all Thai spelling/mark-order rules.
    """
    spans = []
    for position, character in enumerate(raw_text):
        if not _is_latin_letter(character):
            continue
        neighbors = (
            raw_text[max(0, position - 1) : position]
            + raw_text[position + 1 : position + 2]
        )
        if any(
            _is_latin_letter(neighbor) or neighbor.isdecimal() for neighbor in neighbors
        ):
            continue
        if any(
            "\u0e00" <= neighbor <= "\u0e7f" and category(neighbor)[0] in "LM"
            for neighbor in neighbors
        ):
            spans.append(
                SuspiciousTextSpan(position, position + 1, "latin_adjacent_to_thai")
            )
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
                spans.append(
                    SuspiciousTextSpan(position, position + 1, "thai_mark_sequence")
                )
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
                    spans.append(
                        SuspiciousTextSpan(suspect, suspect + 1, "thai_mark_sequence")
                    )
            first_mark.setdefault(character, position)
        else:
            has_base = False
            first_mark = {}
            first_tone = None
    for match in _SPLIT_SYLLABLE.finditer(raw_text):
        # Suspect = final mark before the gap; the gap is whitespace and uncounted.
        spans.append(
            SuspiciousTextSpan(
                match.start("gap") - 1, match.end("gap"), "split_thai_syllable"
            )
        )
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
    return TextQualitySignals(
        tuple(sorted(set(spans), key=lambda span: (span.start, span.end, span.reason)))
    )


@dataclass(frozen=True)
class ProblemCharacters:
    """Union of all signal positions over non-whitespace code points, counted once.

    Shared by extraction (OCR suggestion) and OCR attempts (text acceptance).
    """

    spans: tuple[SuspiciousTextSpan, ...]
    count: int
    non_whitespace_count: int
    percent: float

    def exceeds(self, threshold_percent: float) -> bool:
        """Strictly greater than the threshold; exact integer-safe comparison."""
        return self.count * 100 > threshold_percent * self.non_whitespace_count


def assess_problem_characters(text: str) -> ProblemCharacters:
    spans = detect_text_signals(text).spans
    count = len(
        {
            position
            for span in spans
            for position in range(span.start, span.end)
            if not text[position].isspace()
        }
    )
    characters = sum(not character.isspace() for character in text)
    return ProblemCharacters(
        spans, count, characters, count * 100 / characters if characters else 0.0
    )
