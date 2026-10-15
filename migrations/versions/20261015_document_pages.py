"""Persist upload-time thresholds and per-page extraction results; retain old PDFs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261015_document_pages"
down_revision = "20261015_documents"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents", sa.Column("thresholds", postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("ocr_suggested_count", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_documents_matching_assessment"),
        "documents",
        "(thresholds IS NULL) = (ocr_suggested_count IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_documents_suggested_count_range"),
        "documents",
        "ocr_suggested_count BETWEEN 0 AND page_count",
    )
    op.create_table(
        "document_pages",
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("number", sa.Integer(), primary_key=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("quality", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "number > 0", name=op.f("ck_document_pages_positive_number")
        ),
    )


def downgrade():
    op.drop_table("document_pages")
    op.drop_constraint(
        op.f("ck_documents_matching_assessment"), "documents", type_="check"
    )
    op.drop_constraint(
        op.f("ck_documents_suggested_count_range"), "documents", type_="check"
    )
    op.drop_column("documents", "ocr_suggested_count")
    op.drop_column("documents", "thresholds")
