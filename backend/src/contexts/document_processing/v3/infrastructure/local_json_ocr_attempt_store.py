"""Append-only OCR attempt files in private local POSIX storage.

<data-dir>/<document_id>/ocr/<attempt_id>.json (attempt schema 1). The document
directory must already exist; it is never created here. A complete fsynced
temporary file is hard-linked to its final name (atomic, never overwrites), so a
reader sees either no attempt or a complete one. extraction.json, original.pdf
and earlier attempts are never rewritten. Credentials are not part of OcrAttempt
and are never stored. Any OSError -> OcrAttemptStorageError; a failure after the
link may follow a real commit: never retry or delete.
"""

from dataclasses import asdict
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from ..application.use_cases.ocr_document_pages.errors import OcrAttemptStorageError
from ..application.use_cases.ocr_document_pages.ports import SavedOcrAttempt
from ..domain.documents.ocr_attempt import OcrAttempt

_DOCUMENT_ID = re.compile(r"[0-9a-f]{32}")


def _private_directory_fd(name, *, dir_fd=None) -> int:
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise PermissionError("Private owner-only directory required")
    return fd


class LocalJsonOcrAttemptStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def append(self, attempt: OcrAttempt) -> SavedOcrAttempt:
        attempt_id = uuid4().hex
        payload = json.dumps({
            "schema_version": 1,
            "attempt_id": attempt_id,
            "document_id": attempt.document_id,
            "preset_name": attempt.preset_name,
            "model": attempt.model,
            "threshold_percent": attempt.threshold_percent,
            "pages": [asdict(page) for page in attempt.pages],
        }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        temporary = f".tmp-{uuid4().hex}"
        try:
            if not isinstance(attempt.document_id, str) or not _DOCUMENT_ID.fullmatch(attempt.document_id):
                raise FileNotFoundError("Unknown document directory")
            root_fd = _private_directory_fd(self.root)
            try:
                document_fd = _private_directory_fd(attempt.document_id, dir_fd=root_fd)
            finally:
                os.close(root_fd)
            try:
                try:
                    os.mkdir("ocr", 0o700, dir_fd=document_fd)
                except FileExistsError:
                    pass
                else:
                    os.fsync(document_fd)
                ocr_fd = _private_directory_fd("ocr", dir_fd=document_fd)
            finally:
                os.close(document_fd)
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
                             dir_fd=ocr_fd)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    # link() fails on an existing name: no overwrite of any attempt.
                    os.link(temporary, f"{attempt_id}.json", src_dir_fd=ocr_fd, dst_dir_fd=ocr_fd,
                            follow_symlinks=False)
                finally:
                    try:
                        os.unlink(temporary, dir_fd=ocr_fd)
                    except FileNotFoundError:
                        pass
                os.fsync(ocr_fd)
            finally:
                os.close(ocr_fd)
        except OSError:
            raise OcrAttemptStorageError("OCR attempt storage unavailable") from None
        return SavedOcrAttempt(attempt_id)
