import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int]
    page_count: Mapped[int]
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Store bytes in the same transaction as metadata: no orphaned files on rollback.
    original_pdf: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)

    thresholds: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    ocr_suggested_count: Mapped[int | None] = mapped_column(nullable=True)

    @property
    def quality_status(self) -> str:
        return "not_checked" if self.ocr_suggested_count is None else "checked"

    __table_args__ = (
        CheckConstraint(
            "(thresholds IS NULL) = (ocr_suggested_count IS NULL)",
            name="matching_assessment",
        ),
        CheckConstraint(
            "ocr_suggested_count BETWEEN 0 AND page_count", name="suggested_count_range"
        ),
        CheckConstraint("size_bytes > 0", name="positive_size"),
        CheckConstraint("page_count > 0", name="positive_pages"),
        CheckConstraint(
            "octet_length(original_pdf) = size_bytes", name="matching_size"
        ),
        Index("ix_documents_uploaded_at_id", uploaded_at.desc(), id.desc()),
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(deferred=True)
    quality: Mapped[dict] = mapped_column(JSONB)

    __table_args__ = (CheckConstraint("number > 0", name="positive_number"),)
