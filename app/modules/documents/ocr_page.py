"""OCR one saved page with an LLM preset and keep only the latest successful result.
SPEC
- [x] No preset_id uses the default preset; missing default is DOC_012; unknown id is DOC_013.
- [x] Missing document DOC_007, page outside 1..page_count DOC_009, unassessed page DOC_008,
      all checked before rendering or calling the provider.
- [x] Provider is called outside any DB transaction: read (tx) -> render + OCR -> save (tx).
- [x] OCR text is assessed with the upload-time snapshot and the parser's image coverage.
- [x] Success replaces the previous OCR; OCR quality is shown, never judged.
- [x] ocr_suggested_count drops once a parser-failed page has any OCR (reruns and
      parser-passed pages leave it; failures change nothing).
- [x] Provider timeout/error/invalid output -> 200 status=failed + reason; previous OCR kept.
- [x] OCR text keeps table structure (Markdown pipe tables, labelled layout-frame blocks)
      only when the structuring pass leaves the transcribed text unchanged (adapter).
- [x] Markup the transcription pass returns anyway (pipe/HTML/LaTeX tables, <br>, inline
      tags) is flattened to plain lines before structuring and in the fallback (adapter).
- [x] The structuring pass runs with reasoning_effort "low"; a table missing its separator
      row is repaired without touching cell text (adapter).
- [x] Superscript footnote markers are kept as [^n] (footnote lines as [^n]:), so they never
      merge into numbers; a full-width title row has no label and empty labels are removed.
- [x] Strike/underline marks (~~, ++) that the transcription pass adds on its own are removed.
      Struck/underlined text is instead found in pixels; a mark pass wraps the boxed words
      in ~~/++, kept only if they form exactly the detected runs (boxes on consecutive
      lines may be one run), each run's length fits its box width, and the text is
      unchanged (adapter).
- [x] Each OCR logs one line (document, page, preset, steps; never provider text): WARNING
      when it failed or a pass was skipped/rejected, INFO otherwise.
- [x] POST /documents/{id}/ocr returns OcrResult / mapped errors (endpoint).
"""

import logging
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
    reason: OcrFailure | None = None
    duration_ms: int


log = logging.getLogger(__name__)


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

    # One line per OCR so a reported document can be traced; degraded results are
    # warnings so they show without logging configuration. Never provider text.
    log.log(
        logging.WARNING if reading.text is None or reading.degraded else logging.INFO,
        "OCR document=%s page=%d preset=%s %s ms=%d steps=%s",
        document_id,
        data.page,
        preset.name,
        "failed" if reading.text is None else "ok",
        elapsed(),
        "; ".join(reading.steps) or "-",
    )

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
