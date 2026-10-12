"""Local CLI controller and safe outer error handler; no HTTP/API server."""

import argparse
import os
import logging
from pathlib import Path
import sys

from ..application.use_cases.extract_pdf_text.configuration import ExtractionConfig
from ..application.use_cases.extract_pdf_text.errors import InvalidExtractionConfiguration
from ..application.use_cases.extract_pdf_text.request import ExtractPdfTextRequest
from ..composition import build_local_extraction
from ..infrastructure.private_json_files import read_json
from .json_cli_presenter import JsonCliPresenter


def _load_config(path: Path) -> ExtractionConfig:
    """Read bounded, owner-only regular JSON without following final symlinks.

    The parent path must be administrator-controlled. Reuse strict private-file
    parsing: duplicate keys/nonfinite numbers are errors, never silent overrides.
    Only thresholds are read; model presets in the shared file belong to the
    separate OCR use case and are ignored here. Never include content, file
    paths or credentials in configuration diagnostics.
    """
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            data = read_json(directory_fd, path.name)
        finally:
            os.close(directory_fd)
        if not isinstance(data, dict):
            raise TypeError("Expected configuration object")
        return ExtractionConfig(
            unreadable_threshold_percent=data.get("unreadable_threshold_percent", 60),
            suspicious_threshold_percent=data.get("suspicious_threshold_percent"),
        )
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        raise InvalidExtractionConfiguration("Invalid extraction configuration file") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract PDF text into private local PDF/JSON storage and suggest pages for OCR (no model calls).")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--config", required=True, type=Path, help="Trusted administrator JSON thresholds")
    parser.add_argument("--data-dir", required=True, type=Path, help="Private local data directory; parent must exist")
    args = parser.parse_args(argv)
    # Library diagnostics can contain input fragments. The CLI never emits them.
    logging.getLogger("pypdf").setLevel(logging.CRITICAL + 1)
    try:
        config = _load_config(args.config)
        presenter = JsonCliPresenter(data_dir=args.data_dir)  # Per-execution output state.
        boundary = build_local_extraction(config=config, data_dir=args.data_dir, output=presenter)
        boundary.execute(ExtractPdfTextRequest(args.pdf.read_bytes()))
        if presenter.response is None:
            raise RuntimeError("Missing extraction outcome")
        print(presenter.response)
        return presenter.exit_code
    except Exception:
        # Do not expose paths, PDF/text or configuration secrets.
        # This may follow a commit, including a failed stdout write: never retry.
        try:
            print('{"outcome": "error", "code": "system_error"}', file=sys.stderr)
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
