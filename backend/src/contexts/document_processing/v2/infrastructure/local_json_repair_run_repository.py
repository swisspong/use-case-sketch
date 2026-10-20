"""Append-only repair collection: atomic POSIX publication, no shared JSON index."""

from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from ..application.use_cases.repair_extracted_text.errors import RepairRunStorageError
from ..application.use_cases.repair_extracted_text.records import RepairRun, SavedRepairRun
from ..application.use_cases.repair_extracted_text.response import (
    CompletedTextRepair, RepairNoChanges, RepairSuggested, RepairUnrepairable, SuggestedTextRepair,
)
from .private_json_files import MAX_JSON_BYTES, is_identity, private_directory, read_json


_OUTCOMES = {
    RepairSuggested: "suggested", RepairNoChanges: "no_changes", RepairUnrepairable: "unrepairable",
}


def _decode(data, identity: str) -> RepairRun:
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1 or data.get("repair_id") != identity
            or not isinstance(data.get("created_at"), str)):
        raise ValueError("Invalid repair record")
    timestamp = datetime.fromisoformat(data["created_at"])
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError("Invalid record timestamp")
    for name in ("document_id", "preset_name", "model"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ValueError("Invalid record identity/provenance")
    if type(data.get("page_number")) is not int or data["page_number"] < 1:
        raise ValueError("Invalid record page")
    edits = data.get("edits")
    if not isinstance(edits, list):
        raise ValueError("Invalid record edits")
    common = (data["document_id"], data["page_number"])
    provenance = (data["preset_name"], data["model"])
    if data.get("outcome") == "suggested":
        if not edits or any(
            not isinstance(edit, dict) or set(edit) != {"start", "end", "replacement"}
            or type(edit["start"]) is not int or type(edit["end"]) is not int
            or not 0 <= edit["start"] < edit["end"] or not isinstance(edit["replacement"], str)
            for edit in edits
        ):
            raise ValueError("Invalid record proposal")
        result = RepairSuggested(*common, tuple(SuggestedTextRepair(**edit) for edit in edits), *provenance)
    elif data.get("outcome") == "no_changes" and not edits:
        result = RepairNoChanges(*common, *provenance)
    elif data.get("outcome") == "unrepairable" and not edits:
        result = RepairUnrepairable(*common, *provenance)
    else:
        raise ValueError("Invalid record outcome")
    return RepairRun(identity, data["created_at"], result)


class LocalJsonRepairRunRepository:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, result: CompletedTextRepair) -> SavedRepairRun:
        if type(result) not in _OUTCOMES or result.repair_id is not None:
            raise ValueError("Repository requires an unrecorded completed repair")
        identity = uuid4().hex
        data = asdict(result)
        data.update(schema_version=1, repair_id=identity,
                    created_at=datetime.now(timezone.utc).isoformat(), outcome=_OUTCOMES[type(result)])
        data["edits"] = list(data.get("edits", ()))
        _decode(data, identity)
        content = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(content) > MAX_JSON_BYTES:
            raise RepairRunStorageError("Repair history unavailable")
        try:
            try:
                self.root.mkdir(mode=0o700)
            except FileExistsError:
                pass
            else:
                parent_fd = os.open(self.root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            with private_directory(self.root) as root_fd:
                try:
                    os.mkdir("repair-runs", mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
                else:
                    os.fsync(root_fd)
                with private_directory("repair-runs", dir_fd=root_fd) as collection_fd:
                    collection = self.root / "repair-runs"
                    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=collection))
                    try:
                        fd = os.open(staging / "record.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, "wb") as stream:
                            stream.write(content)
                            stream.flush()
                            os.fsync(stream.fileno())
                        with private_directory(staging) as staging_fd:
                            os.fsync(staging_fd)
                        fcntl.flock(collection_fd, fcntl.LOCK_EX)
                        destination = collection / identity
                        if os.path.lexists(destination):
                            raise FileExistsError("Repair identity collision")
                        os.rename(staging, destination)
                        staging = None
                        os.fsync(collection_fd)
                    finally:
                        if staging is not None:
                            shutil.rmtree(staging)
        except OSError:
            raise RepairRunStorageError("Repair history unavailable") from None
        return SavedRepairRun(identity)

    def get(self, repair_id: str) -> RepairRun | None:
        if not is_identity(repair_id):
            return None
        try:
            with private_directory(self.root) as root_fd:
                with private_directory("repair-runs", dir_fd=root_fd) as collection_fd:
                    try:
                        with private_directory(repair_id, dir_fd=collection_fd) as record_fd:
                            # A published directory with no record is corrupt, not absent.
                            try:
                                return _decode(read_json(record_fd, "record.json"), repair_id)
                            except FileNotFoundError:
                                raise ValueError("Incomplete published repair record") from None
                    except FileNotFoundError:
                        return None
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError, KeyError):
            raise RepairRunStorageError("Repair history unavailable") from None

    def list_by_document(self, document_id: str) -> tuple[RepairRun, ...]:
        try:
            with private_directory(self.root) as root_fd:
                with private_directory("repair-runs", dir_fd=root_fd) as collection_fd:
                    identities = os.listdir(collection_fd)
            records = []
            for identity in identities:
                if identity.startswith(".staging-"):
                    continue
                if not is_identity(identity):
                    raise ValueError("Invalid published repair identity")
                record = self.get(identity)
                if record is None:
                    raise ValueError("Missing published repair record")
                if record.result.document_id == document_id:
                    records.append(record)
            return tuple(sorted(records, key=lambda record: (record.created_at, record.repair_id)))
        except FileNotFoundError:
            return ()
        except (OSError, ValueError, TypeError, KeyError):
            raise RepairRunStorageError("Repair history unavailable") from None
