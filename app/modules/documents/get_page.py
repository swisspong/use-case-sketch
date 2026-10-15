"""Read immutable parser results and the upload-time threshold snapshot.
SPEC
- [x] Missing document and page have distinct errors; legacy documents have no results.
- [x] Reading a page returns saved text, quality and the original threshold snapshot.
- [x] The latest successful OCR result is returned with the page, or null.
"""

import uuid

from fastapi import APIRouter

from app.modules.documents.errors import PageNotFound
from app.modules.documents.get_document import get_document
from app.modules.documents.repository import DocumentRepo
from app.modules.documents.schemas import PageResult
from app.shared.deps import SessionDep


async def get_page(
    document_id: uuid.UUID, number: int, repo: DocumentRepo
) -> PageResult:
    document = await get_document(document_id, repo)
    page = await repo.get_page(document_id, number)
    if page is None:
        raise PageNotFound
    return PageResult(
        number=number,
        thresholds=document.thresholds,
        parser={"text": page.text, "quality": page.quality},
        ocr=page.ocr,
    )


router = APIRouter()


@router.get("/documents/{document_id}/pages/{number}", response_model=PageResult)
async def get_page_endpoint(
    document_id: uuid.UUID, number: int, session: SessionDep
) -> PageResult:
    return await get_page(document_id, number, DocumentRepo(session))
