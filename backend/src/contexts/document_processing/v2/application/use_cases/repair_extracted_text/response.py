"""Semantic outcomes; no automatic text replacement.

Completed outcomes are created with repair_id=None, then presented with the
repository-acknowledged identity. Persisted history keeps the original outcome.
"""

from dataclasses import dataclass, field
from typing import Literal, Union


@dataclass(frozen=True)
class SuggestedTextRepair:
    """Proposed [start, end) code-point edit into the exact parser raw text.

    An edit may expand to surrounding context but must overlap a detected span.
    Edits must not overlap each other; duplicate edits also overlap.
    These are DTOs, not validated domain values.
    Structural validation is not proof that an LLM correction is accurate.
    """

    start: int
    end: int
    replacement: str = field(repr=False)


@dataclass(frozen=True)
class RepairSuggested:
    document_id: str
    page_number: int
    edits: tuple[SuggestedTextRepair, ...]
    preset_name: str
    model: str
    repair_id: str | None = None


@dataclass(frozen=True)
class RepairNoChanges:
    """Model proposes no edits; this is not proof that the source is correct."""

    document_id: str
    page_number: int
    preset_name: str
    model: str
    repair_id: str | None = None


@dataclass(frozen=True)
class RepairUnrepairable:
    """Model explicitly cannot propose a repair; not a provider outage."""

    document_id: str
    page_number: int
    preset_name: str
    model: str
    repair_id: str | None = None


@dataclass(frozen=True)
class RepairRejected:
    code: Literal[
        "invalid_request", "invalid_preset", "page_not_found", "vision_page",
        "not_assessed", "page_not_flagged",
    ]


CompletedTextRepair = Union[RepairSuggested, RepairNoChanges, RepairUnrepairable]
RepairExtractedTextResult = Union[CompletedTextRepair, RepairRejected]
