from typing import Protocol

from .request import ExtractPdfTextRequest


class ExtractPdfTextInputBoundary(Protocol):
    def execute(self, request: ExtractPdfTextRequest) -> None:
        """Extract pages, evaluate quality, selectively fall back, save, present.

        Trusted catalogue/threshold config is injected. The upload supplies only
        the PDF and an approved preset name, never an endpoint/model/threshold.
        Unknown preset and empty/non-bytes PDF emit typed rejections without I/O.
        Parser rejection emits its declared code without fallback or persistence.
        DocumentExtraction owns U+FFFD/non-whitespace code-point quality, strict
        threshold comparison, empty-page fallback and terminal page transitions.
        Fallback text uses the same threshold. No repeated fallback; failed pages
        discard bad text and retain semantic failure plus attempted preset/model.
        Catch only FallbackExtractionError for per-page recovery; other system or
        contract failures reach the deferred outer handler. Pre-storage failures
        prevent save. Storage/ack failures never emit success but may follow a real
        commit; do not retry or claim the operation was rolled back.
        After all pages are terminal, save exact original PDF and all ordered
        results together. Acknowledged save emits ExtractionSaved, which means
        results were saved, NOT that every page extracted successfully.
        Deferred caller is responsible for authenticated resource access; this
        use case does not import IAM internals or treat caller claims as grants.
        One final outcome per normal execution, after storage acknowledgement.
        Declared system failures propagate unless recovery is explicitly supported.
        Production adapters, preset management and Presenter remain deferred.
        """
        ...
