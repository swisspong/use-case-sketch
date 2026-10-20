"""The recount migration against historical data in an isolated schema."""

import json
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests.settings.test_thai_max_migration import migration

FAILED = {
    "thai_percent": 90,
    "garbled_thai_percent": 0,
    "text_chars": 80,
    "image_percent": 100,
    "failed": ["max_thai_percent"],
    "passed": False,
}
PASSED = FAILED | {"failed": [], "passed": True}
OCR = {"text": "x", "quality": FAILED}  # OCR quality never counts


async def test_recount_drops_pages_with_ocr_and_leaves_other_documents(engine):
    ocred, untouched, legacy = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    schema = "migration_" + uuid.uuid4().hex
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            await connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))

            def apply(conn, names, method="upgrade"):
                with Operations.context(MigrationContext.configure(conn)):
                    for name in names:
                        getattr(migration(name), method)()

            await connection.run_sync(
                apply,
                (
                    "20261015_settings_initial.py",
                    "20261015_documents_initial.py",
                    "20261015_document_pages.py",
                    "20261015_thai_max.py",
                    "20261016_page_ocr.py",
                ),
            )

            async def document(id, pages, count):
                await connection.execute(
                    text(
                        "INSERT INTO documents (id,filename,size_bytes,page_count,original_pdf,thresholds,ocr_suggested_count) VALUES (:id,'a.pdf',1,:n,'x',CAST('{}' AS jsonb),:count)"
                    ),
                    {"id": id, "n": max(len(pages), 3), "count": count},
                )
                for n, (quality, ocr) in enumerate(pages, 1):
                    await connection.execute(
                        text(
                            "INSERT INTO document_pages VALUES (:id,:n,'t',CAST(:q AS jsonb),CAST(:ocr AS jsonb))"
                        ),
                        {
                            "id": id,
                            "n": n,
                            "q": json.dumps(quality),
                            "ocr": json.dumps(ocr) if ocr else None,
                        },
                    )

            await document(ocred, [(FAILED, OCR), (FAILED, None), (PASSED, OCR)], 2)
            await document(untouched, [(FAILED, None)], 1)
            await document(legacy, [], 3)  # stored before per-page assessment

            async def counts():
                rows = await connection.execute(
                    text("SELECT id, ocr_suggested_count FROM documents")
                )
                return dict(rows.all())

            name = ("20261017_ocr_suggested.py",)
            await connection.run_sync(apply, name)
            assert await counts() == {ocred: 1, untouched: 1, legacy: 3}
            await connection.run_sync(apply, name, "downgrade")
            assert await counts() == {ocred: 2, untouched: 1, legacy: 3}
        finally:
            await transaction.rollback()
