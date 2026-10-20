"""Exercise the real additive migration against historical data in an isolated schema."""

import importlib.util
import json
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def migration(name):
    path = Path(__file__).resolve().parents[2] / "migrations" / "versions" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_rename_preserves_settings_and_historical_document_snapshot(engine):
    old = {
        "min_thai_percent": 65,
        "max_garbled_thai_percent": 5,
        "min_text_chars": 50,
        "max_image_percent": 80,
    }
    quality = {
        "thai_percent": 38,
        "garbled_thai_percent": 0,
        "text_chars": 80,
        "image_percent": 0,
        "failed": ["min_thai_percent"],
        "passed": False,
    }
    document_id = uuid.uuid4()
    schema = "migration_" + uuid.uuid4().hex
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))

            def upgrade_old(conn):
                with Operations.context(MigrationContext.configure(conn)):
                    for name in (
                        "20261015_settings_initial.py",
                        "20261015_documents_initial.py",
                        "20261015_document_pages.py",
                    ):
                        migration(name).upgrade()

            await connection.run_sync(upgrade_old)
            await connection.execute(
                text("INSERT INTO text_quality_thresholds VALUES (1,65,5,50,80)")
            )
            await connection.execute(
                text(
                    "INSERT INTO documents (id,filename,size_bytes,page_count,original_pdf,thresholds,ocr_suggested_count) VALUES (:id,'old.pdf',1,1,:pdf,CAST(:thresholds AS jsonb),1)"
                ),
                {"id": document_id, "pdf": b"x", "thresholds": json.dumps(old)},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_pages VALUES (:id,1,'unchanged',CAST(:quality AS jsonb))"
                ),
                {"id": document_id, "quality": json.dumps(quality)},
            )

            def apply(conn, method):
                with Operations.context(MigrationContext.configure(conn)):
                    getattr(migration("20261015_thai_max.py"), method)()

            await connection.run_sync(apply, "upgrade")
            assert (
                await connection.scalar(
                    text("SELECT max_thai_percent FROM text_quality_thresholds")
                )
                == 65
            )
            assert (
                await connection.scalar(text("SELECT thresholds FROM documents")) == old
            )
            assert (
                await connection.scalar(text("SELECT quality FROM document_pages"))
                == quality
            )
            assert (
                await connection.scalar(text("SELECT original_pdf FROM documents"))
                == b"x"
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conname='ck_text_quality_thresholds_max_thai_percent_range' AND connamespace=to_regnamespace(:schema)"
                    ),
                    {"schema": schema},
                )
                == 1
            )
            await connection.run_sync(apply, "downgrade")
            assert (
                await connection.scalar(
                    text("SELECT min_thai_percent FROM text_quality_thresholds")
                )
                == 65
            )
            assert (
                await connection.scalar(text("SELECT thresholds FROM documents")) == old
            )
        finally:
            await transaction.rollback()
