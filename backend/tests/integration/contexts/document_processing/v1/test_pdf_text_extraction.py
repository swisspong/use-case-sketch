"""Exercise the parser's public port with actual PDF bytes, not a parser mock."""

from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import distribution
from io import BytesIO
from pathlib import Path
import json
import subprocess
import sys

import pytest

from pypdf import PageObject, PdfWriter
from pypdf.errors import DependencyError, LimitReachedError

from contexts.document_processing.v1.application.use_cases.extract_pdf_text.errors import PdfExtractionError
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject,
)

from contexts.document_processing.v1.application.use_cases.extract_pdf_text.ports import ParsedPdf, PdfRejected
from contexts.document_processing.v1.domain.documents.extraction import SourcePage
from contexts.document_processing.v1.infrastructure.pypdf_text_extractor import PypdfTextExtractor
from contexts.document_processing.v1.presentation.extract_pdf_text_cli import main


def make_pdf(*, encrypted=False, texts=("First page", "", "Third page")):
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        if text:
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            })
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 20 250 Td ({text}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("private-password")
    with BytesIO() as buffer:
        writer.write(buffer)
        return buffer.getvalue()


def test_all_pages_are_returned_in_source_order_including_blank_pages():
    assert PypdfTextExtractor().extract(make_pdf()) == ParsedPdf((
        SourcePage(1, "First page"),
        SourcePage(2, ""),
        SourcePage(3, "Third page"),
    ))


@pytest.mark.parametrize("pdf", [b"", b"not a PDF", b"\xff\xfe\x00binary", b"%PDF-1.7\ntruncated"])
def test_malformed_pdf_is_a_declared_rejection(pdf):
    assert PypdfTextExtractor().extract(pdf) == PdfRejected("invalid_pdf")


def test_encrypted_pdf_is_rejected_without_attempting_text_extraction():
    assert PypdfTextExtractor().extract(make_pdf(encrypted=True)) == PdfRejected("encrypted_pdf")


def test_unsupported_encryption_is_rejected_even_when_reader_construction_fails():
    pdf = make_pdf(encrypted=True).replace(b"/Filter /Standard", b"/Filter /UnknownX")
    assert PypdfTextExtractor().extract(pdf) == PdfRejected("encrypted_pdf")


def test_missing_encryption_dependency_is_a_declared_encrypted_pdf_rejection(monkeypatch):
    def missing_crypto(*args, **kwargs):
        raise DependencyError("cryptography>=3.1 is required for AES algorithm")

    monkeypatch.setattr(
        "contexts.document_processing.v1.infrastructure.pypdf_text_extractor.PdfReader", missing_crypto,
    )
    assert PypdfTextExtractor().extract(make_pdf(encrypted=True)) == PdfRejected("encrypted_pdf")


@pytest.mark.parametrize("error", [MemoryError, LimitReachedError])
def test_known_library_resource_failure_is_a_system_error_not_a_pdf_rejection(monkeypatch, error):
    # Fault injection at the external library, not a mock of our parser port.
    def exhausted(*args, **kwargs):
        raise error("private library details")

    monkeypatch.setattr(PageObject, "extract_text", exhausted)
    with pytest.raises(PdfExtractionError, match="^PDF extraction unavailable$"):
        PypdfTextExtractor().extract(make_pdf())


@pytest.fixture
def cli_files(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "presets": [{"name": "vision", "endpoint": "https://vision.example/v1", "model": "selected-model"}],
        "unreadable_threshold_percent": 60,
    }))
    upload = tmp_path / "upload.pdf"
    upload.write_bytes(make_pdf())
    return config, upload, tmp_path / "documents"


def run_cli(cli_files, *, preset="vision", module=False, legacy=False):
    config, upload, root = cli_files
    script = "extract-pdf-text" if legacy else "extract-pdf-text-v1"
    command = ([sys.executable, "-m", "contexts.document_processing.v1.presentation.extract_pdf_text_cli"]
               if module else [str(Path(sys.executable).parent / script)])
    return subprocess.run([
        *command, str(upload), "--config", str(config), "--preset", preset, "--data-dir", str(root),
    ], cwd=upload.parent, capture_output=True, text=True, timeout=15)


def test_cli_saves_partial_results_with_unavailable_fallback_and_exact_uploaded_pdf(cli_files):
    _, upload, root = cli_files

    result = run_cli(cli_files)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    response = json.loads(result.stdout)
    directory = root / response["document_id"]
    assert response == {
        "outcome": "saved",
        "document_id": directory.name,
        "summary": {"total_pages": 3, "extracted_pages": 2, "failed_pages": 1},
        "files": {
            "original_pdf": str(directory / "original.pdf"),
            "extraction_json": str(directory / "extraction.json"),
        },
    }
    assert "First page" not in result.stdout
    assert "Third page" not in result.stdout
    assert (directory / "original.pdf").read_bytes() == upload.read_bytes()
    stored = json.loads((directory / "extraction.json").read_text())
    assert stored["pages"] == [
        {"number": 1, "text": "First page", "status": "extracted", "method": "pdf_text",
         "failure_code": None, "preset_name": None, "model": None},
        {"number": 2, "text": None, "status": "failed", "method": "vision",
         "failure_code": "fallback_unavailable", "preset_name": "vision", "model": "selected-model"},
        {"number": 3, "text": "Third page", "status": "extracted", "method": "pdf_text",
         "failure_code": None, "preset_name": None, "model": None},
    ]
    assert stored["document_id"] == directory.name


# The main tracer implemented these paths; add regression without deleting code.
def test_module_entry_point_uses_the_same_real_local_composition(cli_files):
    result = run_cli(cli_files, module=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["outcome"] == "saved"


def test_installed_console_commands_target_their_declared_version():
    scripts = {
        entry.name: entry.value for entry in distribution("registration-sketch").entry_points
        if entry.group == "console_scripts"
    }
    assert {name: scripts[name] for name in ("extract-pdf-text", "extract-pdf-text-v1", "extract-pdf-text-v2")} == {
        "extract-pdf-text": "contexts.document_processing.v1.presentation.extract_pdf_text_cli:main",
        "extract-pdf-text-v1": "contexts.document_processing.v1.presentation.extract_pdf_text_cli:main",
        "extract-pdf-text-v2": "contexts.document_processing.v2.presentation.extract_pdf_text_cli:main",
    }


def test_legacy_console_alias_still_saves_the_v1_summary(cli_files):
    _, upload, root = cli_files
    result = run_cli(cli_files, legacy=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    response = json.loads(result.stdout)
    assert response["outcome"] == "saved"
    assert response["summary"] == {"total_pages": 3, "extracted_pages": 2, "failed_pages": 1}
    assert "pages" not in response
    directory = root / response["document_id"]
    assert (directory / "original.pdf").read_bytes() == upload.read_bytes()
    assert Path(response["files"]["extraction_json"]) == directory / "extraction.json"
    assert len(json.loads((directory / "extraction.json").read_text())["pages"]) == 3


def test_readable_pdf_saves_all_pages_without_vision_failure(cli_files):
    _, upload, _ = cli_files
    upload.write_bytes(make_pdf(texts=("Only readable text",)))
    result = run_cli(cli_files)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["summary"] == {"total_pages": 1, "extracted_pages": 1, "failed_pages": 0}
    assert "pages" not in response
    assert "Only readable text" not in result.stdout
    stored = json.loads(Path(response["files"]["extraction_json"]).read_text())
    assert stored["pages"] == [
        {"number": 1, "text": "Only readable text", "status": "extracted", "method": "pdf_text",
         "failure_code": None, "preset_name": None, "model": None},
    ]


@pytest.mark.parametrize("pdf,code", [
    (b"", "invalid_pdf"), (b"private invalid upload", "invalid_pdf"),
    (make_pdf(encrypted=True), "encrypted_pdf"),
    (make_pdf(encrypted=True).replace(b"/Filter /Standard", b"/Filter /UnknownX"), "encrypted_pdf"),
])
def test_cli_expected_pdf_rejection_has_no_storage_effect(cli_files, pdf, code):
    _, upload, root = cli_files
    upload.write_bytes(pdf)
    result = run_cli(cli_files)
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"outcome": "rejected", "code": code}
    assert not root.exists()


def test_cli_unapproved_preset_is_rejected_without_storage(cli_files):
    _, _, root = cli_files
    result = run_cli(cli_files, preset="https://unapproved.example/private")
    assert result.returncode == 2
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"outcome": "rejected", "code": "invalid_preset"}
    assert not root.exists()


@pytest.mark.parametrize("config_text", [
    "private invalid config", "null", '{"presets": []}',
    '{"presets": [{"name": "vision", "endpoint": "https://user:secret@example.com", "model": "m"}]}',
    '{"presets": [{"name": "vision", "endpoint": "https://vision.example/v1", "model": "m"}], "unreadable_threshold_percent": -1}',
])
def test_cli_configuration_failure_has_safe_system_error_and_no_success(cli_files, config_text):
    config, _, root = cli_files
    config.write_text(config_text)
    result = run_cli(cli_files)
    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"outcome": "error", "code": "system_error"}
    assert not root.exists()


def test_cli_missing_input_is_a_safe_system_error(cli_files):
    _, upload, root = cli_files
    upload.unlink()
    result = run_cli(cli_files)
    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"outcome": "error", "code": "system_error"}
    assert not root.exists()


def test_cli_rejects_insecure_storage_instead_of_false_success(cli_files):
    _, _, root = cli_files
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    result = run_cli(cli_files)
    assert result.returncode == 1
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"outcome": "error", "code": "system_error"}
    assert list(root.iterdir()) == []


def test_concurrent_cli_executions_keep_responses_and_saved_documents_isolated(cli_files):
    config, upload, root = cli_files
    other = upload.with_name("other.pdf")
    upload.write_bytes(make_pdf(texts=("Request A",)))
    other.write_bytes(make_pdf(texts=("Request B",)))
    inputs = [(config, upload, root), (config, other, root)]
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(run_cli, files) for files in inputs]
        results = [future.result(timeout=20) for future in futures]

    ids = set()
    for result, (_, source, _), expected in zip(results, inputs, ("Request A", "Request B")):
        assert result.returncode == 0, result.stderr
        response = json.loads(result.stdout)
        assert response["summary"] == {"total_pages": 1, "extracted_pages": 1, "failed_pages": 0}
        assert "pages" not in response
        assert expected not in result.stdout
        ids.add(response["document_id"])
        directory = root / response["document_id"]
        assert response["files"] == {
            "original_pdf": str(directory / "original.pdf"),
            "extraction_json": str(directory / "extraction.json"),
        }
        assert Path(response["files"]["original_pdf"]).read_bytes() == source.read_bytes()
        stored = json.loads(Path(response["files"]["extraction_json"]).read_text())
        assert stored["pages"][0]["text"] == expected
    assert len(ids) == 2
    assert {path.name for path in root.iterdir()} == ids


def test_failed_stdout_after_commit_returns_system_error_without_repeating_or_undoing_storage(cli_files, monkeypatch, capsys):
    config, upload, root = cli_files

    class BrokenStdout:
        def write(self, content):
            raise BrokenPipeError("private transport details")

    with monkeypatch.context() as patch:
        patch.setattr(sys, "stdout", BrokenStdout())
        code = main([
            str(upload), "--config", str(config), "--preset", "vision", "--data-dir", str(root),
        ])

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    directory, = root.iterdir()
    assert (directory / "original.pdf").read_bytes() == upload.read_bytes()
    assert len(json.loads((directory / "extraction.json").read_text())["pages"]) == 3


@pytest.mark.parametrize("error", [MemoryError, RuntimeError])
def test_cli_parser_system_failure_is_safe_and_prevents_storage(cli_files, monkeypatch, capsys, error):
    config, upload, root = cli_files

    def fail(*args, **kwargs):
        raise error("private library content")

    monkeypatch.setattr(PageObject, "extract_text", fail)
    code = main([
        str(upload), "--config", str(config), "--preset", "vision", "--data-dir", str(root),
    ])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert json.loads(captured.err) == {"outcome": "error", "code": "system_error"}
    assert not root.exists()


def test_cli_omits_document_terminal_control_characters_but_preserves_them_in_storage(cli_files):
    _, upload, _ = cli_files
    upload.write_bytes(make_pdf(texts=("\u001b[31mred",)))
    result = run_cli(cli_files)
    assert result.returncode == 0, result.stderr
    assert "\u001b" not in result.stdout
    assert "\\u001b" not in result.stdout
    response = json.loads(result.stdout)
    assert "pages" not in response
    stored = json.loads(Path(response["files"]["extraction_json"]).read_text())
    assert stored["pages"][0]["text"] == "\u001b[31mred"


def test_cli_reports_absolute_file_paths_when_data_directory_is_relative(cli_files):
    config, upload, _ = cli_files
    result = run_cli((config, upload, Path("relative-documents")))
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    directory = upload.parent / "relative-documents" / response["document_id"]
    assert response["files"] == {
        "original_pdf": str(directory / "original.pdf"),
        "extraction_json": str(directory / "extraction.json"),
    }
    assert Path(response["files"]["original_pdf"]).read_bytes() == upload.read_bytes()
    assert json.loads(Path(response["files"]["extraction_json"]).read_text())["document_id"] == directory.name


def test_cli_summary_reports_all_failed_pages_without_false_extraction_success(cli_files):
    _, upload, _ = cli_files
    upload.write_bytes(make_pdf(texts=("", "")))
    result = run_cli(cli_files)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["outcome"] == "saved"
    assert response["summary"] == {"total_pages": 2, "extracted_pages": 0, "failed_pages": 2}
    assert "pages" not in response
    stored = json.loads(Path(response["files"]["extraction_json"]).read_text())
    assert [(page["status"], page["failure_code"], page["text"]) for page in stored["pages"]] == [
        ("failed", "fallback_unavailable", None), ("failed", "fallback_unavailable", None),
    ]

