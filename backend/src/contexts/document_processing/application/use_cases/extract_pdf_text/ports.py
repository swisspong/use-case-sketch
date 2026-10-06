"""External capabilities; named failures are declared in the sibling errors module."""

from dataclasses import dataclass, field
from typing import Literal, Protocol, Union

from contexts.document_processing.domain.documents.extraction import (
    DocumentExtraction,
    SourcePage,
)

from .configuration import VisionPreset


@dataclass(frozen=True)
class ParsedPdf:
    pages: tuple[SourcePage, ...]


@dataclass(frozen=True)
class PdfRejected:
    code: Literal["invalid_pdf", "encrypted_pdf"]


PdfParseResult = Union[ParsedPdf, PdfRejected]


class PdfTextExtractor(Protocol):
    def extract(self, pdf: bytes) -> PdfParseResult:
        """Read exact uploaded bytes; return every page once in original order.

        Adapter translates malformed PDF -> PdfRejected('invalid_pdf'); unsupported
        password/encryption -> PdfRejected('encrypted_pdf'). Do not apply quality
        rules, silently omit empty pages, OCR, or log document text/content.
        Known library/resource failure -> PdfExtractionError -> outer handler,
        no persistence/presentation/retry. Unexpected errors propagate.
        Malformed/undeclared trusted facts -> Interactor ->
        InvalidPdfExtractionResult -> outer handler without downstream effects.
        pypdf adapter and library-level correctness tests remain deferred.
        """
        ...


@dataclass(frozen=True)
class VisionText:
    text: str = field(repr=False)


@dataclass(frozen=True)
class VisionUnreadable:
    """Model cannot read this page; not a timeout/outage or provider message."""


VisionResult = Union[VisionText, VisionUnreadable]


class FallbackExtractor(Protocol):
    def extract_page(
        self, *, pdf: bytes, page_number: int, preset: VisionPreset,
    ) -> VisionResult:
        """Render only the specified one-based page and use the exact trusted preset.

        Adapter performs rasterization/provider representation translation, not
        quality decisions or selection of another page/model/endpoint. Explicit
        model inability -> VisionUnreadable. Known rendering/provider failure ->
        FallbackExtractionError -> Interactor recovers this page as
        fallback_unavailable, continues other pages, saves partial results and
        presents once. Unexpected errors propagate without saving/presentation.
        No automatic retries or presenting/logging provider text. Use the exact
        configured model; never silently substitute another model or endpoint.
        Stored preset/model describe the attempted invocation even on failure.
        Endpoint allowlisting, bounded rendering/network timeouts, payload limits,
        credentials and actual vision model capability need deferred adapter tests.
        Malformed/undeclared trusted result -> Interactor ->
        InvalidFallbackExtractionResult -> handler, never a failed business page.
        """
        ...


@dataclass(frozen=True)
class SavedDocument:
    document_id: str


class ExtractionStore(Protocol):
    def save(self, document: DocumentExtraction, *, pdf: bytes) -> SavedDocument:
        """Atomically create a new document: exact original PDF + terminal pages.

        Reject pending state; persist text/status/method/provenance unchanged and
        bind the original bytes to the SAME new document identity. Acknowledge only
        when BOTH PDF and all ordered page results are durably committed/available.
        Cross-storage implementations must coordinate staging/cleanup; a database
        transaction alone cannot make object storage atomic. Never acknowledge an
        orphaned PDF or missing page results. Unit mocks do not prove this guarantee.
        Assign and return a nonblank new identity only after successful commit.
        No business defaults/transitions here. Original PDFs/text are sensitive;
        deferred storage must enforce access control and never log their contents.
        Known write/commit/ack failure -> DocumentStorageError -> outer handler;
        unexpected errors propagate. Never report success before acknowledgement.
        Malformed acknowledgement -> Interactor -> InvalidStorageResult -> outer
        handler without presentation/retry. No automatic retry: ambiguous
        acknowledgement may follow a real commit.
        Persistence, atomicity, identity generation and retention tests are deferred.
        """
        ...
