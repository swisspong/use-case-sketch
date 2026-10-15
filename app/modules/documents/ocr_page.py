"""OCR one saved page with an LLM preset and keep only the latest successful result.
SPEC
- [x] No preset_id uses the default preset; missing default is DOC_012; unknown id is DOC_013.
- [x] Missing document DOC_007, page outside 1..page_count DOC_009, unassessed page DOC_008,
      all checked before rendering or calling the provider.
- [x] Provider is called outside any DB transaction: read (tx) -> render + OCR -> save (tx).
- [x] OCR text is assessed with the upload-time snapshot and the parser's image coverage.
- [x] Success replaces the previous OCR; text_passed = parser passed or OCR passed.
- [x] Provider timeout/error/invalid output -> 200 status=failed + reason; previous OCR kept.
- [x] OCR text keeps table structure (Markdown pipe tables, labelled layout-frame blocks)
      only when the structuring pass leaves the transcribed text unchanged (adapter).
- [x] Markup that the transcription pass returns anyway (pipe or HTML tables, <br>, inline tags) is
      flattened to plain lines before structuring and in the fallback (adapter).
- [x] The structuring pass runs with reasoning_effort "low"; a table missing its separator
      row is repaired without touching cell text (adapter).
- [x] POST /documents/{id}/ocr returns OcrResult / mapped errors (endpoint).
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, StrictInt

from app.modules.documents.errors import (
    DocumentNotFound,
    NoDefaultPreset,
    OcrPresetNotFound,
    PageNotFound,
    PageOutOfRange,
)
from app.modules.documents.ports import (
    DocumentUow,
    OcrFailure,
    OcrPresets,
    OcrReader,
    PageRenderer,
)
from app.modules.documents.rules import assess_quality
from app.modules.documents.schemas import OcrOutput
from app.shared.deps import (
    DocumentUowDep,
    OcrPresetsDep,
    OcrReaderDep,
    PageRendererDep,
)


class OcrIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: StrictInt
    preset_id: uuid.UUID | None = None


class OcrResult(BaseModel):
    page: int
    status: Literal["ok", "failed"]
    ocr: OcrOutput | None = None
    text_passed: bool | None = None
    reason: OcrFailure | None = None
    duration_ms: int


async def ocr_page(
    document_id: uuid.UUID,
    data: OcrIn,
    uow: DocumentUow,
    presets: OcrPresets,
    renderer: PageRenderer,
    reader: OcrReader,
) -> OcrResult:
    start = time.monotonic()
    async with uow() as repo:
        document = await repo.get(document_id)
        if document is None:
            raise DocumentNotFound
        if not 1 <= data.page <= document.page_count:
            raise PageOutOfRange
        page = await repo.get_page(document_id, data.page)
        if page is None:
            raise PageNotFound  # stored before per-page assessment existed
        thresholds, parser_quality = document.thresholds, page.quality
        content = await repo.get_pdf(document_id)
    if data.preset_id is None:
        preset = await presets.default()
        if preset is None:
            raise NoDefaultPreset
    else:
        preset = await presets.get(data.preset_id)
        if preset is None:
            raise OcrPresetNotFound

    image = await renderer.render_png(content, data.page)
    reading = await reader.read(image, preset)

    def elapsed() -> int:
        return round((time.monotonic() - start) * 1000)

    if reading.text is None:
        return OcrResult(
            page=data.page,
            status="failed",
            reason=reading.reason,
            duration_ms=elapsed(),
        )
    ocr = OcrOutput(
        preset_name=preset.name,
        model_id=preset.model_id,
        created_at=datetime.now(UTC),
        text=reading.text,
        quality=assess_quality(
            reading.text, parser_quality["image_percent"], thresholds
        ),
    )
    async with uow() as repo:
        await repo.save_ocr(document_id, data.page, ocr.model_dump(mode="json"))
    return OcrResult(
        page=data.page,
        status="ok",
        ocr=ocr,
        text_passed=parser_quality["passed"] or ocr.quality.passed,
        duration_ms=elapsed(),
    )


router = APIRouter()


@router.post(
    "/documents/{document_id}/ocr",
    response_model=OcrResult,
    response_model_exclude_none=True,
)
async def ocr_page_endpoint(
    document_id: uuid.UUID,
    data: OcrIn,
    uow: DocumentUowDep,
    presets: OcrPresetsDep,
    renderer: PageRendererDep,
    reader: OcrReaderDep,
) -> OcrResult:
    return await ocr_page(document_id, data, uow, presets, renderer, reader)
