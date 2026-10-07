"""Real local JSON ports; get/list and persisted files are the approved seams."""

import json
import os
import stat
from pathlib import Path

import pytest

from contexts.document_processing.v2.application.use_cases.repair_extracted_text.response import (
    RepairSuggested, SuggestedTextRepair,
)


def test_validated_repairs_are_append_only_records_not_extraction_updates(tmp_path):
    from contexts.document_processing.v2.infrastructure.local_json_repair_run_repository import LocalJsonRepairRunRepository

    root = tmp_path / "documents"
    repository = LocalJsonRepairRunRepository(root)
    proposed = RepairSuggested("a" * 32, 3, (SuggestedTextRepair(0, 3, "กาข"),), "approved", "text-model")

    first = repository.save(proposed)
    second = repository.save(proposed)

    assert first.repair_id != second.repair_id
    record = repository.get(first.repair_id)
    assert record.repair_id == first.repair_id
    assert record.result == proposed
    assert record.created_at.endswith("+00:00")
    assert {item.repair_id for item in repository.list_by_document("a" * 32)} == {
        first.repair_id, second.repair_id,
    }
    assert repository.list_by_document("b" * 32) == ()
    assert repository.get("0" * 32) is None
    path = root / "repair-runs" / first.repair_id / "record.json"
    assert json.loads(path.read_text()) == {
        "schema_version": 1, "repair_id": first.repair_id, "created_at": record.created_at,
        "document_id": "a" * 32, "page_number": 3, "outcome": "suggested",
        "preset_name": "approved", "model": "text-model",
        "edits": [{"start": 0, "end": 3, "replacement": "กาข"}],
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o700 for p in (root, path.parent, path.parent.parent))
    assert sorted(p.name for p in root.iterdir()) == ["repair-runs"]


@pytest.mark.parametrize("assessed", [False, True])
def test_source_reads_exact_saved_page_and_assessment_without_mutation(tmp_path, assessed):
    from contexts.document_processing.v2.domain.documents.extraction import DocumentExtraction, SourcePage
    from contexts.document_processing.v2.infrastructure.local_json_extraction_store import LocalJsonExtractionStore
    from contexts.document_processing.v2.infrastructure.local_json_repair_page_source import LocalJsonRepairPageSource
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import LoadedRepairPage, RepairPageNotFound

    root = tmp_path / "documents"
    document = DocumentExtraction.from_pdf(
        (SourcePage(1, "first"), SourcePage(2, "กิิิAข😀")), threshold_percent=100,
        suspicious_threshold_percent=0 if assessed else None,
    )
    saved = LocalJsonExtractionStore(root).save(document, pdf=b"synthetic original")
    path = root / saved.document_id / "extraction.json"
    original = path.read_bytes()
    source = LocalJsonRepairPageSource(root)

    loaded = source.load_page(document_id=saved.document_id, page_number=2)

    assert loaded == LoadedRepairPage(
        saved.document_id, document.pages[1], document.raw_text_quality[1] if assessed else None,
    )
    assert loaded.page.text == "กิิิAข😀"
    assert isinstance(source.load_page(document_id=saved.document_id, page_number=3), RepairPageNotFound)
    assert isinstance(source.load_page(document_id="0" * 32, page_number=2), RepairPageNotFound)
    assert path.read_bytes() == original
    assert (path.parent / "original.pdf").read_bytes() == b"synthetic original"


@pytest.fixture
def history(tmp_path):
    from contexts.document_processing.v2.infrastructure.local_json_repair_run_repository import LocalJsonRepairRunRepository
    root = tmp_path / "documents"
    repository = LocalJsonRepairRunRepository(root)
    result = RepairSuggested("a" * 32, 3, (SuggestedTextRepair(0, 3, "กาข"),), "approved", "text-model")
    return root, repository, result


@pytest.mark.parametrize("failure", ["file_sync", "staging_sync", "publish", "acknowledgement"])
def test_storage_failure_never_acknowledges_partial_history_and_does_not_undo_commit(history, monkeypatch, failure):
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import RepairRunStorageError
    root, repository, result = history
    real_sync, real_rename = os.fsync, os.rename

    def sync(fd):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        if ((failure == "file_sync" and path.name == "record.json")
                or (failure == "staging_sync" and path.name.startswith(".staging-"))
                or (failure == "acknowledgement" and path.name == "repair-runs")):
            raise OSError("private failure")
        return real_sync(fd)

    def rename(source, destination):
        if failure == "publish":
            raise OSError("private failure")
        return real_rename(source, destination)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "rename", rename)
    with pytest.raises(RepairRunStorageError, match="^Repair history unavailable$"):
        repository.save(result)

    records = repository.list_by_document("a" * 32)
    assert len(records) == (1 if failure == "acknowledgement" else 0)
    if records:
        assert records[0].result == result
    assert all(not path.name.startswith(".staging-") for path in (root / "repair-runs").iterdir())


@pytest.mark.parametrize("collision", [False, True])
def test_concurrent_appends_preserve_independent_records_and_never_overwrite(history, monkeypatch, collision):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import UUID
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import RepairRunStorageError
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.response import RepairNoChanges
    root, repository, suggested = history
    ready = Barrier(2)
    real_sync = os.fsync
    if collision:
        monkeypatch.setattr(
            "contexts.document_processing.v2.infrastructure.local_json_repair_run_repository.uuid4",
            lambda: UUID(int=9),
        )

    def sync(fd):
        if os.path.basename(os.readlink(f"/proc/self/fd/{fd}")).startswith(".staging-"):
            ready.wait(timeout=5)
        return real_sync(fd)

    def save(result):
        try:
            return repository.save(result), result
        except RepairRunStorageError:
            return None, result

    monkeypatch.setattr(os, "fsync", sync)
    unchanged = RepairNoChanges("a" * 32, 3, "approved", "text-model")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save, result) for result in (suggested, unchanged)]
        completed = [future.result(timeout=10) for future in futures]
    winners = [(saved, result) for saved, result in completed if saved is not None]
    assert len(winners) == (1 if collision else 2)
    assert len(repository.list_by_document("a" * 32)) == len(winners)
    for saved, result in winners:
        assert repository.get(saved.repair_id).result == result
    assert len(list((root / "repair-runs").iterdir())) == len(winners)


@pytest.mark.parametrize("fault", ["shared_root", "symlink_root", "shared_record", "symlink_record", "misbound", "missing_record", "unknown_schema", "deep_json"])
def test_unsafe_or_corrupt_history_is_not_returned_as_a_valid_record(history, tmp_path, fault):
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import RepairRunStorageError
    root, repository, result = history
    saved = repository.save(result)
    path = root / "repair-runs" / saved.repair_id / "record.json"
    if fault == "shared_root":
        root.chmod(0o755)
    elif fault == "symlink_root":
        target = tmp_path / "moved"
        root.rename(target)
        root.symlink_to(target, target_is_directory=True)
    elif fault == "shared_record":
        path.chmod(0o644)
    elif fault == "symlink_record":
        target = path.with_name("secret.json")
        path.rename(target)
        path.symlink_to(target)
    elif fault == "missing_record":
        path.unlink()
    elif fault == "deep_json":
        path.write_text("[" * 2000 + "0" + "]" * 2000)
    else:
        data = json.loads(path.read_text())
        data["repair_id" if fault == "misbound" else "schema_version"] = "wrong"
        path.write_text(json.dumps(data))
    with pytest.raises(RepairRunStorageError, match="^Repair history unavailable$"):
        repository.get(saved.repair_id)


@pytest.mark.parametrize("identity", ["../secret", "/tmp/secret", ".staging-private", "x" * 32])
def test_untrusted_identity_cannot_escape_history_or_source_roots(tmp_path, identity):
    from contexts.document_processing.v2.infrastructure.local_json_repair_run_repository import LocalJsonRepairRunRepository
    from contexts.document_processing.v2.infrastructure.local_json_repair_page_source import LocalJsonRepairPageSource
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.ports import RepairPageNotFound
    root = tmp_path / "absent"
    assert LocalJsonRepairRunRepository(root).get(identity) is None
    assert isinstance(LocalJsonRepairPageSource(root).load_page(document_id=identity, page_number=1), RepairPageNotFound)
    assert not root.exists()


@pytest.mark.parametrize("fault", ["document", "page", "schema", "missing_assessment", "missing_json", "symlink", "shared_root", "deep_json"])
def test_source_corruption_and_read_failures_are_not_missing_or_clean_assessments(tmp_path, fault):
    from contexts.document_processing.v2.domain.documents.extraction import DocumentExtraction, SourcePage
    from contexts.document_processing.v2.infrastructure.local_json_extraction_store import LocalJsonExtractionStore
    from contexts.document_processing.v2.infrastructure.local_json_repair_page_source import LocalJsonRepairPageSource
    from contexts.document_processing.v2.application.use_cases.repair_extracted_text.errors import InvalidRepairSourceResult, RepairSourceError
    root = tmp_path / "documents"
    document = DocumentExtraction.from_pdf((SourcePage(1, "กAข"),), threshold_percent=100, suspicious_threshold_percent=0)
    saved = LocalJsonExtractionStore(root).save(document, pdf=b"original")
    path = root / saved.document_id / "extraction.json"
    expected = InvalidRepairSourceResult
    if fault == "missing_json":
        path.unlink()
        expected = RepairSourceError
    elif fault == "symlink":
        target = path.with_name("other.json")
        path.rename(target)
        path.symlink_to(target)
        expected = RepairSourceError
    elif fault == "shared_root":
        root.chmod(0o755)
        expected = RepairSourceError
    elif fault == "deep_json":
        path.write_text("[" * 2000 + "0" + "]" * 2000)
    else:
        data = json.loads(path.read_text())
        if fault == "document":
            data["document_id"] = "b" * 32
        elif fault == "page":
            data["pages"][0]["number"] = 2
        elif fault == "schema":
            data["schema_version"] = True
        else:
            del data["raw_text_quality"]
        path.write_text(json.dumps(data))
    with pytest.raises(expected):
        LocalJsonRepairPageSource(root).load_page(document_id=saved.document_id, page_number=1)
