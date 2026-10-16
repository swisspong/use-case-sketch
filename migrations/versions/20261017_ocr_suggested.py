"""Recount ocr_suggested_count: a parser-failed page with any OCR is no longer suggested."""

from alembic import op

revision = "20261017_ocr_suggested"
down_revision = "20261016_page_ocr"
branch_labels = None
depends_on = None


def _recount(page_filter: str) -> None:
    # Only documents with OCR results can change; others keep their stored count.
    op.execute(
        f"""
        UPDATE documents d SET ocr_suggested_count = (
            SELECT count(*) FROM document_pages p
            WHERE p.document_id = d.id
              AND NOT (p.quality->>'passed')::boolean {page_filter}
        )
        WHERE d.ocr_suggested_count IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM document_pages p
            WHERE p.document_id = d.id AND p.ocr IS NOT NULL
          )
        """
    )


def upgrade() -> None:
    _recount("AND p.ocr IS NULL")


def downgrade() -> None:
    _recount("")
