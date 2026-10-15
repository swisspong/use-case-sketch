"""List uploaded documents.
SPEC
- [x] Newest first, bounded pagination and total, without loading PDF blobs.
- [x] Empty and out-of-range pages return items=[] and the actual total.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.modules.documents.repository import DocumentRepo
from app.modules.documents.schemas import DocumentList, DocumentSummary
from app.shared.deps import SessionDep


async def list_documents(repo: DocumentRepo, page: int, page_size: int) -> DocumentList:
    documents, total = await repo.list_documents(page, page_size)
    return DocumentList(
        items=[DocumentSummary.model_validate(d) for d in documents], total=total
    )


router = APIRouter()


@router.get("/documents", response_model=DocumentList)
async def list_documents_endpoint(
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DocumentList:
    return await list_documents(DocumentRepo(session), page, page_size)
