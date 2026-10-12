"""External capabilities; named failures are declared in the sibling errors module."""

from dataclasses import dataclass
from typing import Literal, Protocol, Union

from ....domain.documents.extraction import (
    DocumentExtraction,
    SourcePage,
)


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
        PypdfTextExtractor implements this port; PDF-byte integration tests cover
        page ordering, blank pages, malformed/encrypted PDFs and resource failure.
        """
        ...


@dataclass(frozen=True)
class SavedDocument:
    document_id: str


class ExtractionStore(Protocol):
    def save(self, document: DocumentExtraction, *, pdf: bytes) -> SavedDocument:
        """Atomically create a new document: exact original PDF + all page results.

        Persist parser text, OCR suggestion and problem counts unchanged and bind
        the original bytes to the SAME new document identity. Acknowledge only
        when BOTH PDF and all ordered page results are durably committed/available.
        Never acknowledge an orphaned PDF or missing page results. Unit mocks do
        not prove this guarantee. Assign and return a nonblank new identity only
        after successful commit. No business defaults/decisions here.
        Original PDFs/text are sensitive; local storage enforces OS-owner-only
        access and never logs their contents.
        Known write/commit/ack failure -> DocumentStorageError -> outer handler;
        unexpected errors propagate. Never report success before acknowledgement.
        Malformed acknowledgement -> Interactor -> InvalidStorageResult -> outer
        handler without presentation/retry. No automatic retry: ambiguous
        acknowledgement may follow a real commit.
        Also retain document.raw_text_quality, when present, exactly in page order.
        The local adapter writes schema 3; existing documents are never migrated
        or overwritten. Later OCR results are added as separate files, never by
        rewriting extraction.json.
        """
        ...
