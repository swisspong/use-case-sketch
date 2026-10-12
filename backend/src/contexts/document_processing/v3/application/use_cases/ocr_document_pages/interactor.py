from ....domain.documents.ocr_attempt import (
    InvalidOcrSelection, InvalidOcrTransition, InvalidSavedFacts, OcrAttempt,
)
from ...model_presets import InvalidModelPresetCatalogue, ModelPresetCatalogue, UnknownVisionPreset

from .configuration import OcrConfig
from .errors import InvalidOcrConfiguration, InvalidOcrResult, OcrProviderError, PageRenderingError
from .input_boundary import OcrDocumentPagesInputBoundary
from .output_boundary import OcrDocumentPagesOutputBoundary
from .ports import (
    DocumentNotFound, OcrAttemptStore, OcrReader, OcrText, OcrUnreadable, PageRenderer,
    SavedDocumentForOcr, SavedDocumentSource, SavedOcrAttempt,
)
from .request import OcrDocumentPagesRequest
from .response import OcrAttemptSaved, OcrPageResult, OcrRejected


class OcrDocumentPagesInteractor(OcrDocumentPagesInputBoundary):
    def __init__(
        self, *, documents: SavedDocumentSource, renderer: PageRenderer, ocr: OcrReader,
        attempts: OcrAttemptStore, output: OcrDocumentPagesOutputBoundary, config: OcrConfig,
    ) -> None:
        self.documents = documents
        self.renderer = renderer
        self.ocr = ocr
        self.attempts = attempts
        self.output = output
        self.config = config

    def execute(self, request: OcrDocumentPagesRequest) -> None:
        try:
            preset = ModelPresetCatalogue(self.config.presets).select(request.preset_name)
        except InvalidModelPresetCatalogue:
            raise InvalidOcrConfiguration("Invalid OCR preset catalogue") from None
        if isinstance(preset, UnknownVisionPreset):
            self.output.present(OcrRejected("invalid_preset"))
            return
        document = self.documents.load(request.document_id)
        if isinstance(document, DocumentNotFound):
            self.output.present(OcrRejected("document_not_found"))
            return
        if (
            not isinstance(document, SavedDocumentForOcr)
            or document.document_id != request.document_id
            or not isinstance(document.pdf, bytes) or not document.pdf
        ):
            raise InvalidOcrResult("Undeclared saved document facts")
        attempt = OcrAttempt.start(
            document_id=document.document_id, saved_pages=document.pages,
            requested=request.page_numbers, preset_name=preset.name, model=preset.model,
            threshold_percent=document.threshold_percent,
        )
        if isinstance(attempt, InvalidSavedFacts):
            raise InvalidOcrResult("Invalid saved document facts")
        if isinstance(attempt, InvalidOcrSelection):
            self.output.present(OcrRejected(attempt.reason))
            return
        for number in attempt.pending_page_numbers():
            # Known per-page failures are recovered; anything else propagates unsaved.
            try:
                image = self.renderer.render(pdf=document.pdf, page_number=number)
                result = self.ocr.read(image=image, preset=preset)
            except (PageRenderingError, OcrProviderError):
                updated = attempt.record_unavailable(page_number=number)
            else:
                if isinstance(result, OcrUnreadable):
                    updated = attempt.record_unreadable(page_number=number)
                elif isinstance(result, OcrText) and isinstance(result.text, str):
                    updated = attempt.record_text(page_number=number, text=result.text)
                else:
                    raise InvalidOcrResult("Undeclared OCR result")
            # Defensive: only pending pages are iterated, so the domain guard is
            # unreachable here; covered by domain tests, not the Interactor seam.
            if isinstance(updated, InvalidOcrTransition):
                raise InvalidOcrResult("Invalid OCR page transition")
            attempt = updated
        saved = self.attempts.append(attempt)
        if (
            not isinstance(saved, SavedOcrAttempt)
            or not isinstance(saved.attempt_id, str) or not saved.attempt_id.strip()
        ):
            raise InvalidOcrResult("Malformed storage acknowledgement")
        self.output.present(OcrAttemptSaved(document.document_id, saved.attempt_id, tuple(
            OcrPageResult(page.number, page.was_suggested, page.status, page.text)
            for page in attempt.pages
        )))
