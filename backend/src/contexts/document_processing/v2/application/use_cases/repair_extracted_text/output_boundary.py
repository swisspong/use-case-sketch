from typing import Protocol

from .response import RepairExtractedTextResult


class RepairExtractedTextOutputBoundary(Protocol):
    def present(self, result: RepairExtractedTextResult) -> None:
        """Present one final outcome; completed repairs already have repair_id.

        Suggestions are sensitive, untrusted text, not approved replacements.
        Escaping, localization, transport mapping and safe display belong to the
        Presenter. Do not log document text or model output by default.
        Presentation failures propagate; do not repeat model invocation or history
        write. A presentation failure does not roll back the committed repair run.
        """
        ...
