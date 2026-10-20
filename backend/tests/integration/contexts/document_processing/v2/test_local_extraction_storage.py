"""Public storage port; persisted files are the approved observation seam."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import stat
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest

from contexts.document_processing.v2.application.use_cases.extract_pdf_text.errors import DocumentStorageError

from contexts.document_processing.v2.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v2.infrastructure.local_json_extraction_store import LocalJsonExtractionStore


def terminal_document(*, detect=False):
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "Hello ไทย"), SourcePage(2, "")), threshold_percent=60,
        suspicious_threshold_percent=0 if detect else None,
    )
    return document.fail_fallback(
        page_number=2, code="fallback_unavailable", preset_name="vision", model="selected-model",
    )


def test_original_pdf_and_exact_terminal_pages_are_saved_under_one_new_identity(tmp_path):
    root = tmp_path / "documents"
    saved = LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"original PDF bytes")

    assert saved.document_id.strip()
    directory = root / saved.document_id
    assert (directory / "original.pdf").read_bytes() == b"original PDF bytes"
    assert json.loads((directory / "extraction.json").read_text()) == {
        "schema_version": 1,
        "document_id": saved.document_id,
        "original_pdf": "original.pdf",
        "threshold_percent": 60,
        "pages": [
            {"number": 1, "text": "Hello ไทย", "status": "extracted", "method": "pdf_text",
             "failure_code": None, "preset_name": None, "model": None},
            {"number": 2, "text": None, "status": "failed", "method": "vision",
             "failure_code": "fallback_unavailable", "preset_name": "vision", "model": "selected-model"},
        ],
    }
    assert sorted(path.name for path in directory.iterdir()) == ["extraction.json", "original.pdf"]
    assert list(root.iterdir()) == [directory]


def test_raw_reports_are_saved_as_schema_two_without_changing_existing_schema_one(tmp_path):
    root = tmp_path / "documents"
    store = LocalJsonExtractionStore(root)
    old = store.save(terminal_document(), pdf=b"old exact PDF bytes")
    old_directory = root / old.document_id
    old_json = (old_directory / "extraction.json").read_bytes()
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "ทีC เชืMอ"), SourcePage(2, "\ufffd")),
        threshold_percent=60, suspicious_threshold_percent=0,
    ).fail_fallback(
        page_number=2, code="fallback_unavailable", preset_name="vision", model="selected-model",
    )

    saved = store.save(document, pdf=b"new exact PDF bytes")

    directory = root / saved.document_id
    assert saved.document_id != old.document_id
    assert (directory / "original.pdf").read_bytes() == b"new exact PDF bytes"
    assert json.loads((directory / "extraction.json").read_text()) == {
        "schema_version": 2,
        "document_id": saved.document_id,
        "original_pdf": "original.pdf",
        "threshold_percent": 60,
        "pages": [
            {"number": 1, "text": "ทีC เชืMอ", "status": "extracted", "method": "pdf_text",
             "failure_code": None, "preset_name": None, "model": None},
            {"number": 2, "text": None, "status": "failed", "method": "vision",
             "failure_code": "fallback_unavailable", "preset_name": "vision", "model": "selected-model"},
        ],
        "raw_text_quality": [
            {"number": 1, "raw_text": "ทีC เชืMอ", "spans": [
                {"start": 2, "end": 3, "reason": "latin_adjacent_to_thai"},
                {"start": 7, "end": 8, "reason": "latin_adjacent_to_thai"},
            ], "suspicious_character_count": 2, "non_whitespace_character_count": 8,
             "suspicious_percent": 25.0, "threshold_percent": 0, "flagged": True},
            {"number": 2, "raw_text": "\ufffd", "spans": [
                {"start": 0, "end": 1, "reason": "replacement_character"},
            ], "suspicious_character_count": 1, "non_whitespace_character_count": 1,
             "suspicious_percent": 100.0, "threshold_percent": 0, "flagged": True},
        ],
    }
    assert (old_directory / "extraction.json").read_bytes() == old_json
    assert json.loads(old_json)["schema_version"] == 1
    assert (old_directory / "original.pdf").read_bytes() == b"old exact PDF bytes"
    assert stat.S_IMODE((directory / "extraction.json").stat().st_mode) == 0o600
    assert {path.name for path in root.iterdir()} == {old.document_id, saved.document_id}


def test_pending_pages_are_rejected_before_any_files_are_created(tmp_path):
    root = tmp_path / "documents"
    pending = DocumentExtraction.from_pdf((SourcePage(1, ""),), threshold_percent=60)

    with pytest.raises(ValueError, match="terminal"):
        LocalJsonExtractionStore(root).save(pending, pdf=b"original")

    assert not root.exists()


@pytest.mark.parametrize("mode", [0o755, 0o777])
def test_existing_data_directory_with_shared_permissions_is_rejected(tmp_path, mode):
    root = tmp_path / "documents"
    root.mkdir()
    root.chmod(mode)

    with pytest.raises(DocumentStorageError, match="^Local document storage unavailable$"):
        LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"private")

    assert list(root.iterdir()) == []


def test_generated_identity_collision_never_replaces_an_existing_document(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir(mode=0o700)
    existing = root / "00000000000000000000000000000001"
    existing.mkdir()
    monkeypatch.setattr(
        "contexts.document_processing.v2.infrastructure.local_json_extraction_store.uuid4",
        lambda: UUID(int=1),
    )

    with pytest.raises(DocumentStorageError):
        LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"new PDF")

    assert list(root.iterdir()) == [existing]
    assert list(existing.iterdir()) == []


# Regression evidence for the already-implemented commit protocol: no fake red.
@pytest.mark.parametrize("detect", [False, True], ids=["schema-one", "schema-two"])
@pytest.mark.parametrize("failure", ["pdf_sync", "json_sync", "staging_sync", "publish"])
def test_pre_publish_failure_leaves_no_visible_document_or_staging(tmp_path, monkeypatch, failure, detect):
    root = tmp_path / "documents"
    real_sync = os.fsync
    real_rename = os.rename

    def sync(fd):
        name = Path(os.readlink(f"/proc/self/fd/{fd}")).name
        if ((failure == "pdf_sync" and name == "original.pdf")
                or (failure == "json_sync" and name == "extraction.json")
                or (failure == "staging_sync" and name.startswith(".staging-"))):
            raise OSError("private disk failure")
        return real_sync(fd)

    def rename(source, destination):
        if failure == "publish":
            raise OSError("private publish failure")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(DocumentStorageError, match="^Local document storage unavailable$"):
        LocalJsonExtractionStore(root).save(terminal_document(detect=detect), pdf=b"private original")

    assert list(root.iterdir()) == []


@pytest.mark.parametrize("detect", [False, True], ids=["schema-one", "schema-two"])
def test_failed_post_publish_ack_does_not_claim_rollback_or_delete_the_complete_document(tmp_path, monkeypatch, detect):
    root = tmp_path / "documents"
    real_sync = os.fsync

    def sync(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if path == root and any(not item.name.startswith(".") for item in root.iterdir()):
            raise OSError("private acknowledgement failure")
        return real_sync(fd)

    monkeypatch.setattr(os, "fsync", sync)
    with pytest.raises(DocumentStorageError):
        LocalJsonExtractionStore(root).save(terminal_document(detect=detect), pdf=b"committed original")

    directory, = root.iterdir()
    assert (directory / "original.pdf").read_bytes() == b"committed original"
    stored = json.loads((directory / "extraction.json").read_text())
    assert stored["document_id"] == directory.name
    assert stored["schema_version"] == (2 if detect else 1)
    if detect:
        assert [(report["raw_text"], report["flagged"]) for report in stored["raw_text_quality"]] == [
            ("Hello ไทย", False), ("", False),
        ]
    assert not directory.name.startswith(".")


@pytest.mark.parametrize("detect", [False, True], ids=["schema-one", "schema-two"])
def test_files_and_directories_are_owner_only(tmp_path, detect):
    root = tmp_path / "documents"
    saved = LocalJsonExtractionStore(root).save(terminal_document(detect=detect), pdf=b"private")
    directory = root / saved.document_id
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert {stat.S_IMODE(path.stat().st_mode) for path in directory.iterdir()} == {0o600}


def test_symlink_data_directory_is_rejected_without_writing_to_its_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    root = tmp_path / "documents"
    root.symlink_to(target, target_is_directory=True)

    with pytest.raises(DocumentStorageError):
        LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"private")

    assert list(target.iterdir()) == []


@pytest.mark.parametrize("detect", [False, True], ids=["schema-one", "schema-two"])
def test_concurrent_identity_collision_has_one_winner_and_never_mixes_documents(tmp_path, monkeypatch, detect):
    root = tmp_path / "documents"
    root.mkdir(mode=0o700)
    ready = Barrier(2)
    real_sync = os.fsync
    monkeypatch.setattr(
        "contexts.document_processing.v2.infrastructure.local_json_extraction_store.uuid4",
        lambda: UUID(int=2),
    )

    def sync(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if path.name.startswith(".staging-"):
            # Force both independent writers to reach the pre-publish boundary.
            assert [item for item in root.iterdir() if not item.name.startswith(".")] == []
            ready.wait(timeout=5)
        return real_sync(fd)

    def save(pdf):
        document = terminal_document()
        if detect:
            document = DocumentExtraction.from_pdf(
                (SourcePage(1, "ทีC" if pdf == b"candidate-A" else "เชืMอ"),),
                threshold_percent=60, suspicious_threshold_percent=0,
            )
        try:
            return LocalJsonExtractionStore(root).save(document, pdf=pdf), pdf
        except DocumentStorageError:
            return None, pdf

    monkeypatch.setattr(os, "fsync", sync)
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(save, pdf) for pdf in (b"candidate-A", b"candidate-B")]
        results = [future.result(timeout=10) for future in futures]

    winners = [(saved, pdf) for saved, pdf in results if saved is not None]
    assert len(winners) == 1
    saved, pdf = winners[0]
    directory, = root.iterdir()
    assert directory.name == saved.document_id
    assert (directory / "original.pdf").read_bytes() == pdf
    stored = json.loads((directory / "extraction.json").read_text())
    assert stored["schema_version"] == (2 if detect else 1)
    if detect:
        expected_text = "ทีC" if pdf == b"candidate-A" else "เชืMอ"
        assert len(stored["pages"]) == 1
        assert stored["pages"][0]["text"] == expected_text
        assert len(stored["raw_text_quality"]) == 1
        assert stored["raw_text_quality"][0]["raw_text"] == expected_text
        assert stored["raw_text_quality"][0]["flagged"] is True
    else:
        assert len(stored["pages"]) == 2
