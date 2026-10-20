"""Descriptor-relative reads for private, owner-controlled local POSIX JSON."""

from contextlib import contextmanager
import json
import os
import re
import stat


MAX_JSON_BYTES = 16 * 1024 * 1024


def is_identity(value: str) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Nonfinite JSON number")


def strict_json_loads(content):
    return json.loads(content, object_pairs_hook=_object, parse_constant=_nonfinite)


@contextmanager
def private_directory(path, *, dir_fd=None):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PermissionError("Private owner-only directory required")
        yield fd
    finally:
        os.close(fd)


def read_json(directory_fd: int, name: str):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > MAX_JSON_BYTES):
            raise ValueError("Invalid private JSON file")
        content = stream.read(MAX_JSON_BYTES + 1)
        if len(content) > MAX_JSON_BYTES:
            raise ValueError("JSON file too large")
        return strict_json_loads(content)
