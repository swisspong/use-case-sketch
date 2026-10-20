import asyncio
import json
import uuid

import httpx
import pytest

from app.modules.documents.adapters.openai_ocr import (
    LAYOUT_PROMPT,
    MARK_PROMPT,
    PROMPT,
    OpenAIOcrReader,
)
from app.modules.documents.adapters.page_renderer import LocalPageRenderer
from app.modules.documents.errors import (
    DocumentNotFound,
    NoDefaultPreset,
    OcrPresetNotFound,
    PageNotFound,
    PageOutOfRange,
    PageRenderFailed,
)
from app.modules.documents.models import Document
from app.modules.documents.ocr_page import OcrIn, ocr_page
from app.modules.documents.ports import OcrReading
from app.modules.documents.repository import DocumentRepo
from app.modules.documents.rules import assess_quality
from app.modules.llm_config.credentials import PresetCredential, SavedPresetCredentials
from app.modules.llm_config.crypto import ApiKeyCipher
from app.modules.llm_config.repository import PresetRepo
from app.shared.config import get_settings
from app.shared.deps import (
    get_document_uow,
    get_ocr_presets,
    get_ocr_reader,
    get_page_renderer,
)
from tests.documents.test_documents import THRESHOLDS, pdf
from tests.documents.test_page_results import text_and_image_pdf
from tests.fakes import FakeOcrReader, FakePageRenderer
from tests.helpers import page, words
from tests.settings.test_presets import DATA, create

# Parser fails on page 2 (empty); a 3-character Latin OCR text passes these thresholds.
SNAPSHOT = THRESHOLDS | {"min_text_chars": 3}
CIPHER = ApiKeyCipher(get_settings().llm_config_api_key_secret)
GOOD = OcrReading(text="Hello OCR")


async def seed(session, texts=("parser text", ""), image_percent=12.5):
    repo = DocumentRepo(session)
    pages = [
        {"text": t, "quality": assess_quality(t, image_percent, SNAPSHOT)}
        for t in texts
    ]
    document = await repo.add(
        Document(
            filename="a.pdf",
            size_bytes=len(pdf(len(texts))),
            page_count=len(texts),
            original_pdf=pdf(len(texts)),
            thresholds=SNAPSHOT,
            ocr_suggested_count=sum(not p["quality"]["passed"] for p in pages),
        )
    )
    await repo.add_pages(document.id, pages)
    return document


@pytest.fixture
def presets(uow):
    return SavedPresetCredentials(uow(PresetRepo), CIPHER)


async def run(session, uow, presets, document_id, page=2, preset_id=None, reader=None):
    reader = reader or FakeOcrReader()
    renderer = FakePageRenderer()
    result = await ocr_page(
        document_id,
        OcrIn(page=page, preset_id=preset_id),
        uow(DocumentRepo),
        presets,
        renderer,
        reader,
    )
    return result, renderer, reader


# ---- L2: legacy snapshots keep the minimum-Thai direction when OCR text is assessed ----
def test_legacy_minimum_thai_snapshot_is_assessed_with_its_original_direction():
    legacy = {k: v for k, v in SNAPSHOT.items() if k != "max_thai_percent"}
    legacy["min_thai_percent"] = 50
    assert assess_quality("abc", 0, legacy)["failed"] == ["min_thai_percent"]
    assert assess_quality("กขค", 0, legacy)["passed"]


# ---- L3: handler + real DB + fake provider ports ----
async def test_success_saves_latest_ocr_and_updates_page_summary(
    client, session, uow, presets
):
    preset = await create(client)
    doc = await seed(session)
    in_tx = []
    reader = FakeOcrReader(
        GOOD, before_call=lambda: in_tx.append(session.in_nested_transaction())
    )
    result, renderer, reader = await run(session, uow, presets, doc.id, reader=reader)
    assert in_tx == [False]  # provider is never called inside a DB transaction
    assert renderer.calls == [2]
    assert reader.calls[0]["preset"] == PresetCredential(
        name=DATA["name"],
        model_id=DATA["model_id"],
        base_url="https://provider.example/v1",
        api_key=DATA["api_key"],
    )
    assert result.status == "ok" and result.page == 2
    assert "text_passed" not in result.model_dump()
    assert result.ocr.preset_name == DATA["name"] and result.ocr.model_id == "model"
    assert result.ocr.text == "Hello OCR"
    # Same snapshot and the parser's image coverage: OCR only changes the text.
    assert result.ocr.quality.model_dump() == assess_quality(
        "Hello OCR", 12.5, SNAPSHOT
    )
    assert result.duration_ms >= 0
    page = (await client.get(f"/documents/{doc.id}/pages/2")).json()
    assert (
        page["ocr"]["text"] == "Hello OCR" and page["ocr"]["preset_name"] == "GPT mini"
    )
    assert page["parser"]["text"] == "" and not page["parser"]["quality"]["passed"]
    detail = (await client.get(f"/documents/{doc.id}")).json()
    assert detail["pages"][1] == {"number": 2, "ocr_suggested": True, "has_ocr": True}
    # The OCR'd page no longer needs OCR, whatever the OCR text scores.
    assert detail["ocr_suggested_count"] == 0
    assert preset["is_default"]


async def test_rerun_replaces_result_and_failure_keeps_previous(
    client, session, uow, presets
):
    await create(client)
    doc = await seed(session)
    await run(session, uow, presets, doc.id)
    poor = OcrReading(text="x")
    result, *_ = await run(session, uow, presets, doc.id, reader=FakeOcrReader(poor))
    assert result.status == "ok"
    assert result.ocr.quality.failed == ["min_text_chars"]  # shown, never judged
    failed = OcrReading(reason="provider_timeout")
    result, *_ = await run(session, uow, presets, doc.id, reader=FakeOcrReader(failed))
    assert result.status == "failed" and result.reason == "provider_timeout"
    assert result.ocr is None
    page = (await client.get(f"/documents/{doc.id}/pages/2")).json()
    assert page["ocr"]["text"] == "x"
    detail = (await client.get(f"/documents/{doc.id}")).json()
    assert detail["pages"][1]["has_ocr"]
    assert detail["ocr_suggested_count"] == 0  # reruns never count a page twice


async def test_each_ocr_logs_one_traceable_line(client, session, uow, presets, caplog):
    await create(client)
    doc = await seed(session)
    caplog.set_level("INFO", logger="app.modules.documents.ocr_page")
    clean = OcrReading(text="Hello OCR", steps=("pass1 ok", "pass2 accepted"))
    skipped = OcrReading(
        text="Hello OCR",
        steps=("pass1 ok", "pass2 accepted", "marks deadline (15+11 boxes)"),
        degraded=True,
    )
    failed = OcrReading(reason="invalid_output", steps=("pass1 invalid_output",))
    for reading in (clean, skipped, failed):
        await run(session, uow, presets, doc.id, reader=FakeOcrReader(reading))
    records = [r for r in caplog.records if r.name == "app.modules.documents.ocr_page"]
    assert [r.levelname for r in records] == ["INFO", "WARNING", "WARNING"]
    lines = [r.getMessage() for r in records]
    assert all(f"document={doc.id} page=2 preset=" in line for line in lines)
    assert "ok" in lines[1] and "marks deadline (15+11 boxes)" in lines[1]
    assert "failed" in lines[2] and "pass1 invalid_output" in lines[2]


async def test_ocr_of_a_passing_parser_page_leaves_the_suggested_count(
    client, session, uow, presets
):
    await create(client)
    doc = await seed(session)
    result, *_ = await run(
        session, uow, presets, doc.id, page=1, reader=FakeOcrReader(OcrReading(text=""))
    )
    assert result.status == "ok"
    detail = (await client.get(f"/documents/{doc.id}")).json()
    assert detail["ocr_suggested_count"] == 1
    assert detail["pages"][0] == {"number": 1, "ocr_suggested": False, "has_ocr": True}


async def test_failed_ocr_leaves_the_suggested_count(client, session, uow, presets):
    await create(client)
    doc = await seed(session)
    failed = OcrReading(reason="provider_error")
    await run(session, uow, presets, doc.id, reader=FakeOcrReader(failed))
    detail = (await client.get(f"/documents/{doc.id}")).json()
    assert detail["ocr_suggested_count"] == 1 and not detail["pages"][1]["has_ocr"]


async def test_suggested_count_drops_once_per_ocr_page(client, session, uow, presets):
    await create(client)
    doc = await seed(session, texts=("", "", ""))
    for page, left in ((1, 2), (1, 2), (3, 1)):
        await run(session, uow, presets, doc.id, page=page)
        detail = (await client.get(f"/documents/{doc.id}")).json()
        assert detail["ocr_suggested_count"] == left


async def test_explicit_preset_is_used_and_default_is_resolved(
    client, session, uow, presets
):
    await create(client)
    other = await create(client, name="Other", model_id="other-model")
    doc = await seed(session)
    _, _, reader = await run(
        session, uow, presets, doc.id, preset_id=uuid.UUID(other["id"])
    )
    assert reader.calls[0]["preset"].model_id == "other-model"
    result, *_ = await run(session, uow, presets, doc.id)
    assert result.ocr.preset_name == DATA["name"]


@pytest.mark.parametrize(
    "case,error",
    [
        ("missing_document", DocumentNotFound),
        ("page_zero", PageOutOfRange),
        ("page_too_large", PageOutOfRange),
        ("no_default", NoDefaultPreset),
        ("unknown_preset", OcrPresetNotFound),
        ("unassessed_legacy", PageNotFound),
    ],
)
async def test_rejections_happen_before_rendering_or_provider(
    client, session, uow, presets, case, error
):
    if case != "no_default":
        await create(client)
    doc = await seed(session)
    document_id, page, preset_id = doc.id, 2, None
    if case == "missing_document":
        document_id = uuid.uuid4()
    elif case == "page_zero":
        page = 0
    elif case == "page_too_large":
        page = 3
    elif case == "unknown_preset":
        preset_id = uuid.uuid4()
    elif case == "unassessed_legacy":
        legacy = await DocumentRepo(session).add(
            Document(
                filename="l.pdf",
                size_bytes=len(pdf()),
                page_count=2,
                original_pdf=pdf(),
            )
        )
        document_id = legacy.id
    reader, renderer = FakeOcrReader(), FakePageRenderer()
    with pytest.raises(error):
        await ocr_page(
            document_id,
            OcrIn(page=page, preset_id=preset_id),
            uow(DocumentRepo),
            presets,
            renderer,
            reader,
        )
    assert reader.calls == [] and renderer.calls == []


# ---- endpoint: wiring + error mapping ----
@pytest.fixture
def ocr_client(client, uow):
    reader, renderer = FakeOcrReader(), FakePageRenderer()
    overrides = client.app.dependency_overrides
    overrides[get_document_uow] = lambda: uow(DocumentRepo)
    overrides[get_ocr_presets] = lambda: SavedPresetCredentials(uow(PresetRepo), CIPHER)
    overrides[get_ocr_reader] = lambda: reader
    overrides[get_page_renderer] = lambda: renderer
    client.reader = reader
    return client


async def test_endpoint_success_and_failed_bodies(ocr_client, session):
    preset = await create(ocr_client)
    doc = await seed(session)
    r = await ocr_client.post(
        f"/documents/{doc.id}/ocr", json={"page": 2, "preset_id": preset["id"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"page", "status", "ocr", "duration_ms"}
    assert body["status"] == "ok"
    assert set(body["ocr"]) == {
        "preset_name",
        "model_id",
        "created_at",
        "text",
        "quality",
    }
    ocr_client.reader.readings = [OcrReading(reason="invalid_output")]
    r = await ocr_client.post(f"/documents/{doc.id}/ocr", json={"page": 2})
    assert r.status_code == 200
    assert set(r.json()) == {"page", "status", "reason", "duration_ms"}
    assert r.json()["reason"] == "invalid_output"


async def test_endpoint_maps_errors(ocr_client, session):
    doc = await seed(session)
    url = f"/documents/{doc.id}/ocr"
    r = await ocr_client.post(url, json={"page": 1})
    assert (r.status_code, r.json()) == (
        409,
        {"code": "no_default_preset", "error_code": "DOC_012"},
    )
    await create(ocr_client)
    r = await ocr_client.post(url, json={"page": 1, "preset_id": str(uuid.uuid4())})
    assert (r.status_code, r.json()["error_code"]) == (404, "DOC_013")
    r = await ocr_client.post(url, json={"page": 3})
    assert (r.status_code, r.json()) == (
        422,
        {"code": "page_out_of_range", "error_code": "DOC_009"},
    )
    r = await ocr_client.post(f"/documents/{uuid.uuid4()}/ocr", json={"page": 1})
    assert (r.status_code, r.json()["error_code"]) == (404, "DOC_007")
    for body in ({}, {"page": "1"}, {"page": 1.5}, {"page": 1, "preset_id": "x"}):
        r = await ocr_client.post(url, json=body)
        assert (r.status_code, r.json()["error_code"]) == (422, "REQ_001"), body
    r = await ocr_client.post("/documents/nope/ocr", json={"page": 1})
    assert r.status_code == 422


# ---- llm_config public credential lookup ----
async def test_saved_credentials_decrypt_and_resolve_default(client, uow):
    a = await create(client)
    b = await create(client, name="B", api_key="other-key")
    credentials = SavedPresetCredentials(uow(PresetRepo), CIPHER)
    assert (await credentials.default()).name == DATA["name"]
    assert (await credentials.get(uuid.UUID(b["id"]))).api_key == "other-key"
    assert await credentials.get(uuid.uuid4()) is None
    assert "other-key" not in repr(await credentials.get(uuid.UUID(b["id"])))
    assert a["is_default"]


# ---- adapters ----
def completion(content, finish_reason="stop"):
    return {
        "choices": [
            {
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ]
    }


PRESET = PresetCredential(
    name="P",
    model_id="vision",
    base_url="https://provider.example/v1",
    api_key="secret",
)


@pytest.mark.parametrize(
    "respond,expected",
    [
        (
            lambda r: httpx.Response(200, json=completion("ข้อความ\nบรรทัด")),
            OcrReading(text="ข้อความ\nบรรทัด"),
        ),
        (lambda r: httpx.Response(200, json=completion("   ")), OcrReading(text="")),
        (lambda r: httpx.Response(503, json={}), OcrReading(reason="provider_error")),
        (lambda r: httpx.Response(401, json={}), OcrReading(reason="provider_error")),
        (
            lambda r: httpx.Response(200, text="<html>"),
            OcrReading(reason="invalid_output"),
        ),
        (
            lambda r: httpx.Response(200, json={"choices": []}),
            OcrReading(reason="invalid_output"),
        ),
        (
            lambda r: httpx.Response(200, json=completion("cut", "length")),
            OcrReading(reason="invalid_output"),
        ),
        (
            lambda r: httpx.Response(200, json=completion(None)),
            OcrReading(reason="invalid_output"),
        ),
    ],
)
async def test_ocr_adapter_translates_provider_responses(respond, expected):
    calls = []

    def handler(request):
        calls.append(request)
        return respond(request)

    reader = OpenAIOcrReader(timeout=5, transport=httpx.MockTransport(handler))
    try:
        assert await reader.read(b"\x89PNG", PRESET) == expected
    finally:
        await reader.aclose()
    # Sync, user-retried action: no automatic retries. Only non-empty text gets pass 2.
    assert len(calls) == (2 if expected.text else 1)
    for request in calls:
        assert str(request.url) == "https://provider.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "vision"
        assert body["max_tokens"] == 16384  # reasoning + a dense page fit
        image = body["messages"][-1]["content"][-1]["image_url"]["url"]
        assert image.startswith("data:image/png;base64,")


async def test_ocr_adapter_timeout_and_network_errors():
    async def slow(request):
        import asyncio

        await asyncio.sleep(1)
        return httpx.Response(200, json=completion("late"))

    def broken(request):
        raise httpx.ConnectError("secret details", request=request)

    for handler, reason in ((slow, "provider_timeout"), (broken, "provider_error")):
        reader = OpenAIOcrReader(timeout=0.05, transport=httpx.MockTransport(handler))
        try:
            assert await reader.read(b"png", PRESET) == OcrReading(reason=reason)
        finally:
            await reader.aclose()


PLAIN_PAGE = "วาระที่\nมติที่ประชุม/ข้อสั่งการ\nฝ่ายเลขานุการ\n๑.๑ ด้านการเกษตร ๗๒.๙๐"
TABLE_PAGE = (
    "มติที่ประชุม/ข้อสั่งการ: ฝ่ายเลขานุการ\n\n| ๑.๑ ด้านการเกษตร | ๗๒.๙๐ |\n| --- | --- |"
)


def two_pass(second):
    """Pass 1 answers PLAIN_PAGE; pass 2 (the layout prompt) answers via `second`."""
    calls = []

    async def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if body["messages"][0]["content"] == PROMPT:
            return httpx.Response(200, json=completion(PLAIN_PAGE))
        return await second(request)

    return calls, handler


def answer(content, status=200, finish_reason="stop"):
    async def respond(request):
        return httpx.Response(status, json=completion(content, finish_reason))

    return respond


async def slow(request):
    await asyncio.sleep(1)
    return httpx.Response(200, json=completion(TABLE_PAGE))


async def broken(request):
    raise httpx.ConnectError("secret details", request=request)


@pytest.mark.parametrize(
    "second,expected",
    [
        (answer(TABLE_PAGE), TABLE_PAGE),
        # Low reasoning effort can drop the separator row: it is put back.
        (answer(TABLE_PAGE.replace("\n| --- | --- |", "")), TABLE_PAGE),
        # An empty label for a column header is removed; the text is unchanged.
        (answer("มติที่ประชุม/ข้อสั่งการ:\n" + TABLE_PAGE), TABLE_PAGE),
        # Structuring changed a digit (seen with real models): keep the transcription.
        (answer(TABLE_PAGE.replace("๗๒", "๓๒")), PLAIN_PAGE),
        (answer(TABLE_PAGE + "<br>"), PLAIN_PAGE),
        (answer(None, status=503), PLAIN_PAGE),
        (answer("| cut", finish_reason="length"), PLAIN_PAGE),
        (answer(None), PLAIN_PAGE),
        (broken, PLAIN_PAGE),
        (slow, PLAIN_PAGE),  # pass 2 shares the total deadline
    ],
)
async def test_ocr_adapter_structures_tables_only_when_text_is_unchanged(
    second, expected
):
    calls, handler = two_pass(second)
    reader = OpenAIOcrReader(timeout=0.5, transport=httpx.MockTransport(handler))
    try:
        assert await reader.read(b"\x89PNG", PRESET) == OcrReading(text=expected)
    finally:
        await reader.aclose()
    assert len(calls) == 2
    assert "reasoning_effort" not in calls[0]  # transcription keeps the model default
    assert calls[1]["reasoning_effort"] == "low"
    layout = calls[1]["messages"]
    assert layout[0]["content"] == LAYOUT_PROMPT
    assert layout[1]["content"][0]["text"] == "Transcription:\n" + PLAIN_PAGE
    assert (
        layout[1]["content"][1] == calls[0]["messages"][1]["content"][1]
    )  # same image


async def test_ocr_adapter_flattens_pass_one_markup_before_structuring():
    markup = "| วาระที่ | มติที่ประชุม/ข้อสั่งการ |<br>|---|---|<br>| | ฝ่ายเลขานุการ |"
    flat = "วาระที่\nมติที่ประชุม/ข้อสั่งการ\nฝ่ายเลขานุการ"
    calls = []

    async def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if body["messages"][0]["content"] == PROMPT:
            return httpx.Response(200, json=completion(markup))
        return httpx.Response(503, json={})

    reader = OpenAIOcrReader(timeout=5, transport=httpx.MockTransport(handler))
    try:
        # Pass 2 failed, so the fallback is the flattened transcription, not the markup.
        assert await reader.read(b"\x89PNG", PRESET) == OcrReading(text=flat)
    finally:
        await reader.aclose()
    assert calls[1]["messages"][1]["content"][0]["text"] == "Transcription:\n" + flat


def struck_page(draw):
    right = words(draw, 100, 200, 12)
    draw.rectangle([100, 209, right, 211], fill=0)


@pytest.mark.parametrize(
    "reply,expected",
    [
        (
            "~~วาระที่~~" + PLAIN_PAGE.removeprefix("วาระที่"),
            "~~วาระที่~~" + PLAIN_PAGE.removeprefix("วาระที่"),
        ),
        (PLAIN_PAGE, PLAIN_PAGE),  # the detected line was not marked: nothing is
        ("~~วาระที่~~ ++มติ++", PLAIN_PAGE),  # text changed: marks discarded
    ],
)
async def test_ocr_adapter_marks_struck_text_only_when_lines_are_found(reply, expected):
    calls = []

    async def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        system = body["messages"][0]["content"]
        if system == PROMPT:
            return httpx.Response(200, json=completion(PLAIN_PAGE))
        if system == LAYOUT_PROMPT:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=completion(reply))

    reader = OpenAIOcrReader(timeout=5, transport=httpx.MockTransport(handler))
    try:
        assert await reader.read(page(struck_page), PRESET) == OcrReading(text=expected)
    finally:
        await reader.aclose()
    mark = calls[2]
    assert mark["messages"][0]["content"] == MARK_PROMPT.format(struck=1, underlined=0)
    assert mark["reasoning_effort"] == "low"
    boxed = mark["messages"][1]["content"][1]["image_url"]["url"]
    assert boxed != calls[0]["messages"][1]["content"][1]["image_url"]["url"]


@pytest.mark.parametrize(
    "second,steps,degraded",
    [
        (answer(TABLE_PAGE), ("pass1 ok", "pass2 accepted", "marks none found"), False),
        (
            answer(None, status=503),
            ("pass1 ok", "pass2 provider_error", "marks none found"),
            True,
        ),
        (slow, ("pass1 ok", "pass2 deadline", "marks none found"), True),
        (
            answer(TABLE_PAGE.replace("๗๒", "๓๒")),
            ("pass1 ok", "pass2 rejected", "marks none found"),
            True,
        ),
    ],
)
async def test_ocr_adapter_reports_what_each_pass_did(second, steps, degraded):
    _, handler = two_pass(second)
    reader = OpenAIOcrReader(timeout=0.5, transport=httpx.MockTransport(handler))
    try:
        reading = await reader.read(b"\x89PNG", PRESET)
    finally:
        await reader.aclose()
    assert (reading.steps, reading.degraded) == (steps, degraded)


async def test_ocr_adapter_reports_pass_one_failure_and_edit_mark_outcomes():
    def broken_pass_one(request):
        return httpx.Response(200, json=completion("cut", "length"))

    reader = OpenAIOcrReader(timeout=5, transport=httpx.MockTransport(broken_pass_one))
    try:
        reading = await reader.read(b"\x89PNG", PRESET)
    finally:
        await reader.aclose()
    assert reading.steps == ("pass1 invalid_output",) and reading.degraded

    for reply, step, degraded in (
        (
            "~~วาระที่~~" + PLAIN_PAGE.removeprefix("วาระที่"),
            "marks applied (1+0 runs in 1+0 boxes)",
            False,
        ),
        (PLAIN_PAGE, "marks rejected (0+0 pairs marked; 1+0 runs in 1+0 boxes)", True),
    ):

        async def handler(request, reply=reply):
            system = json.loads(request.content)["messages"][0]["content"]
            if system == PROMPT:
                return httpx.Response(200, json=completion(PLAIN_PAGE))
            if system == LAYOUT_PROMPT:
                return httpx.Response(200, json=completion(PLAIN_PAGE))
            return httpx.Response(200, json=completion(reply))

        reader = OpenAIOcrReader(timeout=5, transport=httpx.MockTransport(handler))
        try:
            reading = await reader.read(page(struck_page), PRESET)
        finally:
            await reader.aclose()
        assert reading.steps == ("pass1 ok", "pass2 accepted", step)
        assert reading.degraded is degraded


async def test_page_renderer_renders_requested_page_as_png():
    renderer = LocalPageRenderer(timeout=20)
    image = await renderer.render_png(text_and_image_pdf(), 2)
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    for content, number in ((b"%PDF-broken", 1), (text_and_image_pdf(), 3)):
        with pytest.raises(PageRenderFailed):
            await renderer.render_png(content, number)
