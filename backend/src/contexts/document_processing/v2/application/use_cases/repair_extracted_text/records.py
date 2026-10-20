"""Persistence DTOs for immutable repair history, independent of storage technology."""

from dataclasses import dataclass

from .response import CompletedTextRepair


@dataclass(frozen=True)
class SavedRepairRun:
    repair_id: str


@dataclass(frozen=True)
class RepairRun:
    repair_id: str
    created_at: str  # UTC ISO-8601 timestamp assigned by storage.
    result: CompletedTextRepair  # Original validated outcome, before presentation.
