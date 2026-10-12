"""Operational CLI failures, separate from validated repair history.

Only accepts diagnostic facts already allowlisted by the outer error handler.
Never receives exceptions, source text, provider bodies or configuration.
Uses a trusted private POSIX directory: new directories are mode 0700 and records
are mode 0600. Complete files are linked atomically without overwriting attempts.
Filesystem failures propagate to the auxiliary outer handler; a published file
can remain after failed acknowledgement. This is not a retry/checkpoint ledger
and does not imply rollback of any provider/history effect.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from uuid import uuid4


class LocalJsonRepairFailureLog:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir

    def write(self, *, diagnostic: dict[str, object]) -> None:
        attempt_id = uuid4().hex
        record = {
            "schema_version": 1, "attempt_id": attempt_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "outcome": "error", "code": "system_error", "diagnostic": diagnostic,
        }
        self.log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory = self.log_dir.lstat()
        if not stat.S_ISDIR(directory.st_mode) or directory.st_mode & 0o077:
            raise PermissionError("Unsafe failure log directory")
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.log_dir, suffix=".tmp") as stream:
            stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            # Publish a complete file without replacing another attempt's record.
            os.link(stream.name, self.log_dir / (attempt_id + ".json"))
        directory_fd = os.open(self.log_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
