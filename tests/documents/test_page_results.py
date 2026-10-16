import io
import uuid

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from app.modules.documents.adapters.pdf_geometry import union_area
from app.modules.documents.adapters.pdf_inspector import LocalPdfInspector
from app.modules.documents.models import Document, DocumentPage
from app.modules.documents.rules import assess_quality
from app.shared.deps import get_pdf_inspector
from tests.documents.test_documents import THRESHOLDS, pdf, upload


def text_and_image_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    image = DecodedStreamObject()
    image.set_data(b"\xff\x00\x00")
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(1),
            NameObject("/Height"): NumberObject(1),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            ),
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Im"): writer._add_object(image)}
            ),
        }
    )
    content = DecodedStreamObject()
    # Two overlapping copies occupy exactly half the page, not the entire page.
    content.set_data(
        b"BT /F1 12 Tf 10 180 Td (Hello PDF) Tj ET q 200 0 0 100 0 0 cm /Im Do Q q 200 0 0 100 0 0 cm /Im Do Q"
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_quality_inclusive_boundaries_and_order():
    t = {
        "max_thai_percent": 50,
        "max_garbled_thai_percent": 0,
        "min_text_chars": 2,
        "max_image_percent": 80,
    }
    assert assess_quality("ก1", 80, t)["passed"]
    assert assess_quality(" A ", 81, t)["failed"] == [
        "min_text_chars",
        "max_image_percent",
    ]
    assert assess_quality("", 0, THRESHOLDS)["failed"] == ["min_text_chars"]
    assert assess_quality("กิ่", 0, THRESHOLDS)["garbled_thai_percent"] == 0
    assert assess_quality("ิกิิ\ufffd", 0, THRESHOLDS)["garbled_thai_percent"] == 80
    assert assess_quality("ก A\n", 0, THRESHOLDS)["text_chars"] == 2


def test_overlapping_image_rectangles_count_only_once():
    assert union_area([(0, 0, 100, 100), (50, 0, 150, 100)]) == 15000


async def test_actual_extraction_image_area_and_blank_page():
    pages = await LocalPdfInspector().extract_pages(text_and_image_pdf(), 10)
    assert pages[0]["text"] == "Hello PDF\n"
    assert pages[0]["image_percent"] == 50
    assert pages[1] == {"text": "", "image_percent": 0}


async def test_snapshot_persists_after_settings_change_and_has_per_page_results(
    client, session
):
    client.app.dependency_overrides[get_pdf_inspector] = LocalPdfInspector
    thresholds = THRESHOLDS | {"max_thai_percent": 0, "min_text_chars": 1}
    assert (
        await client.patch("/text-quality/thresholds", json=thresholds)
    ).status_code == 200
    doc = (await upload(client, content=text_and_image_pdf())).json()["document"]
    assert doc["ocr_suggested_count"] == 1
    detail = (await client.get(f"/documents/{doc['id']}")).json()
    assert detail["pages"] == [
        {"number": 1, "ocr_suggested": False, "has_ocr": False},
        {"number": 2, "ocr_suggested": True, "has_ocr": False},
    ]
    await client.patch(
        "/text-quality/thresholds", json=THRESHOLDS | {"max_image_percent": 49}
    )
    session.expunge_all()
    result = (await client.get(f"/documents/{doc['id']}/pages/1")).json()
    assert result["thresholds"] == thresholds
    assert result["parser"]["text"] == "Hello PDF\n"
    assert result["parser"]["quality"]["passed"]
    assert result["parser"]["quality"]["image_percent"] == 50
    assert result["ocr"] is None
    assert (
        await client.get(f"/documents/{doc['id']}/file")
    ).content == text_and_image_pdf()
    newer = (await upload(client, content=text_and_image_pdf())).json()["document"]
    assert newer["ocr_suggested_count"] == 2


async def test_missing_pages_document_invalid_paths_and_legacy(client, session):
    client.app.dependency_overrides[get_pdf_inspector] = LocalPdfInspector
    doc = (await upload(client, content=pdf())).json()["document"]
    for n in (0, -1, 3):
        r = await client.get(f"/documents/{doc['id']}/pages/{n}")
        assert r.status_code == 404 and r.json()["error_code"] == "DOC_008"
    r = await client.get(f"/documents/{uuid.uuid4()}/pages/1")
    assert r.status_code == 404 and r.json()["error_code"] == "DOC_007"
    for path in ("invalid/pages/1", f"{doc['id']}/pages/nope"):
        assert (await client.get("/documents/" + path)).status_code == 422
    legacy = Document(
        filename="legacy.pdf", original_pdf=pdf(), size_bytes=len(pdf()), page_count=2
    )
    session.add(legacy)
    await session.flush()
    r = (await client.get(f"/documents/{legacy.id}")).json()
    assert r["quality_status"] == "not_checked" and r["pages"] == []
    assert (await client.get(f"/documents/{legacy.id}/pages/1")).status_code == 404


async def test_page_results_roll_back_with_original(session):
    from sqlalchemy import select

    from app.modules.documents.repository import DocumentRepo
    from app.modules.documents.upload_document import upload_document

    with pytest.raises(RuntimeError):
        async with session.begin_nested():
            await upload_document(
                "a.pdf",
                text_and_image_pdf(),
                DocumentRepo(session),
                LocalPdfInspector(),
                1024 * 1024,
                10,
                THRESHOLDS,
            )
            raise RuntimeError("rollback")
    assert (await session.scalars(select(DocumentPage))).all() == []
    assert (await session.scalars(select(Document))).all() == []


@pytest.mark.parametrize(
    "count,snapshot", [(-1, THRESHOLDS), (3, THRESHOLDS), (0, None), (None, THRESHOLDS)]
)
async def test_database_rejects_inconsistent_assessment(session, count, snapshot):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                Document(
                    filename="a.pdf",
                    original_pdf=pdf(),
                    size_bytes=len(pdf()),
                    page_count=2,
                    thresholds=snapshot,
                    ocr_suggested_count=count,
                )
            )
            await session.flush()


@pytest.mark.parametrize(
    "first,expected,thai", [("0E20", "ภาษษา", 62.5), ("0000", "\ufffdาษษา", 50)]
)
async def test_extracts_thai_and_replaces_unstorable_nul(first, expected, thai):
    from pypdf import PdfReader

    writer = PdfWriter()
    reader = PdfReader(io.BytesIO(text_and_image_pdf()))
    writer.append(reader)
    font = writer.pages[0]["/Resources"]["/Font"]["/F1"].get_object()
    mapping = DecodedStreamObject()
    mapping.set_data(
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Thai def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 4 beginbfchar <48> <0E20> <65> <0E32> <6C> <0E29> <6F> <0E32> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    mapping.set_data(
        mapping.get_data().replace(b"<48> <0E20>", f"<48> <{first}>".encode())
    )
    font[NameObject("/ToUnicode")] = writer._add_object(mapping)
    out = io.BytesIO()
    writer.write(out)
    pages = await LocalPdfInspector().extract_pages(out.getvalue(), 10)
    assert pages[0]["text"].startswith(expected)
    assert "\x00" not in pages[0]["text"]
    assert assess_quality(pages[0]["text"], 0, THRESHOLDS)["thai_percent"] == thai


@pytest.mark.parametrize(
    "text,image_percent,changes,failed",
    [
        ("กก1", 0, {"max_thai_percent": 50}, ["max_thai_percent"]),
        ("ทีC เชืMอ", 0, {"max_garbled_thai_percent": 24}, ["max_garbled_thai_percent"]),
        ("abc", 81, {"max_image_percent": 80}, ["max_image_percent"]),
        ("abc", 0, {"min_text_chars": 4}, ["min_text_chars"]),
        (
            "ก1",
            80,
            {"max_thai_percent": 50, "min_text_chars": 2, "max_image_percent": 80},
            [],
        ),
        ("ทีC เชืMอ", 0, {"max_garbled_thai_percent": 25}, []),
    ],
)
async def test_any_single_failed_rule_is_persisted_as_an_ocr_suggestion(
    client, text, image_percent, changes, failed
):
    from tests.fakes import ExtractedTextPdfInspector

    thresholds = {
        "max_thai_percent": 100,
        "max_garbled_thai_percent": 100,
        "min_text_chars": 0,
        "max_image_percent": 100,
    } | changes
    await client.patch("/text-quality/thresholds", json=thresholds)
    client.app.dependency_overrides[get_pdf_inspector] = lambda: (
        ExtractedTextPdfInspector(text, image_percent)
    )
    response = await upload(client)
    assert response.status_code == 201, response.text
    doc = response.json()["document"]
    assert doc["ocr_suggested_count"] == int(bool(failed))
    page = (await client.get(f"/documents/{doc['id']}/pages/1")).json()
    assert page["thresholds"] == thresholds
    assert page["parser"]["text"] == text
    assert page["parser"]["quality"]["failed"] == failed
    detail = (await client.get(f"/documents/{doc['id']}")).json()
    assert detail["pages"][0]["ocr_suggested"] is bool(failed)
    assert "text_passed" not in detail["pages"][0]


async def test_existing_minimum_thai_snapshot_and_results_are_returned_unchanged(
    client, session
):
    old_thresholds = {
        "min_thai_percent": 50,
        "max_garbled_thai_percent": 5,
        "min_text_chars": 1,
        "max_image_percent": 80,
    }
    old_quality = {
        "thai_percent": 38,
        "garbled_thai_percent": 0,
        "text_chars": 8,
        "image_percent": 0,
        "failed": ["min_thai_percent"],
        "passed": False,
    }
    doc = Document(
        filename="historical.pdf",
        page_count=1,
        original_pdf=pdf(1),
        size_bytes=len(pdf(1)),
        thresholds=old_thresholds,
        ocr_suggested_count=1,
    )
    session.add(doc)
    await session.flush()
    session.add(
        DocumentPage(document_id=doc.id, number=1, text="original", quality=old_quality)
    )
    await session.flush()
    await client.patch("/text-quality/thresholds", json={"max_thai_percent": 10})
    session.expunge_all()
    result = (await client.get(f"/documents/{doc.id}/pages/1")).json()
    assert result["thresholds"] == old_thresholds
    assert result["parser"]["quality"] == old_quality
    assert (await client.get(f"/documents/{doc.id}")).json()["ocr_suggested_count"] == 1
