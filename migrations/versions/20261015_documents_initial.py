"""Original PDF storage and document metadata (round one)."""

import sqlalchemy as sa
from alembic import op

revision = "20261015_documents"
down_revision = "20261015_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("original_pdf", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_documents_positive_size")),
        sa.CheckConstraint("page_count > 0", name=op.f("ck_documents_positive_pages")),
        sa.CheckConstraint(
            "octet_length(original_pdf) = size_bytes",
            name=op.f("ck_documents_matching_size"),
        ),
    )
    op.create_index(
        "ix_documents_uploaded_at_id",
        "documents",
        [sa.text("uploaded_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_table("documents")
