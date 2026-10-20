from typing import Protocol

from .response import OcrDocumentPagesResult


class OcrDocumentPagesOutputBoundary(Protocol):
    def present(self, result: OcrDocumentPagesResult) -> None:
        """Emit one final outcome (CLI: presentation/json_ocr_cli_presenter.py).

        OCR text is sensitive/untrusted; the Presenter must not print it by default.
        """
        ...
