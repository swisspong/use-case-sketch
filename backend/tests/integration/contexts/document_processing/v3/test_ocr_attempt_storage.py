"""OcrAttemptStore port on real private local files; files are the agreed observation seam."""

from concurrent.futures import ThreadPoolExecutor
import json
import stat
from threading import Barrier

import pytest

from contexts.document_processing.v3.application.use_cases.ocr_document_pages.errors import OcrAttemptStorageError
from contexts.document_processing.v3.application.use_cases.ocr_document_pages.ports import SavedOcrAttempt
from contexts.document_processing.v3.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v3.domain.documents.ocr_attempt import OcrAttempt, SuggestedPage
from contexts.document_processing.v3.infrastructure.local_json_extraction_store import LocalJsonExtractionStore
from contexts.document_processing.v3.infrastructure.local_json_ocr_attempt_store import LocalJsonOcrAttemptStore


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / "documents"
    document = DocumentExtraction.from_pdf((SourcePage(1, ""), SourcePage(2, "ok"), SourcePage(3, "")),
                                           threshold_percent=10)
    document_id = LocalJsonExtractionStore(root).save(document, pdf=b"%PDF-original").document_id
    return root, document_id


def finished_attempt(document_id):
    attempt = OcrAttempt.start(
        document_id=document_id,
        saved_pages=(SuggestedPage(1, True), SuggestedPage(2, False), SuggestedPage(3, True)),
        requested=(1, 2, 3), preset_name="mfec", model="gemini-3.8-flash", threshold_percent=10,
    )
    attempt = attempt.record_text(page_number=1, text="หน้าหนึ่ง")
    attempt = attempt.record_unreadable(page_number=2)
    return attempt.record_unavailable(page_number=3)


def test_attempt_is_appended_as_a_new_private_file_without_touching_the_document(saved):
    root, document_id = saved
    directory = root / document_id
    before = {name: (directory / name).read_bytes() for name in ("extraction.json", "original.pdf")}

    acknowledgement = LocalJsonOcrAttemptStore(root).append(finished_attempt(document_id))

    assert isinstance(acknowledgement, SavedOcrAttempt) and acknowledgement.attempt_id.strip()
    record = directory / "ocr" / f"{acknowledgement.attempt_id}.json"
    assert json.loads(record.read_text()) == {
        "schema_version": 1,
        "attempt_id": acknowledgement.attempt_id,
        "document_id": document_id,
        "preset_name": "mfec",
        "model": "gemini-3.8-flash",
        "threshold_percent": 10,
        "pages": [
            {"number": 1, "was_suggested": True, "status": "extracted", "text": "หน้าหนึ่ง",
             "problem_character_count": 0, "non_whitespace_character_count": 9, "problem_percent": 0.0},
            {"number": 2, "was_suggested": False, "status": "unreadable", "text": None,
             "problem_character_count": None, "non_whitespace_character_count": None, "problem_percent": None},
            {"number": 3, "was_suggested": True, "status": "ocr_unavailable", "text": None,
             "problem_character_count": None, "non_whitespace_character_count": None, "problem_percent": None},
        ],
    }
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    assert stat.S_IMODE((directory / "ocr").stat().st_mode) == 0o700
    assert [path.name for path in (directory / "ocr").iterdir()] == [record.name]
    assert {name: (directory / name).read_bytes() for name in before} == before


def test_every_attempt_is_kept_including_concurrent_appends(saved):
    root, document_id = saved
    store = LocalJsonOcrAttemptStore(root)
    first = store.append(finished_attempt(document_id))
    first_bytes = (root / document_id / "ocr" / f"{first.attempt_id}.json").read_bytes()
    barrier = Barrier(4)

    def append(_):
        barrier.wait(timeout=5)
        return LocalJsonOcrAttemptStore(root).append(finished_attempt(document_id)).attempt_id

    with ThreadPoolExecutor(4) as pool:
        concurrent = list(pool.map(append, range(4)))

    identities = {first.attempt_id, *concurrent}
    assert len(identities) == 5
    assert sorted(path.name for path in (root / document_id / "ocr").iterdir()) == sorted(
        f"{identity}.json" for identity in identities
    )
    assert (root / document_id / "ocr" / f"{first.attempt_id}.json").read_bytes() == first_bytes


@pytest.mark.parametrize("failure", ["missing_document", "malformed_identity", "readonly_ocr", "symlinked_ocr"])
def test_storage_failure_is_reported_without_a_published_attempt(saved, tmp_path, failure):
    root, document_id = saved
    attempt = finished_attempt(document_id)
    ocr = root / document_id / "ocr"
    if failure == "missing_document":
        attempt = finished_attempt("e" * 32)
    elif failure == "malformed_identity":
        attempt = finished_attempt("../" + document_id)
    elif failure == "readonly_ocr":
        ocr.mkdir(mode=0o700)
        ocr.chmod(0o500)
    else:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir(mode=0o700)
        ocr.symlink_to(elsewhere)

    with pytest.raises(OcrAttemptStorageError) as caught:
        LocalJsonOcrAttemptStore(root).append(attempt)

    assert str(caught.value) == "OCR attempt storage unavailable"
    if failure == "readonly_ocr":
        ocr.chmod(0o700)
        assert list(ocr.iterdir()) == []
    if failure == "symlinked_ocr":
        assert list((tmp_path / "elsewhere").iterdir()) == []
    assert not (root / ("e" * 32)).exists()
