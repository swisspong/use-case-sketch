import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, LargeBinary, String, func
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

    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="positive_size"),
        CheckConstraint("page_count > 0", name="positive_pages"),
        CheckConstraint(
            "octet_length(original_pdf) = size_bytes", name="matching_size"
        ),
        Index("ix_documents_uploaded_at_id", uploaded_at.desc(), id.desc()),
    )
