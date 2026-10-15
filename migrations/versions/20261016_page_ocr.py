"""Store the latest successful OCR result per document page."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261016_page_ocr"
down_revision = "20261015_thai_max"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_pages",
        sa.Column("ocr", postgresql.JSONB(none_as_null=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_pages", "ocr")
