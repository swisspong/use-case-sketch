"""Validate and atomically store one original PDF plus metadata (round one).
SPEC
- [x] Reject non-PDF content, oversized, multiple, encrypted and broken PDFs.
- [x] Count pages before saving; parsing timeout/cancellation saves nothing.
- [x] Save original bytes and metadata together; quality remains explicitly not checked.
"""

import asyncio
import time

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.modules.documents.errors import FileTooLarge, NotPdf, TooManyFiles
from app.modules.documents.models import Document
from app.modules.documents.ports import PdfInspector
from app.modules.documents.repository import DocumentRepo
from app.modules.documents.schemas import DocumentSummary, UploadResult
from app.shared.deps import PdfInspectorDep, SessionDep, SettingsDep
from app.shared.errors import Invalid


async def upload_document(
    filename: str,
    content: bytes,
    repo: DocumentRepo,
    inspector: PdfInspector,
    max_bytes: int,
    timeout: float,
) -> UploadResult:
    start = time.monotonic()
    if len(content) > max_bytes:
        raise FileTooLarge(field="file")
    if not content.startswith(b"%PDF-"):
        raise NotPdf(field="file")
    pages = await inspector.page_count(content, timeout)
    filename = filename.replace("\\", "/").split("/")[-1]
    filename = (
        "".join(c for c in filename if c.isprintable()).strip()[:255] or "document.pdf"
    )
    document = await repo.add(
        Document(
            filename=filename,
            size_bytes=len(content),
            page_count=pages,
            original_pdf=content,
        )
    )
    return UploadResult(
        document=DocumentSummary.model_validate(document),
        duration_ms=round((time.monotonic() - start) * 1000),
    )


router = APIRouter()


@router.post("/documents", status_code=201, response_model=UploadResult)
async def upload_document_endpoint(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    inspector: PdfInspectorDep,
) -> UploadResult:
    try:
        async with request.form(max_files=1, max_fields=0) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise Invalid
            content = await file.read(settings.documents_max_bytes + 1)
            work = asyncio.create_task(
                upload_document(
                    file.filename or "document.pdf",
                    content,
                    DocumentRepo(session),
                    inspector,
                    settings.documents_max_bytes,
                    settings.documents_parse_timeout_seconds,
                )
            )

            async def disconnected():
                while (await request.receive())["type"] != "http.disconnect":
                    pass

            connection = asyncio.create_task(disconnected())
            try:
                await asyncio.wait(
                    {work, connection}, return_when=asyncio.FIRST_COMPLETED
                )
                if connection.done():
                    # Cleanup below cancels parsing before dependency rollback.
                    raise Invalid
                return await work
            finally:
                for task in (work, connection):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(work, connection, return_exceptions=True)
    except HTTPException as e:
        if "Too many files" in str(e.detail):
            raise TooManyFiles(field="file") from e
        raise Invalid from e
