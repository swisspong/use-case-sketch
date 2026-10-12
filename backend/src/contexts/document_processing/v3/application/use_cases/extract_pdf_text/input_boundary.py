from typing import Protocol

from .request import ExtractPdfTextRequest


class ExtractPdfTextInputBoundary(Protocol):
    def execute(self, request: ExtractPdfTextRequest) -> None:
        """Extract pages, evaluate quality, suggest OCR, save, present.

        Trusted threshold config is injected. The upload supplies only the PDF.
        Extraction never invokes a model and needs no preset or credentials:
        OCR is a separate, later use case the user triggers explicitly.
        Empty/non-bytes PDF emits a typed rejection without I/O.
        Parser rejection emits its declared code without persistence.
        DocumentExtraction counts problem characters as the union of local
        signals (U+FFFD, isolated Latin next to Thai, Thai mark errors, spaces
        splitting a Thai syllable, controls, private use) over non-whitespace
        code points. Strictly above unreadable_threshold_percent, or a blank
        page, suggests OCR. Parser text is always kept unchanged.
        Optional suspicious_threshold_percent additionally saves report-only
        raw_text_quality; None means not assessed, not a clean report.
        Pre-storage failures prevent save. Storage/ack failures never emit
        success but may follow a real commit; do not retry or claim rollback.
        Acknowledged save emits ExtractionSaved exactly once.
        Deferred caller is responsible for authenticated resource access.
        """
        ...
