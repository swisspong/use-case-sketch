from typing import Protocol

from .response import ExtractPdfTextResult


class ExtractPdfTextOutputBoundary(Protocol):
    def present(self, result: ExtractPdfTextResult) -> None:
        """Emit one final outcome. Concrete Presenter is deferred.

        Display text, localization and transport mapping belong to the Presenter.
        Extracted text is untrusted data; safe escaping belongs to presentation.
        Presentation errors propagate; never repeat extraction or persistence.
        """
        ...
