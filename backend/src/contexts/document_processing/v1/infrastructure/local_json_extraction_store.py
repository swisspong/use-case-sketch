"""Private local POSIX storage; publish a complete document on one filesystem."""

from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from ..application.use_cases.extract_pdf_text.errors import DocumentStorageError
from ..application.use_cases.extract_pdf_text.ports import SavedDocument
from ..domain.documents.extraction import DocumentExtraction


@contextmanager
def _directory(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield fd
    finally:
        os.close(fd)


def _write(path: Path, content: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


class LocalJsonExtractionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save(self, document: DocumentExtraction, *, pdf: bytes) -> SavedDocument:
        if any(page.status == "pending_fallback" for page in document.pages):
            raise ValueError("Storage requires terminal pages")
        document_id = uuid4().hex
        payload = json.dumps({
            "schema_version": 1,
            "document_id": document_id,
            "original_pdf": "original.pdf",
            "threshold_percent": document.threshold_percent,
            "pages": [asdict(page) for page in document.pages],
        }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            try:
                self.root.mkdir(mode=0o700)
            except FileExistsError:
                pass
            else:
                with _directory(self.root.parent) as parent_fd:
                    os.fsync(parent_fd)
            with _directory(self.root) as root_fd:
                info = os.fstat(root_fd)
                if info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise PermissionError("Private owner-only data directory required")
                staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.root))
                try:
                    _write(staging / "original.pdf", pdf)
                    _write(staging / "extraction.json", payload)
                    with _directory(staging) as staging_fd:
                        os.fsync(staging_fd)
                    # Cooperating local writers serialize collision check + publish.
                    # Closing root_fd releases the lock on success and every failure.
                    fcntl.flock(root_fd, fcntl.LOCK_EX)
                    destination = self.root / document_id
                    if os.path.lexists(destination):
                        raise FileExistsError("Document identity collision")
                    os.rename(staging, destination)
                    staging = None
                    os.fsync(root_fd)
                finally:
                    if staging is not None:
                        shutil.rmtree(staging)
        except OSError:
            # A post-rename failure can follow a real commit. Do not retry/delete it.
            raise DocumentStorageError("Local document storage unavailable") from None
        return SavedDocument(document_id)
