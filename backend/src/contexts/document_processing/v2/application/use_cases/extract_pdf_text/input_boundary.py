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
        Optional suspicious_threshold_percent separately assesses every raw
        parser page using local Latin/Thai-mark/unusual-character heuristics.
        DocumentExtraction counts suspect non-whitespace positions once and flags
        strictly above that separate threshold. It never rewrites text, changes
        page status or requests extra fallback. None means no new assessment,
        not a clean report. Raw text/reports survive terminal fallback transitions;
        fallback text is never assessed by this detector. ExtractionSaved carries
        those ordered raw-source projections after storage acknowledgement.
        Local CLI reads this trusted optional configuration. The local store saves
        assessed documents as JSON schema 2 with raw reports, or schema 1 when not
        assessed. The Presenter adds assessed/suspicious counts without printing
        raw text. Real CLI/filesystem integration tests cover this path.
        Fallback text uses the original unreadable threshold. No repeated fallback;
        failed terminal page text is discarded while raw reports, semantic failure
        and attempted preset/model are retained.
        Catch only FallbackExtractionError for per-page recovery; other system or
        contract failures reach the caller's outer handler. Pre-storage failures
        prevent save. Storage/ack failures never emit success but may follow a real
        commit; do not retry or claim the operation was rolled back.
        After all pages are terminal, save exact original PDF and all ordered
        results together. Acknowledged save emits ExtractionSaved, which means
        results were saved, NOT that every page extracted successfully.
        Deferred caller is responsible for authenticated resource access; this
        use case does not import IAM internals or treat caller claims as grants.
        One final outcome per normal execution, after storage acknowledgement.
        Declared system failures propagate unless recovery is explicitly supported.
        Local CLI composes a real parser/store/JSON Presenter and an explicitly
        unavailable vision fallback. Remote vision, admin preset editing and
        authenticated API integration remain deferred.
        """
        ...
