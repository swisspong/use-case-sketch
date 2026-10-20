"""Use a maximum Thai percentage for future assessments; retain saved snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "20261015_thai_max"
down_revision = "20261015_document_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the configured number, but give it the newly requested upper-bound meaning.
    # Document JSON snapshots and page results remain historical facts, not recalculated.
    op.drop_constraint(
        op.f("ck_text_quality_thresholds_min_thai_percent_range"),
        "text_quality_thresholds",
        type_="check",
    )
    op.alter_column(
        "text_quality_thresholds",
        "min_thai_percent",
        new_column_name="max_thai_percent",
        existing_type=sa.Integer(),
    )
    op.create_check_constraint(
        op.f("ck_text_quality_thresholds_max_thai_percent_range"),
        "text_quality_thresholds",
        "max_thai_percent BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_text_quality_thresholds_max_thai_percent_range"),
        "text_quality_thresholds",
        type_="check",
    )
    op.alter_column(
        "text_quality_thresholds",
        "max_thai_percent",
        new_column_name="min_thai_percent",
        existing_type=sa.Integer(),
    )
    op.create_check_constraint(
        op.f("ck_text_quality_thresholds_min_thai_percent_range"),
        "text_quality_thresholds",
        "min_thai_percent BETWEEN 0 AND 100",
    )
