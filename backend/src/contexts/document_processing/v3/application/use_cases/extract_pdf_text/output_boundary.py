from typing import Protocol

from .response import ExtractPdfTextResult


class ExtractPdfTextOutputBoundary(Protocol):
    def present(self, result: ExtractPdfTextResult) -> None:
        """Emit one final outcome. JsonCliPresenter maps local CLI outcomes.

        Display text, localization and transport mapping belong to the Presenter.
        Extracted text is untrusted, sensitive data; do not log or print it by
        default. JsonCliPresenter prints OCR-suggested page numbers and, when
        reports are present, assessed/suspicious counts; never raw text.
        Presentation errors propagate; never repeat extraction or persistence.
        """
        ...
