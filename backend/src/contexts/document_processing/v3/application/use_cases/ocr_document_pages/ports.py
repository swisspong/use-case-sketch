"""Dependencies of OcrDocumentPages; named failures live in the sibling errors module."""

from dataclasses import dataclass, field
from typing import Literal, Protocol, Union

from ....domain.documents.ocr_attempt import OcrAttempt, SuggestedPage
from ...model_presets import VisionPreset


@dataclass(frozen=True)
class SavedDocumentForOcr:
    document_id: str
    pdf: bytes = field(repr=False)
    pages: tuple[SuggestedPage, ...]
    # Exact extraction threshold; OCR text must pass this same rule.
    threshold_percent: float


@dataclass(frozen=True)
class DocumentNotFound:
    """No saved document with this identity (business rejection, not an outage)."""


class SavedDocumentSource(Protocol):
    def load(self, document_id: str) -> SavedDocumentForOcr | DocumentNotFound:
        """Read exact original PDF + ordered page suggestions of one saved document.

        Local adapter reads <data-dir>/<id>/original.pdf + extraction.json
        (schema 3: pages[].number/ocr_suggested, threshold_percent) with the same
        private-file checks. Malformed id -> NotFound. Facts that violate the
        domain contract -> Interactor -> InvalidOcrResult.
        I/O or corrupt record -> DocumentSourceError -> outer handler.
        """
        ...


@dataclass(frozen=True)
class PageImage:
    media_type: Literal["image/png"]
    data: bytes = field(repr=False)


class PageRenderer(Protocol):
    def render(self, *, pdf: bytes, page_number: int) -> PageImage:
        """Rasterize exactly one one-based page (Pypdfium2PageRenderer).

        Bounded DPI/pixel size. Known render failure -> PageRenderingError.
        """
        ...


@dataclass(frozen=True)
class OcrText:
    text: str = field(repr=False)


@dataclass(frozen=True)
class OcrUnreadable:
    """Model explicitly reports it cannot read the page; not an outage."""


OcrReadResult = Union[OcrText, OcrUnreadable]


class OcrReader(Protocol):
    def read(self, *, image: PageImage, preset: VisionPreset) -> OcrReadResult:
        """Send one page image to the exact preset (OpenAICompatibleOcrReader).

        Use exactly preset.endpoint/model/api_key; no env key, no substitution,
        no automatic retry, bounded timeout/payload. Known timeout/outage/auth
        failure and malformed/truncated replies -> OcrProviderError (page
        ocr_unavailable). Never log image, text or credentials.
        """
        ...


@dataclass(frozen=True)
class SavedOcrAttempt:
    attempt_id: str


class OcrAttemptStore(Protocol):
    def append(self, attempt: OcrAttempt) -> SavedOcrAttempt:
        """Atomically add a NEW attempt file under the document directory.

        e.g. <data-dir>/<document_id>/ocr/<attempt_id>.json. Never rewrite
        extraction.json, original.pdf or earlier attempts. Acknowledge only after
        durable commit; known failure -> OcrAttemptStorageError; no retry.
        No credentials are stored.
        """
        ...
