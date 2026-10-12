from dataclasses import dataclass


@dataclass(frozen=True)
class OcrDocumentPagesRequest:
    """User-triggered OCR of an already saved document.

    page_numbers=None means "every page extraction suggested for OCR".
    Explicit numbers may include pages that were not suggested (user decision).
    The caller selects only an approved preset name, never endpoint/model/key.
    """

    document_id: str
    preset_name: str
    page_numbers: tuple[int, ...] | None = None
