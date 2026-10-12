"""SavedDocumentSource port against real private local files written by extraction."""

import json
import os

import pytest

from contexts.document_processing.v3.application.use_cases.ocr_document_pages.errors import DocumentSourceError
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.ports import (
    DocumentNotFound, SavedDocumentForOcr,
)
from contexts.document_processing.v3.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v3.domain.documents.ocr_attempt import SuggestedPage
from contexts.document_processing.v3.infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from contexts.document_processing.v3.infrastructure.local_json_saved_document_source import (
    LocalJsonSavedDocumentSource,
)

PDF = b"%PDF-1.7 exact original bytes"


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / "documents"
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "อ่านได้ปกติ"), SourcePage(2, ""), SourcePage(3, "\ufffd\ufffd ok")),
        threshold_percent=25,
    )
    document_id = LocalJsonExtractionStore(root).save(document, pdf=PDF).document_id
    return root, document_id


def test_saved_document_is_loaded_with_exact_pdf_suggestions_and_threshold(saved):
    root, document_id = saved

    assert LocalJsonSavedDocumentSource(root).load(document_id) == SavedDocumentForOcr(
        document_id, PDF,
        (SuggestedPage(1, False), SuggestedPage(2, True), SuggestedPage(3, True)),
        threshold_percent=25,
    )


@pytest.mark.parametrize("document_id", [
    "0" * 32, "", "..", "../documents", "a/b", "ABCDEF" + "0" * 26, "0" * 31, None, 17,
])
def test_unknown_or_malformed_identity_is_not_found(saved, document_id):
    root, _ = saved

    assert LocalJsonSavedDocumentSource(root).load(document_id) == DocumentNotFound()


def test_missing_data_directory_means_not_found(tmp_path):
    assert LocalJsonSavedDocumentSource(tmp_path / "absent").load("a" * 32) == DocumentNotFound()


def corrupt(directory, failure):
    extraction = directory / "extraction.json"
    data = json.loads(extraction.read_text())
    if failure == "invalid_json":
        extraction.write_text("{")
    elif failure == "old_schema":
        extraction.write_text(json.dumps({**data, "schema_version": 2}))
    elif failure == "missing_pages":
        extraction.write_text(json.dumps({key: value for key, value in data.items() if key != "pages"}))
    elif failure == "pages_not_list":
        extraction.write_text(json.dumps({**data, "pages": {"number": 1}}))
    elif failure == "page_without_suggestion":
        extraction.write_text(json.dumps({**data, "pages": [{"number": 1}]}))
    elif failure == "missing_pdf":
        (directory / "original.pdf").unlink()
    elif failure == "shared_pdf":
        (directory / "original.pdf").chmod(0o644)
    elif failure == "symlinked_pdf":
        (directory / "original.pdf").unlink()
        (directory / "original.pdf").symlink_to(directory / "extraction.json")
    elif failure == "symlinked_document":
        target = directory.with_name("elsewhere")
        directory.rename(target)
        directory.symlink_to(target)


@pytest.mark.parametrize("failure", [
    "invalid_json", "old_schema", "missing_pages", "pages_not_list", "page_without_suggestion",
    "missing_pdf", "shared_pdf", "symlinked_pdf", "symlinked_document",
])
def test_corrupt_or_unsafe_saved_record_is_a_source_error(saved, failure):
    root, document_id = saved
    corrupt(root / document_id, failure)

    with pytest.raises(DocumentSourceError) as caught:
        LocalJsonSavedDocumentSource(root).load(document_id)

    assert str(caught.value) == "Saved document unavailable"


def test_shared_data_directory_is_a_source_error(saved):
    root, document_id = saved
    root.chmod(0o755)

    with pytest.raises(DocumentSourceError):
        LocalJsonSavedDocumentSource(root).load(document_id)


def test_domain_level_facts_are_passed_through_for_the_interactor_to_judge(saved):
    root, document_id = saved
    extraction = root / document_id / "extraction.json"
    data = json.loads(extraction.read_text())
    data["document_id"] = "f" * 32
    data["pages"] = [{**data["pages"][0], "number": 5, "ocr_suggested": "yes"}]
    extraction.write_text(json.dumps(data))
    os.chmod(extraction, 0o600)

    loaded = LocalJsonSavedDocumentSource(root).load(document_id)

    assert (loaded.document_id, loaded.pages) == ("f" * 32, (SuggestedPage(5, "yes"),))
