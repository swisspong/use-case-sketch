import uuid

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document


class DocumentRepo:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, document: Document) -> Document:
        self._session.add(document)
        await self._session.flush()
        return document

    async def list_documents(
        self, page: int, page_size: int
    ) -> tuple[list[Document], int]:
        # One statement keeps count and page consistent under concurrent uploads.
        ranked = (
            select(Document.id)
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .subquery()
        )
        total = select(func.count(Document.id).label("total")).subquery()
        rows = (
            await self._session.execute(
                select(Document, total.c.total)
                .select_from(total)
                .outerjoin(ranked, true())
                .outerjoin(Document, Document.id == ranked.c.id)
                .order_by(Document.uploaded_at.desc(), Document.id.desc())
            )
        ).all()
        return [document for document, _ in rows if document is not None], rows[0][1]

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self._session.get(Document, document_id)

    async def get_pdf(self, document_id: uuid.UUID) -> bytes | None:
        return await self._session.scalar(
            select(Document.original_pdf).where(Document.id == document_id)
        )
