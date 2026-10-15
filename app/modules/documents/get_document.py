"""Open saved document metadata and original PDF.
SPEC
- [x] Metadata and exact original bytes can be read by id; missing ids return DOC_005.
"""

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Response

from app.modules.documents.errors import DocumentNotFound
from app.modules.documents.models import Document
from app.modules.documents.repository import DocumentRepo
from app.modules.documents.schemas import DocumentSummary
from app.shared.deps import SessionDep


async def get_document(document_id: uuid.UUID, repo: DocumentRepo) -> Document:
    document = await repo.get(document_id)
    if document is None:
        raise DocumentNotFound
    return document


async def get_original(
    document_id: uuid.UUID, repo: DocumentRepo
) -> tuple[Document, bytes]:
    document = await get_document(document_id, repo)
    content = await repo.get_pdf(document_id)
    if content is None:
        raise DocumentNotFound
    return document, content


router = APIRouter()


@router.get("/documents/{document_id}", response_model=DocumentSummary)
async def get_document_endpoint(
    document_id: uuid.UUID, session: SessionDep
) -> DocumentSummary:
    return DocumentSummary.model_validate(
        await get_document(document_id, DocumentRepo(session))
    )


@router.get("/documents/{document_id}/original", response_class=Response)
async def get_original_endpoint(
    document_id: uuid.UUID, session: SessionDep
) -> Response:
    document, content = await get_original(document_id, DocumentRepo(session))
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline; filename*=UTF-8''"
            + quote(document.filename, safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
