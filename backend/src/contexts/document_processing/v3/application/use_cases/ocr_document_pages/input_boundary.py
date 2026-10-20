from typing import Protocol

from .request import OcrDocumentPagesRequest


class OcrDocumentPagesInputBoundary(Protocol):
    """User-triggered OCR of a saved document; extraction never calls this.

    Event                                   -> owner      -> action / destination
    unknown preset name                     -> catalogue  -> OcrRejected(invalid_preset), no I/O
    invalid trusted catalogue (incl. key)   -> catalogue  -> InvalidOcrConfiguration -> outer handler, no I/O
    DocumentNotFound                        -> source     -> OcrRejected(document_not_found)
    DocumentSourceError                     -> source     -> outer handler, no OCR
    malformed saved facts / id mismatch     -> domain     -> InvalidOcrResult -> outer handler, no OCR
    invalid selection                       -> OcrAttempt -> OcrRejected(no_pages_selected | page_not_found
                                                             | duplicate_page | no_suggested_pages)
    PageRenderingError / OcrProviderError   -> adapters   -> page ocr_unavailable, continue next page
    OcrUnreadable                           -> OcrReader  -> page unreadable
    OcrText blank or problem % > saved threshold -> OcrAttempt -> page unreadable, text discarded
    malformed OCR result / storage ack      -> Interactor -> InvalidOcrResult, nothing presented
    unexpected error                        -> propagate, stop later pages, nothing saved
    OcrAttemptStorageError                  -> store      -> outer handler, no success, no retry
    all pages terminal                      -> store.append (even if all failed) -> OcrAttemptSaved

    Selection: page_numbers=None -> all OCR-suggested pages; explicit -> exactly
    those saved pages (unsuggested allowed, recorded was_suggested=False),
    processed in document order. The selected preset (with its api_key) reaches
    only OcrReader; credentials never enter the attempt or outcome.
    """

    def execute(self, request: OcrDocumentPagesRequest) -> None:
        """Exactly one final outcome per normal execution, after storage ack."""
        ...
