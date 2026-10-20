"""Public storage port; persisted files are the approved observation seam."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import stat
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest

from contexts.document_processing.v1.application.use_cases.extract_pdf_text.errors import DocumentStorageError

from contexts.document_processing.v1.domain.documents.extraction import DocumentExtraction, SourcePage
from contexts.document_processing.v1.infrastructure.local_json_extraction_store import LocalJsonExtractionStore


def terminal_document():
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "Hello ไทย"), SourcePage(2, "")), threshold_percent=60,
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
        "contexts.document_processing.v1.infrastructure.local_json_extraction_store.uuid4",
        lambda: UUID(int=1),
    )

    with pytest.raises(DocumentStorageError):
        LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"new PDF")

    assert list(root.iterdir()) == [existing]
    assert list(existing.iterdir()) == []


# Regression evidence for the already-implemented commit protocol: no fake red.
@pytest.mark.parametrize("failure", ["pdf_sync", "json_sync", "staging_sync", "publish"])
def test_pre_publish_failure_leaves_no_visible_document_or_staging(tmp_path, monkeypatch, failure):
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
        LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"private original")

    assert list(root.iterdir()) == []


def test_failed_post_publish_ack_does_not_claim_rollback_or_delete_the_complete_document(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    real_sync = os.fsync

    def sync(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if path == root and any(not item.name.startswith(".") for item in root.iterdir()):
            raise OSError("private acknowledgement failure")
        return real_sync(fd)

    monkeypatch.setattr(os, "fsync", sync)
    with pytest.raises(DocumentStorageError):
        LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"committed original")

    directory, = root.iterdir()
    assert (directory / "original.pdf").read_bytes() == b"committed original"
    assert json.loads((directory / "extraction.json").read_text())["document_id"] == directory.name
    assert not directory.name.startswith(".")


def test_files_and_directories_are_owner_only(tmp_path):
    root = tmp_path / "documents"
    saved = LocalJsonExtractionStore(root).save(terminal_document(), pdf=b"private")
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


def test_concurrent_identity_collision_has_one_winner_and_never_mixes_documents(tmp_path, monkeypatch):
    root = tmp_path / "documents"
    root.mkdir(mode=0o700)
    ready = Barrier(2)
    real_sync = os.fsync
    monkeypatch.setattr(
        "contexts.document_processing.v1.infrastructure.local_json_extraction_store.uuid4",
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
        try:
            return LocalJsonExtractionStore(root).save(terminal_document(), pdf=pdf), pdf
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
    assert len(json.loads((directory / "extraction.json").read_text())["pages"]) == 2
