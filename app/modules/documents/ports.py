import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.modules.documents.repository import DocumentRepo

DocumentUow = Callable[[], AbstractAsyncContextManager[DocumentRepo]]


class PdfInspector(Protocol):
    async def extract_pages(self, content: bytes, timeout: float) -> list[dict]: ...


class PageRenderer(Protocol):
    async def render_png(self, content: bytes, number: int) -> bytes: ...


class OcrPreset(Protocol):
    """Saved model credentials, supplied by the LLM configuration (wired in shared.deps)."""

    @property
    def name(self) -> str: ...
    @property
    def model_id(self) -> str: ...
    @property
    def base_url(self) -> str: ...
    @property
    def api_key(self) -> str: ...


class OcrPresets(Protocol):
    async def default(self) -> OcrPreset | None: ...
    async def get(self, preset_id: uuid.UUID) -> OcrPreset | None: ...


OcrFailure = Literal["provider_timeout", "provider_error", "invalid_output"]


@dataclass(frozen=True)
class OcrReading:
    """Either recognised text or a provider failure reason (callers branch on it).

    steps says what each pass did, for the log only (never provider text). degraded means
    a pass failed or was skipped, so the text may lack structure or edit marks."""

    text: str | None = None
    reason: OcrFailure | None = None
    steps: tuple[str, ...] = field(default=(), compare=False)
    degraded: bool = field(default=False, compare=False)


class OcrReader(Protocol):
    async def read(self, image: bytes, preset: OcrPreset) -> OcrReading: ...
