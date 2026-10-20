import asyncio
import io
import uuid

import httpx
import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from app.modules.documents.adapters.pdf_inspector import LocalPdfInspector
from app.modules.documents.models import Document
from app.modules.documents.repository import DocumentRepo
from app.modules.documents.upload_document import upload_document
from app.shared.config import Settings, get_settings
from app.shared.deps import get_pdf_inspector
from tests.fakes import WaitingPdfInspector

THRESHOLDS = {
    "max_thai_percent": 50,
    "max_garbled_thai_percent": 5,
    "min_text_chars": 50,
    "max_image_percent": 80,
}


def pdf(pages=2, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    if encrypted:
        writer.encrypt("password")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture(autouse=True)
def inspector(client):
    client.app.dependency_overrides[get_pdf_inspector] = LocalPdfInspector


async def upload(client, name="ทดสอบ.pdf", content=None):
    return await client.post(
        "/documents",
        files={
            "file": (name, pdf() if content is None else content, "application/pdf")
        },
    )


async def test_upload_list_detail_and_exact_original(client, session):
    assert (await client.get("/documents")).json() == {"items": [], "total": 0}
    original = pdf(3)
    response = await upload(client, content=original)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["duration_ms"] >= 0
    doc = result["document"]
    assert doc["filename"] == "ทดสอบ.pdf"
    assert doc["page_count"] == 3 and doc["size_bytes"] == len(original)
    assert doc["quality_status"] == "checked" and doc["ocr_suggested_count"] == 3
    assert (await client.get("/documents")).json() == {"items": [doc], "total": 1}
    detail = (await client.get(f"/documents/{doc['id']}")).json()
    assert {k: v for k, v in detail.items() if k != "pages"} == doc
    assert len(detail["pages"]) == 3
    source = await client.get(f"/documents/{doc['id']}/original")
    assert source.content == original
    assert source.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in source.headers["content-disposition"]
    assert "original_pdf" not in doc
    await session.flush()


async def test_pagination_order_duplicates_and_deferred_pdf(client, session):
    a = (await upload(client)).json()["document"]
    b = (await upload(client)).json()["document"]
    assert a["id"] != b["id"]
    # Postgres now() is stable inside the test transaction. Set distinct times.
    from datetime import UTC, datetime, timedelta

    row = await session.get(Document, uuid.UUID(b["id"]))
    row.uploaded_at = datetime.now(UTC) + timedelta(seconds=1)
    await session.flush()
    session.expunge_all()
    repo = DocumentRepo(session)
    documents, total = await repo.list_documents(1, 1)
    assert total == 2 and str(documents[0].id) == b["id"]
    assert "original_pdf" not in documents[0].__dict__
    second = (await client.get("/documents?page=2&page_size=1")).json()
    assert second["items"][0]["id"] == a["id"] and second["total"] == 2
    assert (await client.get("/documents?page=3&page_size=1")).json() == {
        "items": [],
        "total": 2,
    }


@pytest.mark.parametrize(
    "query", ["page=0", "page=-1", "page=x", "page_size=0", "page_size=101"]
)
async def test_invalid_pagination(client, query):
    response = await client.get("/documents?" + query)
    assert response.status_code == 422 and response.json()["error_code"] == "REQ_001"


@pytest.mark.parametrize(
    "content,code",
    [
        (b"not a pdf", "DOC_001"),
        (b"%PDF-1.7\nbroken", "DOC_004"),
        (pdf(encrypted=True), "DOC_004"),
        (pdf(0), "DOC_004"),
    ],
    ids=["not-pdf", "corrupt", "encrypted", "zero-pages"],
)
async def test_invalid_pdf_does_not_save(client, content, code):
    response = await upload(client, content=content)
    assert response.status_code == 422
    assert response.json()["error_code"] == code
    assert (await client.get("/documents")).json()["total"] == 0


async def test_size_limit_and_exact_boundary(client):
    content = pdf()
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        documents_max_bytes=len(content)
    )
    assert (await upload(client, content=content)).status_code == 201
    response = await upload(client, content=content + b" ")
    assert response.status_code == 422 and response.json()["error_code"] == "DOC_002"
    assert (await client.get("/documents")).json()["total"] == 1


async def test_streaming_body_limit_without_content_length(client):
    async def chunks():
        for _ in range(22):
            yield b"x" * (1024 * 1024)

    response = await client.post(
        "/documents",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=abc"},
    )
    assert response.status_code == 422 and response.json()["error_code"] == "DOC_002"


async def test_multiple_missing_and_wrong_form_fields(client):
    response = await client.post(
        "/documents", files=[("file", ("a.pdf", pdf())), ("file", ("b.pdf", pdf()))]
    )
    assert response.status_code == 422 and response.json()["error_code"] == "DOC_003"
    for kwargs in (
        {},
        {"files": {"other": ("a.pdf", pdf())}},
        {"data": {"file": "string"}},
        {"content": b"invalid", "headers": {"Content-Type": "multipart/form-data"}},
    ):
        response = await client.post("/documents", **kwargs)
        assert (
            response.status_code == 422 and response.json()["error_code"] == "REQ_001"
        )
    assert (await client.get("/documents")).json()["total"] == 0


async def test_filename_is_display_name_only_and_content_overrides_mime(client):
    response = await client.post(
        "/documents", files={"file": ("../../ต้นฉบับ.pdf", pdf(), "text/plain")}
    )
    assert response.status_code == 201
    assert response.json()["document"]["filename"] == "ต้นฉบับ.pdf"


async def test_missing_document_and_original(client):
    for path in (f"/documents/{uuid.uuid4()}", f"/documents/{uuid.uuid4()}/original"):
        response = await client.get(path)
        assert (
            response.status_code == 404 and response.json()["error_code"] == "DOC_007"
        )


async def test_parser_timeout_does_not_save(client):
    client.app.dependency_overrides[get_settings] = lambda: Settings(
        documents_parse_timeout_seconds=0.000001
    )
    response = await upload(client)
    assert response.status_code == 422 and response.json()["error_code"] == "DOC_006"
    assert (await client.get("/documents")).json()["total"] == 0


async def test_cancellation_before_save(session):
    inspector = WaitingPdfInspector()
    task = asyncio.create_task(
        upload_document(
            "test.pdf",
            pdf(),
            DocumentRepo(session),
            inspector,
            1024 * 1024,
            1,
            THRESHOLDS,
        )
    )
    await inspector.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await session.scalars(select(Document))).all() == []


async def test_disconnect_stops_work_and_does_not_save(client):
    inspector = WaitingPdfInspector()
    client.app.dependency_overrides[get_pdf_inspector] = lambda: inspector
    request = httpx.Request(
        "POST", "http://test/documents", files={"file": ("a.pdf", pdf())}
    )
    content = request.read()
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": content, "more_body": False}
        await inspector.started.wait()
        return {"type": "http.disconnect"}

    messages = []

    async def send(message):
        messages.append(message)

    await asyncio.wait_for(
        client.app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/documents",
                "raw_path": b"/documents",
                "root_path": "",
                "query_string": b"",
                "headers": request.headers.raw,
                "server": ("test", 80),
                "client": ("test", 123),
            },
            receive,
            send,
        ),
        timeout=2,
    )
    assert (await client.get("/documents")).json()["total"] == 0


async def test_database_rolls_back_original_and_metadata_together(session):
    repo = DocumentRepo(session)
    with pytest.raises(RuntimeError):
        async with session.begin_nested():
            await upload_document(
                "test.pdf", pdf(), repo, LocalPdfInspector(), 1024 * 1024, 5, THRESHOLDS
            )
            raise RuntimeError("simulate transaction failure")
    assert (await repo.list_documents(1, 20)) == ([], 0)
