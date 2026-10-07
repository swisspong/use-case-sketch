"""Source/model capabilities and append-only repair history persistence."""

from dataclasses import dataclass
from typing import Protocol, Union

from ....domain.documents.extraction import PageExtraction
from ....domain.documents.text_quality import RawPageQuality, SuspiciousTextSpan
from ...model_presets import VisionPreset
from .records import RepairRun, SavedRepairRun
from .response import CompletedTextRepair, SuggestedTextRepair


@dataclass(frozen=True)
class LoadedRepairPage:
    document_id: str
    page: PageExtraction
    raw_quality: RawPageQuality | None


@dataclass(frozen=True)
class RepairPageNotFound:
    """Document or one-based page is absent; does not disclose which."""


RepairPageLoadResult = Union[LoadedRepairPage, RepairPageNotFound]


class RepairPageSource(Protocol):
    def load_page(self, *, document_id: str, page_number: int) -> RepairPageLoadResult:
        """Read one coherent, terminal extraction snapshot for the exact identity.

        Bind page and optional raw report to the SAME requested document/page.
        Preserve exact parser text and code-point offsets; never substitute final
        vision text. A missing assessment returns None, not an invented clean report.
        The adapter reads/translates facts; Interactor owns repair eligibility.
        No mutation or transaction spanning the remote model call is required:
        suggestions reference this snapshot, not an update to latest document state.
        Caller must already have authorized document access.
        Missing document/page -> adapter -> RepairPageNotFound -> semantic rejection.
        Known storage/read failure -> adapter -> RepairSourceError -> outer handler;
        unexpected errors propagate. No retry, model invocation or presentation.
        Undeclared/misbound facts -> Interactor -> InvalidRepairSourceResult -> handler.
        Adapters must not log sensitive source content.
        """
        ...


@dataclass(frozen=True)
class TextRepairProposal:
    edits: tuple[SuggestedTextRepair, ...]
    # Must contain at least one edit; explicit no-change uses TextRepairNoChanges.


@dataclass(frozen=True)
class TextRepairNoChanges:
    """No edits proposed; not a certificate of correct source text."""


@dataclass(frozen=True)
class TextRepairUnrepairable:
    """Explicit model inability, not timeout/outage or a raw provider message."""


TextRepairResult = Union[TextRepairProposal, TextRepairNoChanges, TextRepairUnrepairable]


class RepairRunRepository(Protocol):
    def save(self, result: CompletedTextRepair) -> SavedRepairRun:
        """Append one validated model outcome under a fresh identity.

        Never modify extraction, overwrite history, store rejected requests or
        acknowledge partially published records. Return only after durable local
        acknowledgement. Known I/O failures -> RepairRunStorageError, no retry;
        after publication an acknowledgement failure can leave a complete record.
        Presentation failure cannot roll back this write or the model invocation.
        The trusted caller has already authorized document access.
        """
        ...

    def get(self, repair_id: str) -> RepairRun | None:
        """Read an exact immutable record; absent identity returns None.

        Corrupt/misbound records and known I/O errors -> RepairRunStorageError.
        Never disclose sensitive record content in diagnostics.
        """
        ...

    def list_by_document(self, document_id: str) -> tuple[RepairRun, ...]:
        """Read published records for this document, ordered by time then identity.

        No cross-record transaction/snapshot or pagination guarantee; new records
        may appear during listing. Ignore unpublished staging directories.
        """
        ...


class TextRepairer(Protocol):
    def propose(
        self, *, raw_text: str, spans: tuple[SuspiciousTextSpan, ...], preset: VisionPreset,
    ) -> TextRepairResult:
        """One model invocation for exact raw page context and ALL original spans.

        Treat document content as untrusted data, not model instructions.
        Return proposed code-point edits, never apply edits or rewrite extraction.
        Interactor/domain must validate the proposal, not trust model assertions.
        No span-by-span invocation, hidden retries, logging source/provider text,
        presentation or model-selected business rules.
        No edits needed -> TextRepairNoChanges; explicit inability to repair ->
        TextRepairUnrepairable. Neither is a system failure. Adapter translates
        explicit model decisions to these typed results; no raw provider messages.
        Known provider/network/resource failure -> adapter -> TextRepairError ->
        outer handler without retry or success presentation. Unexpected errors
        propagate. Undeclared/malformed result -> InvalidTextRepairResult -> handler.
        Use the exact approved preset endpoint/model; never silently substitute.
        Proposal requires nonempty edits; translate explicit no-change to its typed
        result, not an empty proposal. Empty/malformed proposals violate the contract.
        Reported preset/model provenance comes from this trusted invocation, not
        model output. Use preset.api_key from the trusted JSON catalogue for this
        exact invocation, never an environment/global key or another preset's key.
        Missing/blank/non-string config keys are rejected before any port call;
        known provider authentication failures -> TextRepairError -> outer handler.
        Credentials never appear in results, history, errors or diagnostics.
        The local CLI/client now uses this exact per-invocation JSON key; there
        is no separately injected credential in composition or the adapter.
        Concrete adapter tests must demonstrate timeouts, payload bounds and
        credential handling; the port alone does not prove these guarantees.
        Controlled HTTP tests do not prove real provider interoperability.
        """
        ...
