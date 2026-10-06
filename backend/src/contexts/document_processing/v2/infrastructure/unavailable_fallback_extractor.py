"""Explicit offline mode: no rendering, model invocation, network or retries."""

from ..application.use_cases.extract_pdf_text.configuration import VisionPreset
from ..application.use_cases.extract_pdf_text.errors import FallbackExtractionError
from ..application.use_cases.extract_pdf_text.ports import VisionResult


class UnavailableFallbackExtractor:
    def extract_page(self, *, pdf: bytes, page_number: int, preset: VisionPreset) -> VisionResult:
        raise FallbackExtractionError("Vision fallback is not configured")
