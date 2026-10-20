"""Actual ocr-document-pages-v3 entry point through production composition.

Real files, pypdfium2 and HTTP client; only the provider is a synthetic loopback double.
"""

from io import BytesIO
import json

from pypdf import PdfWriter
import pytest

from contexts.document_processing.v3.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v3.infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from contexts.document_processing.v3.presentation.ocr_document_pages_cli import main

from .conftest import completion

KEY = "synthetic-cli-key"
TEXT = "ข้อความลับจากภาพ"


def three_page_pdf():
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=100)
    with BytesIO() as buffer:
        writer.write(buffer)
        return buffer.getvalue()


@pytest.fixture
def cli(tmp_path, ocr_provider):
    root = tmp_path / "documents"
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, ""), SourcePage(2, "อ่านได้ปกติ"), SourcePage(3, "")), threshold_percent=20,
    )
    document_id = LocalJsonExtractionStore(root).save(document, pdf=three_page_pdf()).document_id
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "presets": [{"name": "mfec", "endpoint": ocr_provider.endpoint, "model": "vision-model", "api_key": KEY}],
        "unreadable_threshold_percent": 60,
    }))
    config.chmod(0o600)
    ocr_provider.replies = [
        completion(json.dumps({"outcome": "text", "text": TEXT})),
        completion(json.dumps({"outcome": "unreadable"})),
    ]

    def invoke(*extra, document=document_id, preset="mfec"):
        return main([document, "--preset", preset, "--config", str(config), "--data-dir", str(root), *extra])
    return invoke, root, document_id, config


def outputs(capsys):
    captured = capsys.readouterr()
    return captured.out, captured.err


def test_suggested_pages_are_ocred_saved_and_summarized_without_printing_text(cli, ocr_provider, capsys):
    invoke, root, document_id, _ = cli
    extraction_before = (root / document_id / "extraction.json").read_bytes()

    assert invoke() == 0

    out, err = outputs(capsys)
    assert err == ""
    result = json.loads(out)
    attempt_file = root / document_id / "ocr" / f"{result['attempt_id']}.json"
    assert result == {
        "outcome": "saved", "document_id": document_id, "attempt_id": result["attempt_id"],
        "summary": {"pages": [1, 3], "extracted": [1], "unreadable": [3], "ocr_unavailable": []},
        "files": {"ocr_attempt_json": str(attempt_file.absolute())},
    }
    assert TEXT not in out and KEY not in out
    saved = json.loads(attempt_file.read_text())
    assert [(page["number"], page["status"], page["text"]) for page in saved["pages"]] == [
        (1, "extracted", TEXT), (3, "unreadable", None),
    ]
    assert KEY not in attempt_file.read_text()
    assert [headers["Authorization"] for _, headers, _ in ocr_provider.requests] == [f"Bearer {KEY}"] * 2
    assert all(body["model"] == "vision-model" for _, _, body in ocr_provider.requests)
    assert (root / document_id / "extraction.json").read_bytes() == extraction_before


def test_explicit_pages_include_an_unsuggested_page(cli, ocr_provider, capsys):
    invoke, root, document_id, _ = cli

    assert invoke("--pages", "2") == 0

    result = json.loads(outputs(capsys)[0])
    assert result["summary"] == {"pages": [2], "extracted": [2], "unreadable": [], "ocr_unavailable": []}
    saved = json.loads((root / document_id / "ocr" / f"{result['attempt_id']}.json").read_text())
    assert [(page["number"], page["was_suggested"]) for page in saved["pages"]] == [(2, False)]
    assert len(ocr_provider.requests) == 1


def test_provider_outage_still_saves_an_attempt_with_unavailable_pages(cli, ocr_provider, capsys):
    invoke, root, document_id, _ = cli
    ocr_provider.status = 503

    assert invoke() == 0

    result = json.loads(outputs(capsys)[0])
    assert result["summary"] == {"pages": [1, 3], "extracted": [], "unreadable": [], "ocr_unavailable": [1, 3]}
    assert (root / document_id / "ocr" / f"{result['attempt_id']}.json").exists()


@pytest.mark.parametrize("arguments,code", [
    ({"preset": "unknown"}, "invalid_preset"),
    ({"document": "f" * 32}, "document_not_found"),
    ({"document": "../outside"}, "document_not_found"),
    ({"extra": ("--pages", "9")}, "page_not_found"),
    ({"extra": ("--pages", "1,1")}, "duplicate_page"),
    ({"extra": ("--pages", "")}, "no_pages_selected"),
])
def test_rejections_are_reported_without_ocr_or_storage(cli, ocr_provider, capsys, arguments, code):
    invoke, root, document_id, _ = cli

    assert invoke(*arguments.get("extra", ()), **{k: v for k, v in arguments.items() if k != "extra"}) == 2

    out, err = outputs(capsys)
    assert json.loads(out) == {"outcome": "rejected", "code": code}
    assert err == ""
    assert ocr_provider.requests == []
    assert not (root / document_id / "ocr").exists()


def system_failure(cli, failure):
    _, root, document_id, config = cli
    if failure == "missing_api_key":
        data = json.loads(config.read_text())
        del data["presets"][0]["api_key"]
        config.write_text(json.dumps(data))
    elif failure == "presets_not_list":
        config.write_text(json.dumps({"presets": {"name": "mfec"}}))
    elif failure == "shared_config":
        config.chmod(0o644)
    elif failure == "corrupt_document":
        (root / document_id / "extraction.json").write_text("{")
    elif failure == "storage":
        (root / document_id / "ocr").mkdir(mode=0o700)
        (root / document_id / "ocr").chmod(0o500)


@pytest.mark.parametrize("failure,provider_called", [
    ("missing_api_key", False), ("presets_not_list", False), ("shared_config", False),
    ("corrupt_document", False), ("storage", True),
])
def test_system_failures_are_safe_errors_without_false_success(cli, ocr_provider, capsys, failure, provider_called):
    invoke, root, document_id, _ = cli
    system_failure(cli, failure)

    assert invoke() == 1

    out, err = outputs(capsys)
    assert out == ""
    assert json.loads(err) == {"outcome": "error", "code": "system_error"}
    assert KEY not in err and TEXT not in err
    assert bool(ocr_provider.requests) is provider_called
    if failure == "storage":
        (root / document_id / "ocr").chmod(0o700)
        assert list((root / document_id / "ocr").iterdir()) == []


@pytest.mark.parametrize("pages", ["a", "1,,2", "1.5", "-"])
def test_malformed_page_list_is_a_usage_error_before_any_effect(cli, ocr_provider, capsys, pages):
    invoke, *_ = cli

    with pytest.raises(SystemExit) as caught:
        invoke("--pages", pages)

    assert caught.value.code == 2
    assert outputs(capsys)[0] == ""
    assert ocr_provider.requests == []
