from typing import Protocol

from .response import ExtractPdfTextResult


class ExtractPdfTextOutputBoundary(Protocol):
    def present(self, result: ExtractPdfTextResult) -> None:
        """Emit one final outcome. JsonCliPresenter maps local CLI outcomes.

        Display text, localization and transport mapping belong to the Presenter.
        Extracted text is untrusted data; safe escaping belongs to presentation.
        Optional raw_text_quality describes the parser source, not final page text.
        Empty reports mean assessment was not enabled, not that no signals exist.
        Raw source is sensitive/untrusted; do not log or print it by default.
        JsonCliPresenter adds assessed_pages/suspicious_pages summary counts only
        when reports are present; raw text and per-page reports remain off stdout.
        Presentation errors propagate; never repeat extraction or persistence.
        """
        ...
