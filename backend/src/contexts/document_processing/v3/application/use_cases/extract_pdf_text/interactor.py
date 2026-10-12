from ....domain.documents.extraction import DocumentExtraction

from .configuration import ExtractionConfig
from .errors import InvalidExtractionConfiguration, InvalidPdfExtractionResult, InvalidStorageResult
from .input_boundary import ExtractPdfTextInputBoundary
from .output_boundary import ExtractPdfTextOutputBoundary
from .ports import ExtractionStore, ParsedPdf, PdfRejected, PdfTextExtractor, SavedDocument
from .request import ExtractPdfTextRequest
from .response import ExtractedPage, ExtractionRejected, ExtractionSaved


class ExtractPdfTextInteractor(ExtractPdfTextInputBoundary):
    def __init__(
        self, *, pdf_extractor: PdfTextExtractor, store: ExtractionStore,
        output: ExtractPdfTextOutputBoundary, config: ExtractionConfig,
    ) -> None:
        self.pdf_extractor = pdf_extractor
        self.store = store
        self.output = output
        self.config = config

    def execute(self, request: ExtractPdfTextRequest) -> None:
        if not isinstance(request.pdf, bytes) or not request.pdf:
            self.output.present(ExtractionRejected("invalid_pdf"))
            return
        parsed = self.pdf_extractor.extract(request.pdf)
        if isinstance(parsed, PdfRejected):
            if parsed.code not in ("invalid_pdf", "encrypted_pdf"):
                raise InvalidPdfExtractionResult("Undeclared PDF rejection")
            self.output.present(ExtractionRejected(parsed.code))
            return
        if not isinstance(parsed, ParsedPdf):
            raise InvalidPdfExtractionResult("Undeclared parser result")
        document = DocumentExtraction.from_pdf(
            parsed.pages, threshold_percent=self.config.unreadable_threshold_percent,
            suspicious_threshold_percent=self.config.suspicious_threshold_percent,
        )
        if not isinstance(document, DocumentExtraction):
            if document.reason in ("invalid_threshold", "invalid_suspicious_threshold"):
                raise InvalidExtractionConfiguration("Invalid quality threshold")
            raise InvalidPdfExtractionResult("Parser returned invalid page facts")
        saved = self.store.save(document, pdf=request.pdf)
        if (
            not isinstance(saved, SavedDocument)
            or not isinstance(saved.document_id, str) or not saved.document_id.strip()
        ):
            raise InvalidStorageResult("Malformed storage acknowledgement")
        self.output.present(ExtractionSaved(saved.document_id, tuple(
            ExtractedPage(
                page.number, page.text, page.ocr_suggested, page.ocr_reason,
                page.problem_character_count, page.non_whitespace_character_count,
                page.problem_percent,
            )
            for page in document.pages
        ), raw_text_quality=document.raw_text_quality))
