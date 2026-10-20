"""Fresh global Settings schema (replaces the legacy per-user prototype)."""

from alembic import op
import sqlalchemy as sa

revision = "20261015_settings"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "text_quality_thresholds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("min_thai_percent", sa.Integer(), nullable=False),
        sa.Column("max_garbled_thai_percent", sa.Integer(), nullable=False),
        sa.Column("min_text_chars", sa.Integer(), nullable=False),
        sa.Column("max_image_percent", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "id = 1", name=op.f("ck_text_quality_thresholds_single_row")
        ),
        sa.CheckConstraint(
            "min_thai_percent BETWEEN 0 AND 100",
            name=op.f("ck_text_quality_thresholds_min_thai_percent_range"),
        ),
        sa.CheckConstraint(
            "max_garbled_thai_percent BETWEEN 0 AND 100",
            name=op.f("ck_text_quality_thresholds_max_garbled_thai_percent_range"),
        ),
        sa.CheckConstraint(
            "min_text_chars >= 0",
            name=op.f("ck_text_quality_thresholds_min_text_chars_range"),
        ),
        sa.CheckConstraint(
            "max_image_percent BETWEEN 0 AND 100",
            name=op.f("ck_text_quality_thresholds_max_image_percent_range"),
        ),
    )
    op.create_table(
        "llm_config_presets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("model_id", sa.String(200), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_llm_config_presets_name_ci",
        "llm_config_presets",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_llm_config_presets_one_default",
        "llm_config_presets",
        ["is_default"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_table("llm_config_presets")
    op.drop_table("text_quality_thresholds")
