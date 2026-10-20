"""Application-owned system failures; adapters never expose provider messages."""

from dataclasses import dataclass
from typing import Literal


RepairProposalRejectionReason = Literal[
    "invalid_edits", "out_of_bounds", "outside_signals", "overlapping_edits",
]
RepairProviderResponseFailureReason = Literal[
    "incomplete_completion", "malformed_json", "invalid_schema",
]
RepairProviderFailureReason = Literal[
    "http_error", "timeout", "network_failure", "payload_limit",
    "invalid_credentials", "invalid_endpoint", "resource_failure",
]


PROPOSAL_DIAGNOSTIC_RANGE_LIMIT = 10


@dataclass(frozen=True)
class OutsideSignalsDiagnostic:
    """Count/code-point facts; no source, replacements or trusted configuration.

    The Interactor bounds range samples while preserving original order/counts.
    The CLI validates numeric metadata and bounds samples again before display.
    """

    edit_count: int
    outside_signal_edit_count: int
    signal_count: int
    outside_signal_edit_ranges: tuple[tuple[int, int], ...]
    signal_ranges: tuple[tuple[int, int], ...]


class RepairSourceError(RuntimeError):
    """Known source read/storage failure -> source adapter -> outer handler.

    No LLM invocation, presentation or retry. Missing document/page is instead
    the typed RepairPageNotFound result, not this exception.
    """


class TextRepairError(RuntimeError):
    """Known provider/network/resource failure -> text adapter -> outer handler.

    No recovery, success presentation or automatic retry. Unexpected errors propagate.
    Optional reason/status are safe diagnostic facts, never raw provider messages.
    Legacy exception arguments and propagation identity remain unchanged.
    """

    def __init__(
        self, *args: object, reason: RepairProviderFailureReason | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(*args)
        self.reason = reason
        self.http_status = http_status


class RepairRunStorageError(RuntimeError):
    """History storage/read failure; no success, retry or assumed rollback."""


class InvalidRepairSourceResult(RuntimeError):
    """Malformed/undeclared source facts -> Interactor -> outer handler."""


class InvalidTextRepairResult(RuntimeError):
    """Malformed/undeclared trusted model result, not an ordinary rejection.

    An optional reason preserves a domain rejection or provider response failure
    for opt-in diagnostics. It contains no source, replacement or provider text.
    Existing exception arguments remain compatible; failures still propagate.
    """

    def __init__(
        self, *args: object,
        reason: RepairProposalRejectionReason | RepairProviderResponseFailureReason | None = None,
        proposal_diagnostic: OutsideSignalsDiagnostic | None = None,
    ) -> None:
        super().__init__(*args)
        self.reason = reason
        self.proposal_diagnostic = proposal_diagnostic
