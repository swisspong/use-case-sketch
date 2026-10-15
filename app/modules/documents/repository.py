import uuid

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentPage


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

    async def add_pages(self, document_id: uuid.UUID, pages: list[dict]) -> None:
        self._session.add_all(
            [
                DocumentPage(
                    document_id=document_id,
                    number=n,
                    text=p["text"],
                    quality=p["quality"],
                )
                for n, p in enumerate(pages, 1)
            ]
        )
        await self._session.flush()

    async def page_summaries(self, document_id: uuid.UUID) -> list[dict]:
        pages = (
            await self._session.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.number)
            )
        ).all()
        return [
            {
                "number": p.number,
                "ocr_suggested": not p.quality["passed"],
                "has_ocr": False,
                "text_passed": p.quality["passed"],
            }
            for p in pages
        ]

    async def get_page(self, document_id: uuid.UUID, number: int) -> dict | None:
        from sqlalchemy.orm import undefer

        page = await self._session.scalar(
            select(DocumentPage)
            .options(undefer(DocumentPage.text))
            .where(
                DocumentPage.document_id == document_id, DocumentPage.number == number
            )
        )
        return {"text": page.text, "quality": page.quality} if page else None
