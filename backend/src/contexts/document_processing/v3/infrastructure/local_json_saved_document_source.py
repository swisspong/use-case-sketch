"""Read one saved schema-3 document for OCR from private local POSIX storage.

Identity is the 32-hex directory name assigned by LocalJsonExtractionStore; any
other identity is NotFound without touching the filesystem. Both files are read
through one no-follow document directory descriptor. Structural corruption,
unsafe permissions and I/O failures -> DocumentSourceError (no paths/content).
Domain-level facts (numbering, suggestion types, threshold, id) are passed
through unchanged for OcrAttempt/Interactor to judge.
"""

import os
import re
import stat
from pathlib import Path

from ..application.use_cases.ocr_document_pages.errors import DocumentSourceError
from ..application.use_cases.ocr_document_pages.ports import DocumentNotFound, SavedDocumentForOcr
from ..domain.documents.ocr_attempt import SuggestedPage
from .private_json_files import read_json

MAX_PDF_BYTES = 256 * 1024 * 1024
_DOCUMENT_ID = re.compile(r"[0-9a-f]{32}")


def _private_directory_fd(name, *, dir_fd=None) -> int:
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise PermissionError("Private owner-only directory required")
    return fd


def _read_private_bytes(directory_fd: int, name: str) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > MAX_PDF_BYTES):
            raise ValueError("Invalid private PDF file")
        content = stream.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("PDF file too large")
    return content


class LocalJsonSavedDocumentSource:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def load(self, document_id: str) -> SavedDocumentForOcr | DocumentNotFound:
        if not isinstance(document_id, str) or not _DOCUMENT_ID.fullmatch(document_id):
            return DocumentNotFound()
        try:
            try:
                root_fd = _private_directory_fd(self.root)
            except FileNotFoundError:
                return DocumentNotFound()
            try:
                try:
                    document_fd = _private_directory_fd(document_id, dir_fd=root_fd)
                except FileNotFoundError:
                    return DocumentNotFound()
            finally:
                os.close(root_fd)
            try:
                data = read_json(document_fd, "extraction.json")
                if (not isinstance(data, dict) or data.get("schema_version") != 3
                        or data.get("original_pdf") != "original.pdf"
                        or not isinstance(data.get("pages"), list)):
                    raise ValueError("Unsupported saved extraction record")
                pages = tuple(
                    SuggestedPage(page["number"], page["ocr_suggested"]) for page in data["pages"]
                )
                facts = (data["document_id"], data["threshold_percent"])
                pdf = _read_private_bytes(document_fd, "original.pdf")
            finally:
                os.close(document_fd)
        except (OSError, KeyError, TypeError, ValueError, RecursionError, MemoryError):
            # Symlinks (ELOOP), permissions, I/O and corrupt records alike.
            raise DocumentSourceError("Saved document unavailable") from None
        return SavedDocumentForOcr(facts[0], pdf, pages, threshold_percent=facts[1])
