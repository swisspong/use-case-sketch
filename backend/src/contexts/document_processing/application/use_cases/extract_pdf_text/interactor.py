from contexts.document_processing.domain.documents.extraction import DocumentExtraction

from .configuration import ExtractionConfig, UnknownVisionPreset
from .errors import (
    FallbackExtractionError, InvalidExtractionConfiguration, InvalidFallbackExtractionResult,
    InvalidPdfExtractionResult, InvalidStorageResult,
)
from .input_boundary import ExtractPdfTextInputBoundary
from .output_boundary import ExtractPdfTextOutputBoundary
from .ports import (
    ExtractionStore, FallbackExtractor, ParsedPdf, PdfRejected, PdfTextExtractor, VisionText,
    SavedDocument, VisionUnreadable,
)
from .request import ExtractPdfTextRequest
from .response import ExtractedPage, ExtractionRejected, ExtractionSaved


class ExtractPdfTextInteractor(ExtractPdfTextInputBoundary):
    def __init__(
        self, *, pdf_extractor: PdfTextExtractor, fallback: FallbackExtractor,
        store: ExtractionStore, output: ExtractPdfTextOutputBoundary,
        config: ExtractionConfig,
    ) -> None:
        self.pdf_extractor = pdf_extractor
        self.fallback = fallback
        self.store = store
        self.output = output
        self.config = config

    def execute(self, request: ExtractPdfTextRequest) -> None:
        preset = self.config.select(request.preset_name)
        if isinstance(preset, UnknownVisionPreset):
            self.output.present(ExtractionRejected("invalid_preset"))
            return
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
        )
        if not isinstance(document, DocumentExtraction):
            if document.reason == "invalid_threshold":
                raise InvalidExtractionConfiguration("Invalid unreadable threshold")
            raise InvalidPdfExtractionResult("Parser returned invalid page facts")
        for page in document.pages:
            if page.status != "pending_fallback":
                continue
            try:
                result = self.fallback.extract_page(
                    pdf=request.pdf, page_number=page.number, preset=preset,
                )
            except FallbackExtractionError:
                updated = document.fail_fallback(
                    page_number=page.number, code="fallback_unavailable",
                    preset_name=preset.name, model=preset.model,
                )
            else:
                if isinstance(result, VisionText):
                    updated = document.complete_fallback(
                        page_number=page.number, text=result.text,
                        preset_name=preset.name, model=preset.model,
                    )
                elif isinstance(result, VisionUnreadable):
                    updated = document.fail_fallback(
                        page_number=page.number, code="unreadable",
                        preset_name=preset.name, model=preset.model,
                    )
                else:
                    raise InvalidFallbackExtractionResult("Undeclared fallback result")
            if not isinstance(updated, DocumentExtraction):
                raise InvalidFallbackExtractionResult("Invalid fallback facts or transition")
            document = updated
        saved = self.store.save(document, pdf=request.pdf)
        if (
            not isinstance(saved, SavedDocument)
            or not isinstance(saved.document_id, str) or not saved.document_id.strip()
        ):
            raise InvalidStorageResult("Malformed storage acknowledgement")
        self.output.present(ExtractionSaved(saved.document_id, tuple(
            ExtractedPage(
                page.number, page.text, page.status, page.method, page.failure_code,
                page.preset_name, page.model,
            )
            for page in document.pages
        )))
